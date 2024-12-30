import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

from .tasks import REGISTRY
from .utils import cron_to_human_readable


class TimeUnit(str, Enum):
    """Time unit for job scheduling"""

    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


class Status(str, Enum):
    """Status of a job execution log"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobDependency(BaseModel):
    """Job dependency configuration"""

    job_name: str
    required_status: Status = Status.COMPLETED
    within_hours: Optional[float] = None


class JobSchedule(BaseModel):
    """Job interval scheduling configuration"""

    interval: int = Field(gt=0)
    unit: TimeUnit
    at: Optional[str] = None

    @field_validator("at")
    @classmethod
    def validate_at_time(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                hour, minute = map(int, v.split(":"))
                if not (0 <= hour < 24 and 0 <= minute < 60):
                    raise ValueError("Invalid hour/minute values")
                return f"{hour:02d}:{minute:02d}"  # Normalize format
            except ValueError as e:
                raise ValueError("'at' must be in HH:MM format (00:00-23:59)") from e
        return v


class JobOptions(BaseModel):
    """Enhanced job configuration"""

    timeout: Optional[int] = Field(None, ge=1)
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    dependencies: List[JobDependency] = Field(default_factory=list)

    @field_validator("end_date")
    def validate_dates(cls, v, values):
        start = values.get("start_date")
        if start and v and v <= start:
            raise ValueError("end_date must be after start_date")
        return v


class JobCreate(BaseModel):
    """Job definition"""

    task: str
    params: Dict[str, Any]
    options: Optional[JobOptions] = JobOptions()
    schedule: Union[JobSchedule, str] = Field(
        ..., description="Job schedule as either interval or cron expression"
    )

    @field_validator("task")
    def validate_task(cls, v):
        if v not in REGISTRY:
            raise ValueError(f"Task '{v}' not found in registry")
        return v


class Task(BaseModel):
    name: str
    title: str
    description: Optional[str] = None

    @property
    def func(self) -> Callable:
        """Return the task function from the registry"""
        return REGISTRY.get(self.name)


class Job(BaseModel):
    """API response model for jobs"""

    uid: str = Field(default_factory=lambda: uuid.uuid4().hex)
    task: Task
    params: Dict[str, Any]
    options: JobOptions
    schedule: Union[JobSchedule, str]
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

    @classmethod
    def from_user_definition(cls, job_create: JobCreate) -> "Job":
        """Create a Job instance from a JobCreate instance."""
        task = REGISTRY.get(job_create.task)
        if task is None:
            raise ValueError(f"Task '{job_create.task}' not found in registry")

        return cls(
            task=task,
            params=job_create.params,
            options=job_create.options,
            schedule=job_create.schedule,
        )

    def __str__(self) -> str:
        """Generate a string representation of the Job instance."""
        if isinstance(self.schedule, JobSchedule):
            unit = self.schedule.unit.name.lower()
            period = f"every {self.schedule.interval} {unit}"
            if self.schedule.at:
                period += f" at {self.schedule.at}"
        else:
            period = cron_to_human_readable(self.schedule)
        return f"Run '{self.task.name}' {period}"


class JobExecution(BaseModel):
    """API response model for job results"""

    id: int
    job: Job
    status: Status
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retries: int = 0

    class Config:
        from_attributes = True


class Settings(BaseModel):
    """Settings for Homeworq"""

    api_on: bool = Field(False, description="Run without web service")
    api_host: str = Field("localhost", description="Host address for API server")
    api_port: int = Field(8000, description="Port for API server")
    debug: bool = False
    log_path: Optional[str] = Field(
        None,
        description=("Path to log file. Per default, logs will be printed to stdout."),
    )
    db_path: Optional[str] = Field("results.db", description="Path to result database")
    cache_path: Optional[str] = Field("cache", description="Path to job cache")
