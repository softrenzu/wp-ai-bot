import os
import time
import traceback
from datetime import datetime, timedelta

from main import run_once

INTERVAL_HOURS = float(os.environ.get("SCHEDULER_INTERVAL_HOURS", "24"))


def main():
    while True:
        now = datetime.now()
        print(f"[SCHEDULER] Start job at {now.isoformat()}")
        try:
            run_once()
        except Exception as e:
            print("[SCHEDULER] Error during job:", e)
            traceback.print_exc()

        sleep_seconds = int(INTERVAL_HOURS * 3600)
        next_time = now + timedelta(seconds=sleep_seconds)
        print(f"[SCHEDULER] Next job at {next_time.isoformat()}")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
