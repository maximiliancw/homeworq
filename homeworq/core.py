import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from . import models
from .log_config import get_uvicorn_log_config, setup_logging
from .schemas import Job, JobCreate, Log, Settings, Status, TimeUnit
from .tasks import execute_task

logger = logging.getLogger(__name__)


class HQ(BaseModel):
    """
    Main scheduler class that handles job execution and management.

    Attributes:
        settings: Configuration settings for the scheduler
        defaults: List of default jobs to create on startup
        _running: Internal flag indicating if scheduler is running
        _scheduler_engine: Main scheduler loop task
        _api_engine: API server task
        _api: FastAPI instance
        _job_locks: Dictionary of job locks for concurrent execution control
        _job_tasks: Dictionary of running job tasks
    """

    settings: Settings
    defaults: List[JobCreate]
    _running: bool = False
    _beat: Optional[asyncio.Task] = None
    _api_runner: Optional[asyncio.Task] = None
    _api: Optional[FastAPI] = None
    _job_locks: Dict[int, asyncio.Lock] = {}
    _job_runners: Dict[int, asyncio.Task] = {}

    async def _init_api(self) -> FastAPI:
        """Initialize FastAPI instance."""
        from .api import create_api

        return await create_api(self)

    async def _start_api_server(self) -> None:
        """Start the API server if enabled in settings."""
        if not self.settings.api_on:
            logger.debug("API server disabled")
            return

        logger.debug("Starting API server...")
        import uvicorn

        config = uvicorn.Config(
            self._api,
            host=self.settings.api_host,
            port=self.settings.api_port,
            log_config=get_uvicorn_log_config(),
            log_level="debug" if self.settings.debug else "info",
        )

        server = uvicorn.Server(config)
        self._api_runner = asyncio.create_task(server.serve())

        logger.info(
            "API server started at http://%s:%d",
            self.settings.api_host,
            self.settings.api_port,
        )

    def model_post_init(self, __context) -> None:
        """Initialize instance after Pydantic model creation."""
        super().model_post_init(__context)
        self._job_runners = {}
        self._job_locks = {}
        setup_logging(self.settings.log_path, self.settings.debug)
        self._api = None

    async def _calculate_next_run(self, job: Job) -> datetime:
        """Calculate the next run time for a job based on its schedule."""
        now = datetime.now(timezone.utc)  # Use UTC consistently

        if job.schedule_cron:
            raise NotImplementedError("Cron scheduling not implemented")

        if job.schedule_at:
            # Parse time in UTC
            hour, minute = map(int, job.schedule_at.split(":"))
            next_run = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            # If the time has passed for today, move to next interval
            if next_run <= now:
                if job.schedule_unit == TimeUnit.DAYS:
                    next_run += timedelta(days=job.schedule_interval)
                elif job.schedule_unit == TimeUnit.WEEKS:
                    next_run += timedelta(weeks=job.schedule_interval)
                else:
                    raise ValueError(
                        "Time-of-day scheduling only for daily/weekly jobs"
                    )

            return next_run

        # Handle interval-based scheduling
        if not job.schedule_unit or not job.schedule_interval:
            raise ValueError("Job must have either interval or cron schedule")

        interval = {job.schedule_unit.value: job.schedule_interval}
        return now + timedelta(**interval)

    async def _can_run_job(self, job: Job) -> bool:
        """Check if a job is eligible to run."""
        now = datetime.now(timezone.utc)

        # Check date constraints
        if job.start_date and now < job.start_date:
            return False
        if job.end_date and now > job.end_date:
            return False

        # Check last execution
        last_execution = (
            await models.Log.filter(job_id=job.id).order_by("-started_at").first()
        )
        if not last_execution:
            return True

        # If job has a next_run time, use that
        if job.next_run:
            return now >= job.next_run

        # Calculate next run based on last execution
        try:
            next_run = await self._calculate_next_run(job)
            return now >= next_run
        except Exception as e:
            logger.error(f"Error calculating next run for job {job.id}: {str(e)}")
            return False

    async def _execute_job(self, job: Job) -> Log:
        """Execute a job with retry logic."""
        now = datetime.now(timezone.utc)

        # Update job's last_run time
        job.last_run = now
        await job.save()

        execution = await models.Log.create(
            job=job,
            status=Status.RUNNING,
            started_at=now,
            retries=0,
        )

        max_retries = job.max_retries or 0
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                if job.timeout:
                    result = await asyncio.wait_for(
                        execute_task(job.task_name, job.params),
                        timeout=job.timeout,
                    )
                else:
                    result = await execute_task(job.task_name, job.params)

                execution.status = Status.COMPLETED
                execution.result = result
                execution.retries = retry_count
                break

            except asyncio.TimeoutError:
                logger.warning(
                    "Job %d timed out (attempt %d/%d)",
                    job.id,
                    retry_count + 1,
                    max_retries + 1,
                )
                last_error = "Job execution timed out"

            except Exception as e:
                logger.error(
                    "Job %d failed (attempt %d/%d): %s",
                    job.id,
                    retry_count + 1,
                    max_retries + 1,
                    str(e),
                    exc_info=True,
                )
                last_error = str(e)

            retry_count += 1
            if retry_count <= max_retries:
                delay = min(300, (2**retry_count) + random.uniform(0, 1))
                await asyncio.sleep(delay)

        if execution.status != Status.COMPLETED:
            execution.status = Status.FAILED
            execution.error = last_error

        execution.completed_at = datetime.now(timezone.utc)
        execution.duration = (
            execution.completed_at - execution.started_at
        ).total_seconds()
        await execution.save()

        return execution

    async def _run_job_scheduler(self, job: Job) -> None:
        """Run scheduler loop for a single job."""
        lock = self._job_locks.get(job.id) or asyncio.Lock()
        self._job_locks[job.id] = lock

        while self._running:
            try:
                async with lock:
                    if await self._can_run_job(job):
                        # Execute job
                        await self._execute_job(job)

                        # Calculate and save next run time
                        job.next_run = await self._calculate_next_run(job)
                        await job.save()

                    # Calculate sleep time
                    if job.next_run:
                        now = datetime.now(timezone.utc)
                        sleep_time = max(0, (job.next_run - now).total_seconds())
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                    else:
                        # If we can't determine next run time, use a default interval
                        await asyncio.sleep(60)

            except Exception as e:
                logger.error(
                    f"Job scheduler error for {job.id}: {str(e)}", exc_info=True
                )
                # Add a delay before retrying on error
                await asyncio.sleep(60)

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop that manages all job schedulers."""
        while self._running:
            try:
                # Get all active jobs
                jobs = await models.Job.filter(end_date__isnull=True).prefetch_related(
                    "logs"
                )

                # Start schedulers for new jobs
                for job in jobs:
                    if (
                        job.id not in self._job_runners
                        or self._job_runners[job.id].done()
                    ):
                        self._job_runners[job.id] = asyncio.create_task(
                            self._run_job_scheduler(job)
                        )

                # Clean up completed tasks
                for job_id, task in list(self._job_runners.items()):
                    if task.done():
                        try:
                            await task
                        except Exception as e:
                            logger.error(
                                "Job task error for %d: %s",
                                job_id,
                                str(e),
                                exc_info=True,
                            )
                        finally:
                            del self._job_runners[job_id]
                            if job_id in self._job_locks:
                                del self._job_locks[job_id]

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Main scheduler error: {str(e)}", exc_info=True)
                await asyncio.sleep(1)

    async def start(self) -> None:
        """Start the scheduler and API server."""
        if self._running:
            return

        # Initialize API server
        if self.settings.api_on:
            self._api = await self._init_api()
            await self._start_api_server()

        # Start scheduler
        self._running = True
        self._beat = asyncio.create_task(self._scheduler_loop())
        logger.info("Task scheduler started")

        # Create default jobs if any
        for job_create in self.defaults:
            await models.Job.from_schema(job_create, is_default=True)

    async def stop(self) -> None:
        """Stop the scheduler and API server."""
        if not self._running:
            return

        # Disconnect database
        if self._db:
            await self._db.disconnect()

        self._running = False

        # Cancel all job tasks
        for task in self._job_runners.values():
            task.cancel()

        if self._job_runners:
            await asyncio.gather(
                *self._job_runners.values(),
                return_exceptions=True,
            )
            self._job_runners.clear()

        # Cancel main scheduler
        if self._beat:
            self._beat.cancel()
            try:
                await self._beat
            except asyncio.CancelledError:
                pass

        # Stop API server
        if self._api_runner:
            self._api_runner.cancel()
            try:
                await self._api_runner
            except asyncio.CancelledError:
                pass

        logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    @classmethod
    async def _init_db(cls, db_uri) -> None:
        """Initialize database connection."""
        from tortoise import Tortoise

        await Tortoise.init(
            db_url=db_uri,
            modules={"models": ["homeworq.models"]},
        )
        await Tortoise.generate_schemas()

    @classmethod
    def run(
        cls,
        settings: Optional[Settings] = None,
        defaults: Optional[List[JobCreate]] = None,
    ) -> None:
        """
        Run Homeworq instance.

        Args:
            settings: Optional Settings instance for configuration
            defaults: Optional list of default jobs to create
        """

        async def _run_instance() -> None:
            await cls._init_db(db_uri=settings.db_uri)
            instance = cls(
                settings=settings or Settings(),
                defaults=defaults or [],
            )
            await instance.start()

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutdown initiated...")
                await instance.stop()
            except Exception as e:
                logger.error(
                    "Error during execution: %s",
                    str(e),
                    exc_info=True,
                )
                await instance.stop()
                raise

        try:
            asyncio.run(_run_instance())
        except KeyboardInterrupt:
            pass
