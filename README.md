# CoachOS AI Review Service

AI-assisted video review and coach approval service for CoachOS.

## Responsibilities

- AI review generation
- Prompt construction
- Structured review output
- Strengths and improvement areas
- Recommended drills
- Coach edit and approval workflow
- Review status tracking

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker
- External AI provider later

## Project Structure

- `app/api`: API route modules
- `app/core`: configuration and AI provider settings
- `app/db`: database connection and session setup
- `app/models`: database models
- `app/schemas`: request and response schemas
- `app/services`: AI review business logic
- `app/utils`: shared utilities
- `alembic`: database migrations
- `tests`: service tests

## Environment

Copy `.env.example` to `.env` for local development. Do not commit `.env`.

Required values:

- `APP_NAME`
- `ENVIRONMENT`
- `DATABASE_URL`

Future AI values:

- `AI_PROVIDER`
- `AI_API_KEY`
- `AI_MODEL`

## Running Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The service exposes:

- Local app: `http://localhost:8000`
- Docker Compose port: `http://localhost:8004`
- Health check: `GET /health`

## Docker

```bash
docker compose up --build
```

## Planned API

- `POST /reviews`
- `GET /reviews/{review_id}`
- `PATCH /reviews/{review_id}`
- `POST /reviews/{review_id}/approve`
- `POST /reviews/{review_id}/reject`
- `POST /reviews/{review_id}/publish`

## Testing

```bash
pytest
```

## Status

Stage 0: service skeleton created. Review models, AI provider adapter, prompt templates, approval workflow, and tests are next.

## Timeline Outbox Foundation

Stage 5 adds the PostgreSQL outbox model, migration, publisher worker, and safe event factories for AI and coach review activity. Future review transactions must add the factory-produced row before committing domain state. Raw prompts and model output are rejected from metadata; generated reviews stay `coach_only`, while approved coach feedback becomes `athlete_visible`.

```bash
alembic upgrade head
python -m app.workers.outbox_publisher
pytest -q
```
