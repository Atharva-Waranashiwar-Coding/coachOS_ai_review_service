"""Test environment required before application settings are imported."""

import os

os.environ.update(
    {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "ATHLETE_SERVICE_INTERNAL_URL": "http://athlete.test",
        "INTERNAL_SERVICE_TOKEN": "test",
        "JWT_SECRET_KEY": "test",
        "ATHLETE_SERVICE_URL": "http://athlete.test",
        "MEDIA_SERVICE_URL": "http://media.test",
    }
)
