import argparse
import logging
import signal
import sys
import time
from typing import Optional

from backend.core.config import get_settings
from backend.core.database import SessionLocal
from backend.services.webhook_worker import WebhookWorkerService

logger = logging.getLogger("prip.worker")


class GracefulKiller:
    """Catches termination signals to allow active processing batches to finish cleanly."""

    def __init__(self) -> None:
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum: int, frame: object) -> None:
        logger.info(f"Received termination signal ({signum}). Initiating graceful worker shutdown...")
        self.kill_now = True


def run_worker_loop(
    once: bool = False,
    batch_size: Optional[int] = None,
    poll_interval: Optional[float] = None,
    worker_id: Optional[str] = None,
) -> int:
    """
    Main polling loop for the standalone background worker.
    Processes eligible webhook events, updates distributed leases and heartbeats,
    and supports graceful termination.
    """
    settings = get_settings()
    killer = GracefulKiller()

    configured_batch_size = batch_size or settings.worker_batch_size
    configured_poll_interval = poll_interval if poll_interval is not None else settings.worker_poll_interval_seconds
    configured_lease_seconds = settings.worker_lease_seconds

    total_processed = 0
    logger.info(f"Starting PRIP background worker [id={worker_id or 'auto'}, batch_size={configured_batch_size}, poll={configured_poll_interval}s]")

    while not killer.kill_now:
        session = SessionLocal()
        try:
            worker = WebhookWorkerService(session, worker_id=worker_id)
            processed = worker.tick(
                batch_size=configured_batch_size,
                lease_seconds=configured_lease_seconds,
            )
            total_processed += processed

            if processed > 0:
                logger.info(f"Worker tick processed {processed} webhook event(s).")

            if once:
                logger.info("Worker '--once' mode executed. Terminating cleanly.")
                break

            # If no items processed, sleep for poll interval checking kill flag
            sleep_step = 0.5
            elapsed = 0.0
            target_sleep = 0.1 if processed > 0 else configured_poll_interval
            while elapsed < target_sleep and not killer.kill_now:
                time.sleep(min(sleep_step, target_sleep - elapsed))
                elapsed += sleep_step

        except Exception as exc:
            logger.error(f"Unexpected worker error in tick: {exc}", exc_info=True)
            if once:
                raise
            time.sleep(min(5.0, configured_poll_interval))
        finally:
            session.close()

    # Graceful shutdown heartbeat
    shutdown_session = SessionLocal()
    try:
        final_worker = WebhookWorkerService(shutdown_session, worker_id=worker_id)
        final_worker.send_heartbeat(status="STOPPED")
    except Exception as exc:
        logger.warning(f"Could not record final STOPPED heartbeat: {exc}")
    finally:
        shutdown_session.close()

    logger.info(f"PRIP background worker stopped cleanly. Total events processed: {total_processed}")
    return total_processed


def main() -> None:
    parser = argparse.ArgumentParser(description="PRIP Background Webhook Worker Process")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size for event processing")
    parser.add_argument("--poll-interval", type=float, default=None, help="Poll interval in seconds")
    parser.add_argument("--worker-id", type=str, default=None, help="Custom identifier for this worker instance")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    )

    try:
        run_worker_loop(
            once=args.once,
            batch_size=args.batch_size,
            poll_interval=args.poll_interval,
            worker_id=args.worker_id,
        )
    except KeyboardInterrupt:
        logger.info("Worker interrupted by keyboard.")
        sys.exit(0)
    except Exception as exc:
        logger.fatal(f"Fatal worker error: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
