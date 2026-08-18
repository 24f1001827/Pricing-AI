"""Dedicated process for automated evaluations and retraining."""
import signal
import time

from core.logger import get_logger
from core.scheduler import start_scheduler, stop_scheduler

logger = get_logger(__name__)
running = True


def _shutdown(*_args):
    global running
    running = False


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    start_scheduler()
    while running:
        time.sleep(1)
    stop_scheduler()
    logger.info("Scheduler stopped")
