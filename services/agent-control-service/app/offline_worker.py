import time
from datetime import UTC, datetime, timedelta

from .config import get_settings
from .database import build_engine, build_session_factory
from .offline import mark_stale_devices_offline


def main():
    settings = get_settings()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    while True:
        now = datetime.now(UTC)
        with factory() as session:
            mark_stale_devices_offline(session, now - timedelta(seconds=settings.offline_timeout_seconds), now)
            session.commit()
        time.sleep(max(5, settings.heartbeat_interval_seconds // 2))


if __name__ == "__main__":
    main()
