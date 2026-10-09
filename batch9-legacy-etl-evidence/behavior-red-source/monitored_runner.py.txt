"""ETL pipeline wrapper with alerting support.

Wraps ETL execution with monitoring, error tracking, and alerting.
"""

import asyncio
import logging
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


logger = logging.getLogger(__name__)


class ETLMonitor:
    """Monitor ETL pipeline execution and send alerts on failures."""

    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.success = False
        self.error: Optional[str] = None
        self.metadata: Dict[str, Any] = {}

    async def run_with_monitoring(
        self, pipeline_func, *args, **kwargs
    ) -> Dict[str, Any]:
        """Run ETL pipeline with monitoring and alerting.

        Args:
            pipeline_func: Async function to run
            *args: Arguments to pass to function
            **kwargs: Keyword arguments to pass to function

        Returns:
            Pipeline execution results
        """
        self.start_time = time.time()
        self.metadata = {
            "start_time": datetime.now().isoformat(),
            "pipeline": pipeline_func.__name__,
        }

        try:
            logger.info(f"Starting ETL pipeline: {pipeline_func.__name__}")

            # Run the pipeline
            result = await pipeline_func(*args, **kwargs)

            self.success = True
            self.end_time = time.time()
            duration = self.end_time - self.start_time

            self.metadata.update(
                {
                    "end_time": datetime.now().isoformat(),
                    "duration_seconds": round(duration, 2),
                    "success": True,
                    "result": result,
                }
            )

            logger.info(
                f"ETL pipeline completed successfully in {duration:.2f}s: {pipeline_func.__name__}"
            )

            # Send success notification if configured
            await self._send_success_notification()

            return result

        except Exception as e:
            self.success = False
            self.error = str(e)
            self.end_time = time.time()
            duration = self.end_time - self.start_time

            self.metadata.update(
                {
                    "end_time": datetime.now().isoformat(),
                    "duration_seconds": round(duration, 2),
                    "success": False,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )

            logger.error(
                f"ETL pipeline failed after {duration:.2f}s: {pipeline_func.__name__}",
                exc_info=True,
            )

            # Send failure alert
            await self._send_failure_alert(e)

            # Re-raise to maintain normal error handling
            raise

    async def _send_success_notification(self):
        """Send success notification if ETL took unusually long or other conditions."""
        try:
            # Only notify on very long runs (> 1 hour)
            duration = self.end_time - self.start_time
            if duration > 3600:
                from backend.monitoring.alerts import AlertSeverity, send_alert

                await send_alert(
                    title="ETL Pipeline - Long Execution Time",
                    message=f"ETL pipeline completed but took {duration/60:.1f} minutes",
                    severity=AlertSeverity.WARNING,
                    metadata=self.metadata,
                )
        except ImportError:
            logger.warning("Alert system not available")
        except Exception as e:
            logger.error(f"Failed to send success notification: {e}")

    async def _send_failure_alert(self, exception: Exception):
        """Send alert when ETL pipeline fails."""
        try:
            from backend.monitoring.alerts import AlertSeverity, send_alert

            # Determine severity based on error type
            severity = AlertSeverity.ERROR

            # Critical if database connection or data corruption issues
            if any(
                keyword in str(exception).lower()
                for keyword in ["database", "connection", "corrupt", "critical"]
            ):
                severity = AlertSeverity.CRITICAL

            await send_alert(
                title=f"ETL Pipeline Failed: {self.metadata.get('pipeline', 'Unknown')}",
                message=f"Error: {self.error}\n\nDuration: {self.metadata.get('duration_seconds', 0):.2f}s",
                severity=severity,
                metadata=self.metadata,
            )

            logger.info("ETL failure alert sent successfully")

        except ImportError:
            logger.warning("Alert system not available, logging error only")
        except Exception as e:
            logger.error(f"Failed to send ETL failure alert: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics from the last run."""
        return {
            "success": self.success,
            "duration_seconds": (
                round(self.end_time - self.start_time, 2)
                if self.start_time and self.end_time
                else None
            ),
            "error": self.error,
            "metadata": self.metadata,
        }


async def run_monitored_pipeline():
    """Run the Kenya data pipeline with monitoring."""
    try:
        from etl.kenya_pipeline import KenyaDataPipeline

        pipeline = KenyaDataPipeline()
        monitor = ETLMonitor()

        result = await monitor.run_with_monitoring(pipeline.run_full_pipeline)

        # Export metrics for Prometheus
        metrics = monitor.get_metrics()
        print(f"\nETL Metrics: {metrics}")

        return result

    except Exception as e:
        logger.critical(f"Fatal ETL error: {e}", exc_info=True)
        sys.exit(1)


async def run_monitored_backfill():
    """Run backfill with monitoring."""
    try:
        from etl.backfill import run_backfill

        monitor = ETLMonitor()

        result = await monitor.run_with_monitoring(run_backfill)

        metrics = monitor.get_metrics()
        print(f"\nBackfill Metrics: {metrics}")

        return result

    except Exception as e:
        logger.critical(f"Fatal backfill error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        asyncio.run(run_monitored_backfill())
    else:
        asyncio.run(run_monitored_pipeline())
