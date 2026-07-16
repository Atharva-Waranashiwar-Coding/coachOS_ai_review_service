# CoachOS AI Review Service

The AI Review Service creates evidence-bound coaching drafts for uploaded videos, then keeps the coach in control of revision, approval, or rejection. It owns review requests, persisted outputs, revisions, generation jobs, and timeline outbox events.

## Review Lifecycle

`pending -> processing -> generated -> approved|rejected`

Generated output is a coach-only baseline. Coaches save append-only revisions with `expected_revision_number`; stale saves return `409 STALE_REVIEW_REVISION` and are never merged automatically. Approval requires explicit confirmation and creates one immutable snapshot. Its visibility defaults to `coach_only` and is selected at approval. Snapshots never include private coach notes, provider metadata, prompts, or raw provider output.

Generation failures retry with bounded exponential backoff and terminate as `failed`; coaches can retry failed reviews or cancel pending work. Request creation writes the review, its job, and `ai_review_requested` outbox event in one transaction. Generated, failed, edited, approved, and rejected transitions also create their timeline events transactionally.

The request path reads athlete, session, and uploaded-video metadata using the coach bearer token, stores a minimal context snapshot, and returns `202`. The background `review-worker` sends only that snapshot and coach-provided textual evidence to the provider. It never sends raw video bytes, storage URLs, credentials, or raw provider output.

## API

All routes are under `/api/v1`, require a valid coach JWT, and return the standard error envelope.

- `POST /reviews` creates an async review. Pass `Idempotency-Key` for safe client retries.
- `GET /reviews`, `GET /reviews/athletes/{athlete_id}/reviews`, `GET /reviews/videos/{video_id}/reviews` list reviews.
- `GET /reviews/{id}` and `GET /reviews/{id}/status` fetch a review or polling status.
- `POST /reviews/{id}/revisions`, `GET /revisions`, and `GET /revisions/{revision_id}` manage immutable revisions.
- `POST /reviews/{id}/preview` returns the athlete-facing representation without private notes.
- `POST /reviews/{id}/approve`, `/reject`, `/retry`, and `/cancel` transition lifecycle state.
- `GET /reviews/{id}/approved` and `/audit-log` return immutable approval and safe audit history for coaches.

The approved endpoint also returns `review_id`, `athlete_id`, and `status: approved` for Athlete Service drill-assignment validation. Recommended drills remain advisory; this service never creates Athlete Service assignments.

Athlete-facing endpoints:

- `GET /api/v1/athlete/reviews`
- `GET /api/v1/athlete/reviews/{review_id}`

These routes require an athlete JWT and resolve the linked athlete by forwarding that bearer token to `GET {ATHLETE_SERVICE_URL}/api/v1/athlete/me`. Queries require `approved` status, an immutable approved snapshot, `athlete_visible` visibility, and an exact athlete ID match.

Athlete schemas include only approved summary content, coach-approved athlete messages, strengths, improvement areas, safe observations, recommended drills, approval time, and an allowlisted practice-session context. They exclude confidence, evidence, coach notes, generated drafts, revisions, rejection data, provider metadata, model details, token usage, raw responses, prompts, and audit history. Inaccessible or coach-only feedback returns `404`.

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

The API entrypoint executes `alembic upgrade head` before startup. Both workers set `RUN_MIGRATIONS=false`, wait for API readiness, and use the same structured logging configuration. The multi-stage image runs as UID/GID `10001`.

## Production Operations

- `GET /health/live` reports process liveness.
- `GET /health/ready` verifies PostgreSQL connectivity.
- `GET /metrics` exposes Prometheus HTTP metrics.
- `X-Request-ID` is propagated across HTTP requests and emitted in JSON stdout logs.

Use `coachos-infra` for HTTPS termination, rate limiting, CORS allowlists, hardened read-only containers, Prometheus/Grafana, Loki/Promtail, image deployment, and isolated AI Review PostgreSQL backup/restore.

## Quality

```bash
black --check app tests alembic
ruff check app tests alembic
mypy app
pytest -q
```

Current tradeoffs: provider invocation is a poll-based worker rather than a queue, context is captured at request time rather than refreshed at execution time, and this MVP uses an external structured-output provider. The provider boundary, prompt version, schema version, job table, and revision history leave room for queues, additional providers, retrieval, and future vision features without changing public review ownership.

## Progress Insight Data Contract

Stage 10 adds:

- `GET /api/v1/insights/athletes/{athlete_id}/approved-reviews`
- `POST /api/v1/insights/athletes/approved-review-summary`

The single-athlete route uses coach authorization and verifies athlete access. The batch route accepts only authenticated Athlete Service calls and enforces `INSIGHT_MAX_BATCH_ATHLETES`.

Both contracts return immutable approved snapshots within start-inclusive, end-exclusive UTC boundaries. Safe fields include review ID/type, approval time, visibility, structured strengths, improvement areas, recommendations, nullable taxonomy codes, and source session/video IDs.

They exclude generated and rejected reviews, coach notes, prompts, raw provider output, provider/model metadata, token usage, confidence/evidence internals, revision history, and audit history. `taxonomy_code` is optional so historical structured JSON remains valid. Configure batch auth with `INSIGHT_INTERNAL_SERVICE_TOKEN` or the shared internal service token.
