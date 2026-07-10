import signal
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.outbox_publisher import OutboxPublisher

running = True


def stop(*_: object) -> None:
    global running
    running = False


def main() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        with SessionLocal() as db:
            OutboxPublisher(db).publish_batch()
        time.sleep(settings.outbox_poll_interval_seconds)


if __name__ == "__main__":
    main()
