import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from tortoise import Tortoise

from .models import JobExecution
from .schemas import Status

logger = logging.getLogger(__name__)


class Database:
    """Async database storage using TortoiseORM"""

    def __init__(self, db_uri: str = "sqlite://homeworq.db"):
        self.db_uri = db_uri
        self._connected = False

    async def connect(self):
        """Initialize database connection and models"""
        if self._connected:
            return

        try:
            # Initialize Tortoise ORM
            await Tortoise.init(
                db_url=self.db_uri,
                modules={"models": ["homeworq.models"]},
                use_tz=True,
            )

            # Generate schemas
            await Tortoise.generate_schemas()

            self._connected = True
            logger.info("Connected to database at %s", self.db_uri)

        except Exception as e:
            logger.error("Failed to connect to database: %s", str(e))
            raise

    async def disconnect(self):
        """Close database connection"""
        if self._connected:
            await Tortoise.close_connections()
            self._connected = False
            logger.info("Disconnected from database")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def store_execution(self, execution: JobExecution) -> int:
        """Store a job execution result"""
        if not self._connected:
            raise RuntimeError("Database not connected")

        try:
            execution_model = await JobExecution.from_schema(execution)
            return execution_model.id

        except Exception as e:
            logger.error(f"Failed to store execution result: {str(e)}")
            raise

    async def get_job_history(
        self,
        job_id: int,
        limit: int = 100,
        status: Optional[Status] = None,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get execution history for a job"""
        if not self._connected:
            raise RuntimeError("Database not connected")

        try:
            # Start building query
            query = JobExecution.filter(job__id=job_id)

            if status:
                query = query.filter(status=status)
            if since:
                query = query.filter(started_at__gte=since)

            # Get results
            executions = (
                await query.order_by("-started_at")
                .limit(limit)
                .prefetch_related("job")  # noqa
            )

            # Convert to schema format
            return [execution.to_schema() for execution in executions]

        except Exception as e:
            logger.error(f"Failed to get job history: {str(e)}")
            raise

    async def get_last_execution(self, job_id: str) -> Optional[JobExecution]:
        """Get the last execution of a job"""
        if not self._connected:
            raise RuntimeError("Database not connected")

        try:
            execution = (
                await JobExecution.filter(job__id=job_id)
                .order_by("-started_at")
                .first()
                .prefetch_related("job")
            )

            if execution:
                return execution.to_schema()
            return None

        except Exception as e:
            logger.error(f"Failed to get last execution: {str(e)}")
            raise

    async def get_recent_failures(
        self, limit: int = 100, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get recent failed job executions"""
        if not self._connected:
            raise RuntimeError("Database not connected")

        try:
            # Build query
            query = JobExecution.filter(status=Status.FAILED)

            if since:
                query = query.filter(started_at__gte=since)

            # Get results
            executions = (
                await query.order_by("-started_at")
                .limit(limit)
                .prefetch_related("job")  # noqa
            )

            # Convert to schema format
            return [execution.to_schema() for execution in executions]

        except Exception as e:
            logger.error(f"Failed to get recent failures: {str(e)}")
            raise

    async def cleanup_old_records(self, days: int = 30):
        """Delete old execution records"""
        if not self._connected:
            raise RuntimeError("Database not connected")

        try:
            cutoff = datetime.now() - timedelta(days=days)
            await JobExecution.filter(created_at__lt=cutoff).delete()

        except Exception as e:
            logger.error(f"Failed to cleanup old records: {str(e)}")
            raise
