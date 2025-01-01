import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from .db import Database
from .models import Job, JobDependency, JobExecution
from .schemas import Job as JobSchema
from .schemas import JobCreate
from .schemas import JobExecution as JobExecutionSchema
from .schemas import JobUpdate, Settings, Status, TimeUnit
from .tasks import execute_task

logger = logging.getLogger(__name__)


class Homeworq(BaseModel):
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
    defaults: List[JobCreate] = []
    _running: bool = False
    _db: Optional["Database"] = None
    _scheduler_engine: Optional[asyncio.Task] = None
    _api_engine: Optional[asyncio.Task] = None
    _api: Optional[FastAPI] = None
    _job_locks: Dict[int, asyncio.Lock] = {}
    _job_tasks: Dict[int, asyncio.Task] = {}

    def model_post_init(self, __context) -> None:
        """Initialize instance after Pydantic model creation."""
        super().model_post_init(__context)
        self._job_tasks = {}
        self._job_locks = {}
        self._setup_logging()
        self._api = None

    def _setup_logging(self) -> None:
        """Configure logging based on settings."""
        if self.settings.log_path:
            handler = logging.FileHandler(self.settings.log_path)
        else:
            handler = logging.StreamHandler()

        fstring = "%(levelname)s:\t%(asctime)s\t%(message)s"
        formatter = logging.Formatter(fstring)
        handler.setFormatter(formatter)
        level = logging.DEBUG if self.settings.debug else logging.INFO

        logger.setLevel(level)
        handler.setLevel(level)
        logger.addHandler(handler)

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
            log_level=logger.level,
        )

        server = uvicorn.Server(config)
        self._api_engine = asyncio.create_task(server.serve())

        logger.info(
            "API server started at http://%s:%d",
            self.settings.api_host,
            self.settings.api_port,
        )

    async def _execute_job(self, job: Job) -> JobExecution:
        """
        Execute a job with retry logic.

        Args:
            job: Job instance to execute

        Returns:
            JobExecution instance with execution results
        """
        now = datetime.now(timezone.utc)
        execution = await JobExecution.create(
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
                # Exponential backoff with jitter
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

        # Store execution in database
        if self._db:
            await self._db.store_execution(execution)

        return execution

    async def _calculate_next_run(self, job: Job) -> datetime:
        """
        Calculate the next run time for a job based on its schedule.

        Args:
            job: Job instance

        Returns:
            datetime of next scheduled run

        Raises:
            ValueError: If schedule configuration is invalid
            NotImplementedError: For unimplemented cron scheduling
        """
        now = datetime.now()

        if job.schedule_cron:
            # TODO: Implement cron parsing
            raise NotImplementedError("Cron scheduling not implemented")

        if job.schedule_at:
            hour, minute = map(int, job.schedule_at.split(":"))
            next_run = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

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

        interval = {job.schedule_unit.value: job.schedule_interval}
        return now + timedelta(**interval)

    async def _can_run_job(self, job: Job) -> bool:
        """
        Check if a job is eligible to run based on its schedule and constraints.

        Args:
            job: Job instance to check

        Returns:
            bool indicating if job can run
        """
        now = datetime.now()
        if job.start_date and now < job.start_date:
            return False
        if job.end_date and now > job.end_date:
            return False

        last_execution = (
            await JobExecution.filter(job_id=job.id).order_by("-started_at").first()
        )
        if not last_execution:
            return True

        next_run = await self._calculate_next_run(job)
        return next_run <= now

    async def _run_job_scheduler(self, job: Job) -> None:
        """
        Run scheduler loop for a single job.

        Args:
            job: Job instance to schedule
        """
        lock = self._job_locks.get(job.id) or asyncio.Lock()
        self._job_locks[job.id] = lock

        while self._running:
            try:
                async with lock:
                    if await self._can_run_job(job):
                        await self._execute_job(job)
                        job.next_run = await self._calculate_next_run(job)
                        await job.save()

                        sleep_time = (job.next_run - datetime.now()).total_seconds()
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(
                    f"Job scheduler error for {job.id}: {str(e)}", exc_info=True
                )
                await asyncio.sleep(60)  # Wait before retrying

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop that manages all job schedulers."""
        while self._running:
            try:
                jobs = await Job.all()
                for job in jobs:
                    if job.id not in self._job_tasks or self._job_tasks[job.id].done():
                        self._job_tasks[job.id] = asyncio.create_task(
                            self._run_job_scheduler(job)
                        )

                # Clean up completed tasks
                for job_id, task in list(self._job_tasks.items()):
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
                            del self._job_tasks[job_id]

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Main scheduler error: {str(e)}", exc_info=True)
                await asyncio.sleep(1)

    async def list_jobs(
        self,
        limit: int = 100,
        offset: int = 0,
        task: Optional[str] = None,
    ) -> List[JobSchema]:
        """
        List jobs with pagination and optional filtering by task name.

        Args:
            limit: Maximum number of jobs to return.
            offset: Number of jobs to skip.
            task: Optional task name to filter jobs.

        Returns:
            List of JobSchema instances.
        """
        query = Job.all()

        if task:
            query = query.filter(task_name=task)

        jobs = await query.offset(offset).limit(limit)
        return [await job.to_schema() for job in jobs]

    async def get_job(self, job_id: int) -> JobSchema:
        """
        Retrieve a job by its ID.

        Args:
            job_id: ID of the job to retrieve.

        Returns:
            JobSchema instance representing the job.

        Raises:
            ValueError: If the job with the given ID does not exist.
        """
        job = await Job.filter(id=job_id).first()

        if not job:
            raise ValueError(f"Job with ID '{job_id}' not found")

        return await job.to_schema()

    async def create_job(self, job_create: JobCreate) -> JobSchema:
        """
        Create a new job.

        Args:
            job_create: JobCreate instance with job configuration

        Returns:
            JobSchema instance of created job
        """
        job = await Job.from_schema(job_create)
        await job.save()
        return await job.to_schema()

    async def update_job(
        self,
        job_id: int,
        job_update: JobUpdate,
    ) -> JobSchema:
        """
        Update an existing job.

        Args:
            job_id: ID of job to update
            job_update: JobUpdate instance with updated configuration

        Returns:
            JobSchema instance of updated job
        """
        job = await Job.get(id=job_id)
        await job.update_from_schema(job_update)

        if job_id in self._job_tasks:
            self._job_tasks[job_id].cancel()
            self._job_tasks[job_id] = asyncio.create_task(self._run_job_scheduler(job))

        return job.to_schema()

    async def upsert_job(self, job_create: JobCreate) -> JobSchema:
        """
        Upsert a job: update if it exists, or create a new job.

        Args:
            job_create: JobCreate instance with job configuration.

        Returns:
            JobSchema instance of the created or updated job.
        """
        # Check if the job exists based on a unique identifier (e.g., task_name)
        existing_job = await Job.filter(task_name=job_create.task).first()

        if existing_job:
            # Update the existing job
            job_update = JobUpdate(**job_create.model_dump())
            await existing_job.update_from_schema(job_update)
            await existing_job.save()

            # Restart the job scheduler if necessary
            if existing_job.id in self._job_tasks:
                self._job_tasks[existing_job.id].cancel()
                self._job_tasks[existing_job.id] = asyncio.create_task(
                    self._run_job_scheduler(existing_job)
                )

            logger.info(f"Updated existing job: {existing_job.id}")
            return await existing_job.to_schema()

        # Otherwise, create a new job
        new_job = await Job.from_schema(job_create)
        await new_job.save()
        logger.info(f"Created new job: {new_job.id}")
        return await new_job.to_schema()

    async def delete_job(self, job_id: int) -> None:
        """
        Delete a job and its related data.

        Args:
            job_id: ID of job to delete
        """
        await JobExecution.filter(job_id=job_id).delete()
        await JobDependency.filter(job_id=job_id).delete()
        await Job.filter(id=job_id).delete()

        if job_id in self._job_tasks:
            self._job_tasks[job_id].cancel()
            del self._job_tasks[job_id]

    async def get_job_executions(
        self, job_id: int = None, skip: int = 0, limit: int = 100
    ) -> List[JobExecutionSchema]:
        """
        Get execution history for a job or all jobs.

        Args:
            job_id: ID of job to get history for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of JobExecutionSchema instances
        """
        if job_id:
            executions = (
                await JobExecution.filter(job_id=job_id)
                .order_by("-started_at")
                .offset(skip)
                .limit(limit)
            )
        else:
            executions = (
                await JobExecution.all()
                .prefetch_related("job")
                .order_by("-started_at")
                .offset(skip)
                .limit(limit)
            )

        return [await execution.to_schema() for execution in executions]

    async def start(self) -> None:
        """Start the scheduler and API server."""
        if self._running:
            return

        # Initialize database
        self._db = Database(self.settings.db_path)
        await self._db.connect()

        # Initialize API server
        if self.settings.api_on:
            self._api = await self._init_api()
            await self._start_api_server()

        # Start scheduler
        self._running = True
        self._scheduler_engine = asyncio.create_task(self._scheduler_loop())
        logger.info("Task scheduler started")

        # Create default jobs if any
        for job_create in self.defaults:
            logger.debug(f"MODEL DUMP: {job_create.model_dump()}")
            await self.upsert_job(job_create)

    async def stop(self) -> None:
        """Stop the scheduler and API server."""
        if not self._running:
            return

        # Disconnect database
        if self._db:
            await self._db.disconnect()

        self._running = False

        # Cancel all job tasks
        for task in self._job_tasks.values():
            task.cancel()

        if self._job_tasks:
            await asyncio.gather(
                *self._job_tasks.values(),
                return_exceptions=True,
            )
            self._job_tasks.clear()

        # Cancel main scheduler
        if self._scheduler_engine:
            self._scheduler_engine.cancel()
            try:
                await self._scheduler_engine
            except asyncio.CancelledError:
                pass

        # Stop API server
        if self._api_engine:
            self._api_engine.cancel()
            try:
                await self._api_engine
            except asyncio.CancelledError:
                pass

        logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    @classmethod
    async def init_db(cls) -> None:
        """Initialize database connection."""
        from tortoise import Tortoise

        await Tortoise.init(
            db_url="sqlite://db.sqlite3", modules={"models": ["homeworq.models"]}
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
            await cls.init_db()
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
                logger.error("Error during execution: %s", str(e), exc_info=True)
                await instance.stop()
                raise

        try:
            asyncio.run(_run_instance())
        except KeyboardInterrupt:
            pass
