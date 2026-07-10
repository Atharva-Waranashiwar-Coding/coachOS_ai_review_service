# CoachOS AI Review Service

The AI Review Service creates evidence-bound coaching drafts for uploaded videos, then keeps the coach in control of revision, approval, or rejection. It owns review requests, persisted outputs, revisions, generation jobs, and timeline outbox events.

## Review Lifecycle

`pending -> processing -> generated -> approved|rejected`

Generation failures retry with bounded exponential backoff and terminate as `failed`; coaches can retry failed reviews or cancel pending work. Request creation writes the review, its job, and `ai_review_requested` outbox event in one transaction. Generated, failed, edited, approved, and rejected transitions also create their timeline events transactionally.

The request path reads athlete, session, and uploaded-video metadata using the coach bearer token, stores a minimal context snapshot, and returns `202`. The background `review-worker` sends only that snapshot and coach-provided textual evidence to the provider. It never sends raw video bytes, storage URLs, credentials, or raw provider output.

## API

All routes are under `/api/v1`, require a valid coach JWT, and return the standard error envelope.

- `POST /reviews` creates an async review. Pass `Idempotency-Key` for safe client retries.
- `GET /reviews`, `GET /reviews/athletes/{athlete_id}/reviews`, `GET /reviews/videos/{video_id}/reviews` list reviews.
- `GET /reviews/{id}` and `GET /reviews/{id}/status` fetch a review or polling status.
- `PATCH /reviews/{id}/draft` saves a coach revision.
- `POST /reviews/{id}/approve`, `/reject`, `/retry`, and `/cancel` transition lifecycle state.

## Context and Output

Inputs may include athlete profile metadata, practice session metadata, uploaded-video metadata, coach context, objectives, focus areas, manual observations, transcript, and frame observations. The output is validated by Pydantic and persists a summary, observations with confidence/evidence, strengths, improvement areas, recommended drills, and limitations.

The provider instruction explicitly prohibits claims of raw-video viewing, medical diagnosis, or certainty unsupported by supplied evidence. Every output remains coach-only until a coach approval event makes the final feedback athlete-visible in the timeline.

## Configuration

Copy `.env.example` to `.env`; do not commit it. Required local values include `DATABASE_URL`, `JWT_SECRET_KEY`, Athlete and Media service URLs, the internal Athlete Service timeline credentials, and `OPENAI_API_KEY` when running generation. `AI_*`, `REVIEW_JOB_*`, `MAX_*`, and `PROMPT_VERSION` control provider behavior and safe input bounds.

## Run

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8004
python -m app.workers.review_worker
python -m app.workers.outbox_publisher
```

Docker Compose starts the API, PostgreSQL, review worker, and outbox worker. Supply real secrets through an uncommitted `.env` or deployment secret store rather than `.env.example`.

## Quality

```bash
black --check app tests alembic
ruff check app tests alembic
mypy app
pytest -q
```

Current tradeoffs: provider invocation is a poll-based worker rather than a queue, context is captured at request time rather than refreshed at execution time, and this MVP uses an external structured-output provider. The provider boundary, prompt version, schema version, job table, and revision history leave room for queues, additional providers, retrieval, and future vision features without changing public review ownership.
