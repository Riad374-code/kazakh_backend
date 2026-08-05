"""
Background Automation Scheduler (Backend Task 12).

Dependency-free periodic scheduler that keeps the operational database fresh by
re-running the pipeline stages on an interval:
    boot (seed checkpoints) -> inference refresh -> risk scoring -> energy
    impact -> trend analysis -> anomaly masks -> DB commit.

Launched automatically as a daemon thread by the FastAPI lifespan, or standalone via:
    python -m src.pipeline.scheduler --interval-seconds 3600
"""

from __future__ import annotations

import os
import time
import signal
import logging
import threading
from typing import Optional, Callable

from src.storage.db import CaspianDatabase
from src.pipeline.bootstrap import run_full_refresh

logging.basicConfig(level=logging.INFO, format="%(levelname)s: [%(name)s] %(message)s")
logger = logging.getLogger("BackgroundScheduler")

DEFAULT_INTERVAL_SECONDS = int(os.environ.get("REFRESH_INTERVAL_SECONDS", "3600"))


class CaspianScheduler:
    """Background loop that refreshes the AI/risk/energy/trend store periodically."""

    def __init__(self, db: CaspianDatabase, interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
                 refresh_fn: Callable[[], None] = None):
        self.db = db
        self.interval = max(60, int(interval_seconds))
        self.refresh_fn = refresh_fn or (lambda: run_full_refresh(self.db))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run_loop(self) -> None:
        logger.info(f"Background scheduler started (refresh interval {self.interval}s).")
        while not self._stop.is_set():
            try:
                self.refresh_fn()
                logger.info("Scheduled refresh completed successfully.")
            except Exception as exc:  # keep the loop alive across transient failures
                logger.warning(f"Scheduled refresh failed: {exc}")
            # Sleep in small slices so stop() responds promptly.
            deadline = time.time() + self.interval
            while time.time() < deadline and not self._stop.is_set():
                time.sleep(min(1.0, deadline - time.time()))
        logger.info("Background scheduler stopped.")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="caspian-scheduler",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


_scheduler: Optional[CaspianScheduler] = None


def global_scheduler(db: Optional[CaspianDatabase] = None) -> CaspianScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CaspianScheduler(db or CaspianDatabase())
    return _scheduler


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Caspian AI pipeline background scheduler")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS,
                        help="Refresh interval in seconds (min 60).")
    parser.add_argument("--run-once", action="store_true",
                        help="Run a single refresh then exit instead of looping.")
    args = parser.parse_args()

    db = CaspianDatabase()
    print("=== CASPIAN AI BACKGROUND AUTOMATION SCHEDULER ===")
    if args.run_once:
        result = run_full_refresh(db)
        stats = result["stats"]
        print(f"[DONE] Single refresh complete: {stats['incidents']} incidents, "
              f"{stats['risk_scores']} risk scores, {stats['energy_impacts']} energy impacts.")
    else:
        sched = CaspianScheduler(db, interval_seconds=args.interval_seconds)
        sched.start()
        print(f"Scheduler running. Press Ctrl+C to stop (interval {sched.interval}s).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sched.stop()
            print("Scheduler stopped.")