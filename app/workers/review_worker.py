"""Poll and execute persisted review generation jobs outside the HTTP request path."""

import logging
import signal
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.ai.openai_provider import OpenAIProvider
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.review import (
    AIReview,
    AuditAction,
    JobStatus,
    ReviewAuditEvent,
    ReviewGenerationJob,
    ReviewResult,
    ReviewStatus,
)
from app.services.timeline_events import ai_timeline_event

logger = logging.getLogger(__name__)
running = True
configure_logging()


def stop(*_: object) -> None:
    global running
    running = False


def run_once() -> bool:
    """Claim one job atomically and either persist its result or schedule a retry."""
    with SessionLocal() as db:
        job = db.scalar(
            select(ReviewGenerationJob)
            .where(
                ReviewGenerationJob.status == JobStatus.PENDING, ReviewGenerationJob.available_at <= datetime.now(UTC)
            )
            .order_by(ReviewGenerationJob.created_at)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return False

        review = db.get(AIReview, job.review_id)
        if not review or review.status == ReviewStatus.CANCELLED:
            job.status = JobStatus.CANCELLED
            db.commit()
            return True

        job.status, job.started_at = JobStatus.PROCESSING, datetime.now(UTC)
        review.status, review.generation_started_at, review.failure_reason = (
            ReviewStatus.PROCESSING,
            datetime.now(UTC),
            None,
        )
        db.commit()

        try:
            # The provider receives typed text/metadata context only. Storage URLs and raw video are never included.
            context = {
                "review_type": review.review_type.value,
                "athlete_context": review.context_snapshot.get("athlete", {}),
                "practice_session": review.context_snapshot.get("practice_session", {}),
                "video_metadata": review.context_snapshot.get("video", {}),
                "coach_context": review.coach_context,
                "session_objectives": review.session_objectives,
                "requested_focus_areas": review.requested_focus_areas,
                "manual_observations": review.manual_observations,
                "transcript": review.transcript,
                "frame_observations": review.frame_observations,
                "evidence_policy": "Raw video was not provided. Use only supplied evidence and state limitations.",
            }
            output = OpenAIProvider().generate_review(context)
            db.refresh(review)
            if review.status == ReviewStatus.CANCELLED:
                job.status = JobStatus.CANCELLED
                db.commit()
                return True

            db.add(ReviewResult(review_id=review.id, **output.model_dump(mode="json")))
            completed_at = datetime.now(UTC)
            review.status = ReviewStatus.GENERATED
            review.generation_completed_at = completed_at
            review.generated_at = completed_at
            review.model_provider, review.model_name = "openai", settings.openai_model
            job.status, job.completed_at, job.last_error = JobStatus.COMPLETED, completed_at, None
            db.add(
                ReviewAuditEvent(
                    review_id=review.id,
                    actor_user_id=None,
                    action_type=AuditAction.REVIEW_GENERATED,
                    metadata_json={"prompt_version": review.prompt_version},
                    occurred_at=completed_at,
                )
            )
            db.add(
                ai_timeline_event(
                    event_type="ai_review_generated",
                    athlete_id=review.athlete_id,
                    review_id=review.id,
                    actor_user_id=review.requested_by_user_id,
                    occurred_at=completed_at,
                    metadata={
                        "review_id": str(review.id),
                        "video_id": str(review.video_id),
                        "practice_session_id": str(review.practice_session_id),
                    },
                )
            )
            db.commit()
            return True
        except Exception:  # Provider details remain in logs, never in client-visible review state.
            logger.exception("AI review generation failed", extra={"review_id": str(job.review_id)})
            job.attempt_count += 1
            job.last_error = "Generation could not be completed."
            retrying = job.attempt_count < settings.review_job_max_attempts
            job.status = JobStatus.PENDING if retrying else JobStatus.FAILED
            job.available_at = datetime.now(UTC) + timedelta(
                seconds=min(settings.review_job_base_retry_seconds * 2 ** max(job.attempt_count - 1, 0), 3600)
            )
            review.status = ReviewStatus.PENDING if retrying else ReviewStatus.FAILED
            review.failure_reason = "Generation could not be completed."
            if not retrying:
                db.add(
                    ai_timeline_event(
                        event_type="ai_review_failed",
                        athlete_id=review.athlete_id,
                        review_id=review.id,
                        actor_user_id=review.requested_by_user_id,
                        occurred_at=datetime.now(UTC),
                        metadata={
                            "review_id": str(review.id),
                            "video_id": str(review.video_id),
                            "practice_session_id": str(review.practice_session_id),
                        },
                    )
                )
            db.commit()
            return True


def main() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        run_once()
        time.sleep(settings.review_job_poll_interval_seconds)


if __name__ == "__main__":
    main()
