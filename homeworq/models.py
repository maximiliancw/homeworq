from datetime import datetime

from tortoise import fields, models

from .schemas import Job as JobSchema
from .schemas import JobCreate, JobOptions, JobSchedule
from .schemas import Log as LogSchema
from .schemas import Status, TimeUnit
from .tasks import get_registered_task


class BaseModel(models.Model):
    id = fields.IntField(pk=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True


class Job(BaseModel):
    id: str = fields.CharField(pk=True, max_length=64)
    task_name = fields.CharField(max_length=255)
    params = fields.JSONField()
    schedule_interval = fields.IntField(null=True)
    schedule_unit = fields.CharEnumField(TimeUnit, null=True)
    schedule_at = fields.CharField(max_length=5, null=True)
    schedule_cron = fields.CharField(max_length=100, null=True)
    timeout = fields.IntField(null=True)
    max_retries = fields.IntField(null=True)
    start_date = fields.DatetimeField(null=True)
    end_date = fields.DatetimeField(null=True)
    last_run = fields.DatetimeField(null=True)
    next_run = fields.DatetimeField(null=True)

    @staticmethod
    def create_default_hash(schema: JobCreate) -> str:
        """Create a unique hash for a default job configuration"""
        import hashlib
        import json

        # Create a deterministic representation of the JobCreate object
        # Only include fields that define the job's essential nature
        hash_dict = {
            "task": schema.task,
            "params": schema.params,
        }

        # Create a deterministic JSON string
        hash_input = json.dumps(hash_dict, sort_keys=True)

        # Create SHA-256 hash
        return hashlib.sha256(hash_input.encode()).hexdigest()

    @classmethod
    async def from_schema(
        cls,
        schema: JobCreate,
        is_default: bool = False,
    ) -> "Job":
        """Create Job model from JobCreate schema with upsert support for default jobs"""
        schedule_dict = {}
        if isinstance(schema.schedule, str):
            schedule_dict["schedule_cron"] = schema.schedule
        else:
            for k, v in schema.schedule.model_dump().items():
                schedule_dict[f"schedule_{k}"] = v

        if is_default:
            default_hash = cls.create_default_hash(schema)
            # Try to find existing default job by its ID
            existing_job = await cls.get_or_none(id=default_hash)
            if existing_job:
                # Update existing job
                existing_job.params = schema.params
                existing_job.timeout = schema.options.timeout
                existing_job.max_retries = schema.options.max_retries
                existing_job.start_date = schema.options.start_date
                existing_job.end_date = schema.options.end_date

                # Reset schedule parameters
                if "schedule_cron" in schedule_dict:
                    existing_job.schedule_interval = None
                    existing_job.schedule_unit = None
                    existing_job.schedule_at = None
                else:
                    existing_job.schedule_cron = None
                # Set new schedule parameters
                for k, v in schedule_dict.items():
                    setattr(existing_job, k, v)
                # Save/update job
                await existing_job.save()
                return existing_job

        # Create new job
        job = await cls.create(
            id=cls.create_default_hash(schema) if is_default else None,
            task_name=schema.task,
            params=schema.params,
            timeout=schema.options.timeout,
            max_retries=schema.options.max_retries,
            start_date=schema.options.start_date,
            end_date=schema.options.end_date,
            next_run=datetime.now(),  # Set initial next_run time
            **schedule_dict,
        )
        return job

    async def to_schema(self) -> JobSchema:
        """Convert DB model to Pydantic schema"""
        if self.schedule_cron:
            schedule = self.schedule_cron
        elif self.schedule_interval and self.schedule_unit:
            schedule = JobSchedule(
                interval=self.schedule_interval,
                unit=self.schedule_unit,
                at=self.schedule_at,
            )
        else:
            raise ValueError("Job must have either cron or interval schedule")

        options = JobOptions(
            timeout=self.timeout,
            max_retries=self.max_retries,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        return JobSchema(
            id=self.id,
            task=get_registered_task(self.task_name),
            params=self.params,
            options=options,
            schedule=schedule,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_run=self.last_run,
            next_run=self.next_run,
        )

    async def update_from_schema(self, job_update: JobSchema) -> None:
        """Update model from schema"""
        if job_update.params is not None:
            self.params = job_update.params

        if job_update.options:
            self.timeout = job_update.options.timeout
            self.max_retries = job_update.options.max_retries
            self.start_date = job_update.options.start_date
            self.end_date = job_update.options.end_date

        if job_update.schedule:
            if isinstance(job_update.schedule, str):
                self.schedule_cron = job_update.schedule
                self.schedule_interval = None
                self.schedule_unit = None
                self.schedule_at = None
            else:
                self.schedule_cron = None
                self.schedule_interval = job_update.schedule.interval
                self.schedule_unit = job_update.schedule.unit
                self.schedule_at = job_update.schedule.at

        await self.save()


class Log(BaseModel):
    job = fields.ForeignKeyField("models.Job", related_name="logs")
    status = fields.CharEnumField(Status)
    started_at = fields.DatetimeField()
    completed_at = fields.DatetimeField(null=True)
    duration = fields.FloatField(null=True)
    result = fields.JSONField(null=True)
    error = fields.TextField(null=True)
    retries = fields.IntField(default=0)

    async def to_schema(self) -> LogSchema:
        """Convert DB model to Pydantic schema"""
        return LogSchema(
            id=self.id,
            job_id=self.job.id,
            job=await self.job.to_schema(),
            status=self.status,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration=self.duration,
            result=self.result,
            error=self.error,
            retries=self.retries,
            created_at=self.created_at,
        )

    @classmethod
    async def from_schema(cls, schema: LogSchema) -> "Log":
        """Create model from schema"""
        return await cls.create(
            job_id=schema.job_id,
            status=schema.status,
            started_at=schema.started_at,
            completed_at=schema.completed_at,
            duration=schema.duration,
            result=schema.result,
            error=schema.error,
            retries=schema.retries,
        )
