"""Container health check for the unit-hold expiry worker."""

import os
import sys
import time
from pathlib import Path


def main() -> int:
    interval = max(5, int(os.getenv("UNIT_HOLD_EXPIRY_INTERVAL_SECONDS", "30")))
    maximum_age = max(30, interval * 3)
    heartbeat = Path(
        os.getenv("UNIT_HOLD_EXPIRY_HEARTBEAT_PATH", "/tmp/unit-hold-expiry.heartbeat")
    )
    try:
        age = time.time() - heartbeat.stat().st_mtime
    except OSError:
        return 1
    return 0 if age <= maximum_age else 1


if __name__ == "__main__":
    sys.exit(main())
