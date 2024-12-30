import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI
from pydantic import BaseModel

from .db import Database
from .models import (
    Job,
    JobCreate,
    JobExecution,
    JobSchedule,
    Settings,
    Status,
    TimeUnit,
)
from .tasks import REGISTRY

logger = logging.getLogger(__name__)


class Homeworq(BaseModel):
    """
    Homeworq: A powerful task scheduling system with integrated REST API.

    This class combines a robust task scheduler with a FastAPI application,
    allowing users to manage tasks and jobs through both Python API and HTTP endpoints.
    The FastAPI server is started automatically when the scheduler starts.

    Key Features:
    - Task scheduling with interval and time-based triggers
    - Built-in REST API for task/job management
    - Result storage and job history
    - Configurable logging and settings
    """

    settings: Settings
    defaults: List[JobCreate] = []
    jobs: List[Job] = []
    _db: Optional[Database] = None
    _running: bool = False
    _scheduler_engine: Optional[asyncio.Task] = None
    _api_engine: Optional[asyncio.Task] = None
    _api: Optional[FastAPI] = None
    _job_locks: Dict[str, asyncio.Lock] = {}
    _job_tasks: Dict[str, asyncio.Task] = {}

    def model_post_init(self, __context):
        """
        Custom initialization logic after Pydantic handles validation.
        """
        super().model_post_init(__context)
        self._job_tasks = {}
        self._job_locks = {}

        from .db import Database

        self._db = Database(self.settings.db_path)

        # Create default jobs
        for default_job in self.defaults:
            self.jobs.append(Job.from_user_definition(default_job))

        self._setup_logging(
            level=logging.DEBUG if self.settings.debug else logging.INFO
        )
        # Remove API initialization from here - we'll do it in start()
        self._api = None

    def get_tasks(self) -> Dict[str, Any]:
        """
        Returns the task registry.

        Returns:
            Dict[str, Any]: A dictionary of tasks
        """
        return REGISTRY

    def _setup_logging(self, level: int = logging.INFO):
        """Configure logging based on settings"""

        if self.settings.log_path:
            handler = logging.FileHandler(self.settings.log_path)
        else:
            handler = logging.StreamHandler()

        formatter = logging.Formatter("%(levelname)s:\t%(asctime)s\t%(message)s")
        handler.setFormatter(formatter)

        logger.setLevel(level)
        handler.setLevel(level)
        logger.addHandler(handler)

    async def _init_api(self) -> FastAPI:
        """Initialize the FastAPI application if API is enabled"""
        from .api import create_api

        return await create_api(self)

    async def _start_api_server(self):
        """Start the FastAPI server using uvicorn if API is enabled"""
        if not self.settings.api_on:
            logger.debug("API server disabled, skipping startup")
            return

        if not (self.settings.api_host and self.settings.api_port):
            raise ValueError("API host and port must be specified")

        logger.debug("API server enabled. Starting up...")
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
            "API server started at http://%s:%s",
            self.settings.api_host,
            self.settings.api_port,
        )

    def _calculate_next_run(
        self,
        schedule: Union[JobSchedule, str],
        last_run: Optional[datetime] = None,
    ) -> datetime:
        """
        Calculate next run time based on schedule

        Args:
            schedule: Job schedule configuration
            last_run: Last execution time, if any

        Returns:
            datetime: Next scheduled run time
        """
        now = datetime.now()

        # Handle cron expressions
        if isinstance(schedule, str):
            if schedule.at:
                raise ValueError("Do not use 'at' with cron expression")
            # TODO: Implement cron expression parsing
            raise NotImplementedError("Cron scheduling not yet implemented")

        # Handle interval scheduling
        interval = schedule.interval
        unit = TimeUnit(schedule.unit)

        if schedule.at:
            # Time-of-day scheduling
            hour, minute = map(int, schedule.at.split(":"))
            target_time = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            if target_time <= now:
                if unit == TimeUnit.DAYS:
                    target_time += timedelta(days=1)
                elif unit == TimeUnit.WEEKS:
                    target_time += timedelta(weeks=1)
                else:
                    raise ValueError(
                        "Time-of-day scheduling only supported for daily/weekly jobs"
                    )

            return target_time

        # Regular interval-based scheduling
        if not last_run:
            return now + timedelta(**{unit.value: interval})

        next_run = last_run + timedelta(**{unit.value: interval})
        while next_run <= now:
            next_run += timedelta(**{unit.value: interval})

        return next_run

    async def _execute_job(self, job: Job) -> JobExecution:
        """
        Execute a job with retry logic and proper error handling

        Args:
            job: Job to execute

        Returns:
            JobExecution: Execution result
        """
        task = REGISTRY.get(job.task.name)
        if task is None:
            raise ValueError(f"Task {job.task.name} not found")

        task_func = task.func

        execution = JobExecution(
            job=job,
            status=Status.RUNNING,
            started_at=datetime.now(),
            retries=0,
        )

        max_retries = job.options.max_retries or 0
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                # Execute task with timeout if specified
                if job.options.timeout:
                    result = await asyncio.wait_for(
                        asyncio.ensure_future(task_func(**job.params)),
                        timeout=job.options.timeout,
                    )
                else:
                    result = await asyncio.ensure_future(task_func(**job.params))

                execution.status = Status.COMPLETED
                execution.result = result
                execution.retries = retry_count
                break

            except asyncio.TimeoutError:
                last_error = "Task execution timed out"
                logger.warning(
                    "Job %s timed out (attempt %d/%d)",
                    job.name,
                    retry_count + 1,
                    max_retries + 1,
                )

            except Exception as e:
                last_error = str(e)
                logger.error(
                    "Job %s failed (attempt %d/%d): %s",
                    job.name,
                    retry_count + 1,
                    max_retries + 1,
                    str(e),
                    exc_info=True,
                )

            retry_count += 1
            if retry_count <= max_retries:
                # Exponential backoff with jitter
                delay = min(
                    300, (2**retry_count) + random.uniform(0, 1)
                )  # Max 5 minutes
                await asyncio.sleep(delay)

        if execution.status != Status.COMPLETED:
            execution.status = Status.FAILED
            execution.error = last_error

        execution.completed_at = datetime.now()
        if execution.completed_at and execution.started_at:
            execution.duration = (
                execution.completed_at - execution.started_at
            ).total_seconds()

        return execution

    async def _can_run_job(self, job: Job) -> bool:
        """
        Check if a job can run based on its schedule

        Args:
            job: Job to check

        Returns:
            bool: True if the job can run, False otherwise
        """
        now = datetime.now()
        if job.options.start_date and now < job.options.start_date:
            return False
        if job.options.end_date and now > job.options.end_date:
            return False

        last_execution = await self._db.get_last_execution(job.name)
        if not last_execution:
            return True

        next_run = self._calculate_next_run(job.schedule, last_execution.started_at)
        return next_run <= now

    async def _run_job_scheduler(self, job: Job):
        """
        Individual job scheduler loop that manages a single job's execution

        Args:
            job: Job to schedule
        """
        lock = self._job_locks.get(job.uid) or asyncio.Lock()
        self._job_locks[job.uid] = lock

        while self._running:
            try:
                async with lock:
                    last_execution = await self._db.get_last_execution(job.uid)
                    last_run = last_execution.started_at if last_execution else None

                    next_run = self._calculate_next_run(job.schedule, last_run)
                    now = datetime.now()

                    if next_run <= now and await self._can_run_job(job):
                        execution = await self._execute_job(job)
                        await self._db.store_execution(execution)
                        next_run = self._calculate_next_run(
                            job.schedule, execution.started_at
                        )

                    sleep_time = (next_run - datetime.now()).total_seconds()
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(
                    f"Job scheduler error for {job.uid}: {str(e)}",
                    exc_info=True,
                )
                await asyncio.sleep(1)

    async def _scheduler_loop(self):
        """Main scheduler loop that manages individual job schedulers"""
        while self._running:
            try:
                # Start schedulers for new jobs
                for job in self.jobs:
                    if (
                        job.uid not in self._job_tasks
                        or self._job_tasks[job.uid].done()
                    ):
                        self._job_tasks[job.uid] = asyncio.create_task(
                            self._run_job_scheduler(job)
                        )

                # Clean up completed tasks
                for job_name, task in list(self._job_tasks.items()):
                    if task.done():
                        try:
                            await task
                        except Exception as e:
                            logger.error(
                                f"Job task error for {job_name}: {str(e)}",
                                exc_info=True,
                            )
                        finally:
                            del self._job_tasks[job_name]

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Main scheduler error: {str(e)}", exc_info=True)
                await asyncio.sleep(1)

    async def start(self):
        """
        Start both the scheduler and API server.
        """
        if self._running:
            return

        # Connect to database
        await self._db.connect()

        # Initialize and start API server
        if self.settings.api_on:
            self._api = await self._init_api()
            await self._start_api_server()

        # Start scheduler
        self._running = True
        self._scheduler_engine = asyncio.create_task(self._scheduler_loop())
        logger.info("Task scheduler started")

    async def stop(self):
        """
        Stop both the scheduler and API server gracefully.

        This method ensures clean shutdown by:
        1. Stopping new job scheduling
        2. Cancelling all running job tasks
        3. Stopping the API server
        4. Closing database connections
        """
        if not self._running:
            return

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

        # Stop scheduler
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

        # Disconnect from database
        await self._db.disconnect()
        logger.info("Homeworq shutdown complete")

    def live(self) -> bool:
        """
        Check if the system is running.

        If API is enabled, checks both scheduler and API server status.
        If API is disabled, only checks scheduler status.

        Returns:
            bool: True if all enabled components are running, False otherwise.
        """
        if self.settings.api_on:
            api_running = self._api_engine and not self._api_engine.done()
            return self._running and api_running
        return self._running

    @classmethod
    def run(cls, settings: Settings, defaults: List[JobCreate] = None):
        """
        Class method to create and run a Homeworq instance.

        Args:
            settings: Configuration settings
            defaults: Optional list of default jobs

        Example:
            from homeworq import Homeworq, Settings, JobCreate, register_task

            @register_task("Ping URL")
            def ping(url: str) -> Dict[str, Any]:
                with urllib.request.urlopen(url) as req:
                    return {
                        "status": req.status,
                        "headers": dict(req.headers),
                    }

            if __name__ == "__main__":
                settings = Settings(api_on=True, debug=False)
                jobs = [
                    JobCreate(
                        task="ping",
                        params={"url": "https://reddit.com"},
                        schedule=JobSchedule(
                            interval=1,
                            unit=TimeUnit.DAYS,
                            at="08:00"
                        )
                    ),
                    JobCreate(
                        task="ping",
                        params={"url": "https://example.com"},
                        options: JobOptions(timeout=10),
                        schedule="0 8 * * 1-5"
                    ),
                ]

                Homeworq.run(settings, defaults=jobs)
        """

        async def _run_instance():
            instance = cls(settings=settings, defaults=defaults or [])
            await instance.start()

            try:
                # Keep the main task running
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutdown initiated...")
                await instance.stop()
            except Exception as e:
                logger.error(f"Error during execution: {e}", exc_info=True)
                await instance.stop()
                raise

        try:
            asyncio.run(_run_instance())
        except KeyboardInterrupt:
            pass  # Clean exit on Ctrl+C
