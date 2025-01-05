import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from . import models
from .cron import CronParser
from .log_config import get_uvicorn_log_config, setup_logging
from .schemas import Job, JobCreate, Log, Settings, Status, TimeUnit
from .tasks import execute_task

logger = logging.getLogger(__name__)


class HQ(BaseModel):
    """
    Main scheduler class that manages job execution and scheduling.

    This class maintains a single asyncio task that continuously monitors
    jobs and executes them when they are due. It also provides an optional
    FastAPI-based web interface for job management.

    The scheduler is instantiated with settings and optional default jobs,
    making it clear which configuration is being used.

    Can be used either as a context manager or directly:

    Example:
        With context manager:
        ```python
        settings = Settings(api_on=True, db_uri="sqlite://db.sqlite")
        default_jobs = [JobCreate(...)]

        with HQ(settings=settings, defaults=default_jobs) as hq:
            # Scheduler is running here
            # Will be automatically stopped when exiting the context
            ...
        ```

        Direct usage:
        ```python
        hq = HQ(settings=settings, defaults=default_jobs)
        hq.run()
        ```

    Attributes:
        settings (Settings): Configuration settings for the scheduler
        defaults (List[JobCreate]): List of default jobs to create on startup
    """

    settings: Settings
    defaults: List[JobCreate] = []

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data):
        super().__init__(**data)
        self._running: bool = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._api_task: Optional[asyncio.Task] = None
        self._api: Optional[FastAPI] = None
        self._executing_jobs: Set[str] = set()
        setup_logging(self.settings.log_path, self.settings.debug)

    async def _init_api(self) -> FastAPI:
        """Initialize and configure FastAPI instance."""
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
        self._api_task = asyncio.create_task(server.serve())
        logger.info(
            "API server started at http://%s:%d",
            self.settings.api_host,
            self.settings.api_port,
        )

    async def _calculate_next_run(self, job: Job) -> datetime:
        """
        Calculate the next scheduled run time for a job.

        Args:
            job: Job instance to calculate next run for

        Returns:
            datetime: Next scheduled run time in UTC

        Raises:
            ValueError: If job schedule configuration is invalid
        """
        now = datetime.now(timezone.utc)

        if job.schedule_cron:
            parser = CronParser(job.schedule_cron)
            return parser.get_next_run(after=now)

        if job.schedule_at:
            # Parse time in UTC
            hour, minute = map(int, job.schedule_at.split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If time has passed today, move to next interval
            if next_run <= now:
                if job.schedule_unit == TimeUnit.DAYS:
                    next_run += timedelta(days=job.schedule_interval)
                elif job.schedule_unit == TimeUnit.WEEKS:
                    next_run += timedelta(weeks=job.schedule_interval)
                else:
                    raise ValueError(
                        "Time-of-day scheduling only supported for daily/weekly jobs"
                    )
            return next_run

        # Handle interval-based scheduling
        if not job.schedule_unit or not job.schedule_interval:
            raise ValueError("Job must have either interval or cron schedule")

        interval = {job.schedule_unit.value: job.schedule_interval}
        return now + timedelta(**interval)

    async def _can_run_job(self, job: Job) -> bool:
        """
        Check if a job is eligible to run.

        Args:
            job: Job instance to check

        Returns:
            bool: True if job can run, False otherwise
        """
        now = datetime.now(timezone.utc)

        # Skip if job is currently executing
        if job.id in self._executing_jobs:
            return False

        # Check date constraints
        if job.start_date and now < job.start_date:
            return False
        if job.end_date and now > job.end_date:
            return False

        # Use next_run time if available
        if job.next_run:
            return now >= job.next_run

        # Calculate based on last execution
        try:
            last_execution = (
                await models.Log.filter(
                    job_id=job.id,
                )
                .order_by("-started_at")
                .first()
            )
            if not last_execution:
                return True

            next_run = await self._calculate_next_run(job)
            return now >= next_run
        except Exception as e:
            logger.error(
                "Error calculating next run for job %s: %s",
                job.id,
                str(e),
            )
            return False

    async def _execute_job(self, job: Job) -> Log:
        """
        Execute a job with retry logic.

        Args:
            job: Job to execute

        Returns:
            Log: Execution log entry
        """
        now = datetime.now(timezone.utc)
        self._executing_jobs.add(job.id)

        try:
            # Update job's last_run time
            job.last_run = now
            await job.save()

            # Create execution log
            execution = await models.Log.create(
                job=job,
                status=Status.RUNNING,
                started_at=now,
                retries=0,
            )

            max_retries = job.max_retries or 0
            retry_count = 0
            last_error = None

            # Execute with retries
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
                        "Job %s timed out (attempt %d/%d)",
                        job.id,
                        retry_count + 1,
                        max_retries + 1,
                    )
                    last_error = "Job execution timed out"

                except Exception as e:
                    logger.error(
                        "Job %s failed (attempt %d/%d): %s",
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

            # Update execution status
            if execution.status != Status.COMPLETED:
                execution.status = Status.FAILED
                execution.error = last_error

            execution.completed_at = datetime.now(timezone.utc)
            execution.duration = (
                execution.completed_at - execution.started_at
            ).total_seconds()
            await execution.save()

            return execution

        finally:
            self._executing_jobs.remove(job.id)

    async def _scheduler_loop(self) -> None:
        """
        Main scheduler loop that checks for and executes due jobs.

        This is the core scheduling logic that runs continuously while
        the scheduler is active. It queries for active jobs, checks if
        they are due to run, and executes them in separate tasks.
        """
        while self._running:
            try:
                # Get all active jobs
                jobs = await models.Job.filter(
                    end_date__isnull=True,
                ).prefetch_related("logs")

                # Check and execute due jobs
                for job in jobs:
                    if await self._can_run_job(job):
                        # Execute job in separate task
                        asyncio.create_task(self._handle_job_execution(job))

                # Small delay before next check
                await asyncio.sleep(1)

            except Exception as e:
                logger.error("Scheduler loop error: %s", str(e), exc_info=True)
                await asyncio.sleep(1)

    async def _handle_job_execution(self, job: Job) -> None:
        """
        Handle the execution of a single job, including updating its next run time.

        Args:
            job: Job to execute
        """
        try:
            # Execute job
            await self._execute_job(job)

            # Calculate and save next run time
            job.next_run = await self._calculate_next_run(job)
            await job.save()

        except Exception as e:
            logger.error(
                "Error handling job %s execution: %s",
                job.id,
                str(e),
                exc_info=True,
            )

    async def start(self) -> None:
        """Start the scheduler and optional API server."""
        if self._running:
            return

        # Initialize API server if enabled
        if self.settings.api_on:
            logger.info("Starting API server...")
            self._api = await self._init_api()
            await self._start_api_server()

        # Create default jobs
        logger.info("Creating/updating default jobs...")
        for job_create in self.defaults:
            await models.Job.from_schema(job_create, is_default=True)

        # Start scheduler
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler and API server."""
        if not self._running:
            return

        self._running = False

        # Cancel scheduler task
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # Stop API server
        if self._api_task:
            self._api_task.cancel()
            try:
                await self._api_task
            except asyncio.CancelledError:
                pass

        logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    async def _init_db(self) -> None:
        """Initialize database connection."""
        from tortoise import Tortoise

        await Tortoise.init(
            db_url=self.settings.db_uri,
            modules={"models": ["homeworq.models"]},
            table_name_generator=lambda cls: f"hq_{cls.__name__.lower()}s",
        )
        await Tortoise.generate_schemas()

    async def __aenter__(self) -> "HQ":
        """
        Async context manager entry.
        Sets up database connection and API server if enabled.
        """
        await self._init_db()

        # Initialize API server if enabled
        if self.settings.api_on:
            logger.info("Starting API server...")
            self._api = await self._init_api()
            await self._start_api_server()

        # Create default jobs if any
        logger.info("Creating/updating default jobs...")
        for job_create in self.defaults:
            await models.Job.from_schema(job_create, is_default=True)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Async context manager exit.
        Cleans up resources including API server and database connections.
        """
        # Stop API server if running
        if self._api_task:
            self._api_task.cancel()
            try:
                await self._api_task
            except asyncio.CancelledError:
                pass

        # Close database connection
        from tortoise import Tortoise

        await Tortoise.close_connections()

    def __enter__(self) -> "HQ":
        """
        Synchronous context manager entry.
        Creates event loop if needed and sets up resources.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.__aenter__())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Synchronous context manager exit.
        Cleans up resources.
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.__aexit__(exc_type, exc_val, exc_tb))

    async def run(self) -> None:
        """
        Run the scheduler.

        This method starts the main scheduler loop. It should be called
        after the HQ instance has been properly initialized (typically
        within a context manager).

        Example:
            ```python
            async with HQ(settings=settings, defaults=default_jobs) as hq:
                await hq.run()  # Starts the scheduler
            ```
        """
        if self._running:
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started")

        try:
            # Run until stopped
            while self._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutdown initiated...")
        finally:
            await self.stop()

    def run_sync(self) -> None:
        """
        Synchronous version of run().

        Example:
            ```python
            with HQ(settings=settings, defaults=default_jobs) as hq:
                hq.run_sync()  # Starts the scheduler
            ```
        """
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.run())
        except KeyboardInterrupt:
            pass

        async def _run_instance() -> None:
            await self._init_db()
            await self.start()

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutdown initiated...")
                await self.stop()
            except Exception as e:
                logger.error(
                    "Error during execution: %s",
                    str(e),
                    exc_info=True,
                )
                await self.stop()
                raise

        try:
            asyncio.run(_run_instance())
        except KeyboardInterrupt:
            pass
