import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260710_0002"
down_revision = "20260710_0001"
branch_labels = None
depends_on = None


def upgrade():
    rs = postgresql.ENUM(
        "pending", "processing", "generated", "failed", "cancelled", "approved", "rejected", name="review_status"
    )
    rt = postgresql.ENUM(
        "general",
        "hitting",
        "pitching",
        "fielding",
        "throwing",
        "footwork",
        "mobility",
        "strength",
        "decision_making",
        name="review_type",
    )
    js = postgresql.ENUM("pending", "processing", "completed", "failed", "cancelled", name="review_job_status")
    [x.create(op.get_bind(), checkfirst=True) for x in (rs, rt, js)]
    op.create_table(
        "ai_reviews",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("athlete_id", sa.UUID(), nullable=False),
        sa.Column("practice_session_id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=False),
        sa.Column("status", rs, nullable=False),
        sa.Column("review_type", rt, nullable=False),
        sa.Column("coach_context", sa.Text()),
        sa.Column("session_objectives", postgresql.JSONB(), nullable=False),
        sa.Column("requested_focus_areas", postgresql.JSONB(), nullable=False),
        sa.Column("manual_observations", postgresql.JSONB(), nullable=False),
        sa.Column("transcript", sa.Text()),
        sa.Column("frame_observations", postgresql.JSONB(), nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(255)),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("model_provider", sa.String(100)),
        sa.Column("model_name", sa.String(200)),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("generation_started_at", sa.DateTime(timezone=True)),
        sa.Column("generation_completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("requested_by_user_id", "idempotency_key", name="uq_review_idempotency"),
    )
    op.create_table(
        "review_results",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("ai_reviews.id"), unique=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("observations", postgresql.JSONB(), nullable=False),
        sa.Column("strengths", postgresql.JSONB(), nullable=False),
        sa.Column("improvement_areas", postgresql.JSONB(), nullable=False),
        sa.Column("recommended_drills", postgresql.JSONB(), nullable=False),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("provider_request_id", sa.String(255)),
        sa.Column("input_token_count", sa.Integer()),
        sa.Column("output_token_count", sa.Integer()),
        sa.Column("estimated_cost", sa.Numeric(12, 6)),
        sa.Column("raw_provider_response", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "review_revisions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("ai_reviews.id")),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("edited_by_user_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("observations", postgresql.JSONB(), nullable=False),
        sa.Column("strengths", postgresql.JSONB(), nullable=False),
        sa.Column("improvement_areas", postgresql.JSONB(), nullable=False),
        sa.Column("recommended_drills", postgresql.JSONB(), nullable=False),
        sa.Column("coach_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("review_id", "revision_number", name="uq_revision_number"),
    )
    op.create_table(
        "review_generation_jobs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("ai_reviews.id"), unique=True),
        sa.Column("status", js, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("worker_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for name, col in [
        ("ix_reviews_athlete", "athlete_id"),
        ("ix_reviews_video", "video_id"),
        ("ix_reviews_session", "practice_session_id"),
        ("ix_reviews_status", "status"),
        ("ix_reviews_requested_by", "requested_by_user_id"),
        ("ix_reviews_created", "created_at"),
    ]:
        op.create_index(name, "ai_reviews", [col])
    op.create_index("ix_revision_review_number", "review_revisions", ["review_id", "revision_number"])
    op.create_index("ix_job_status_available", "review_generation_jobs", ["status", "available_at"])


def downgrade():
    op.drop_table("review_generation_jobs")
    op.drop_table("review_revisions")
    op.drop_table("review_results")
    op.drop_table("ai_reviews")
    [
        postgresql.ENUM(name=x).drop(op.get_bind(), checkfirst=True)
        for x in ("review_job_status", "review_type", "review_status")
    ]
