from fastapi import FastAPI

app = FastAPI(title="CoachOS AI Review Service")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "ai-review"}
