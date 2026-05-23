from __future__ import annotations

import signal
import sys
import time
from datetime import datetime, timezone

from app.database import init_database
from app.repository import OICRepository
from app.services.oic_interface import MockOICCollector


def main() -> None:
    init_database()
    repository = OICRepository()
    repository.seed_if_empty(total=170)
    collector = MockOICCollector(repository)

    should_run = True

    def stop_handler(signum, frame):  # type: ignore[unused-argument]
        nonlocal should_run
        should_run = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    print("Mock collector started. Running every 30 seconds...")
    while should_run:
        updated = collector.collect_cycle()
        now = datetime.now(timezone.utc).isoformat()
        print(f"[{now}] mock collector updated {updated} integrations")
        time.sleep(30)

    print("Mock collector stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
