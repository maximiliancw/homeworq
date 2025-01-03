import base64
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import models
from .core import HQ
from .schemas import Job, JobCreate, JobUpdate, Log, PaginatedResponse, Status
from .tasks import Task, get_registered_task, get_registered_tasks

logger = logging.getLogger(__name__)

API_DESCRIPTION = """
This is the API documentation for **homeworq**.
It's built on top of the OpenAPI standard and provides
a RESTful interface for consuming/managing tasks, jobs, and logs.

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
"""


async def create_api(hq: HQ) -> FastAPI:
    app = FastAPI(
        title="homeworq",
        description=API_DESCRIPTION,
        summary="A self-contained, async-first task scheduling system with an integrated JSON API and web interface. Built with Python 3.13+.",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files and templates setup
    app.mount(
        "/static",
        StaticFiles(
            directory=os.path.join(
                os.path.dirname(__file__),
                "static",
            ),
        ),
        name="static",
    )

    templates = Jinja2Templates(
        directory=os.path.join(os.path.dirname(__file__), "templates")
    )

    # Create dependency for protected routes
    if hq.settings.api_auth:
        from .auth import authenticate

        async def is_authenticated(
            valid: Annotated[bool, Depends(authenticate)]
        ) -> bool:
            return valid

    else:
        # No-op dependency when auth is disabled
        async def is_authenticated() -> bool:
            return True

    # Login routes
    @app.get("/login", include_in_schema=False)
    async def login_page(request: Request):
        if not hq.settings.api_auth:
            return RedirectResponse(url="/", status_code=302)
        return templates.TemplateResponse("login.html", {"request": request})

    @app.post("/login", include_in_schema=False)
    async def login(
        request: Request, username: str = Form(...), password: str = Form(...)
    ):
        if not hq.settings.api_auth:
            return RedirectResponse(url="/", status_code=302)

        try:
            # Create dummy credentials to use with get_current_username
            credentials = HTTPBasicCredentials(
                username=username,
                password=password,
            )
            authenticate(credentials)  # Will raise HTTPException if invalid

            # If we get here, credentials are valid
            response = RedirectResponse(url="/", status_code=302)

            # Set Basic auth header
            auth_str = f"{username}:{password}"
            auth_bytes = base64.b64encode(auth_str.encode()).decode()
            response.headers["Authorization"] = f"Basic {auth_bytes}"

            return response

        except HTTPException:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid username or password"},
                status_code=401,
            )

    # UI Routes
    @app.get("/", include_in_schema=False)
    async def view_dashboard(
        request: Request,
        auth: bool = Depends(is_authenticated),
    ):
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request},
        )

    @app.get("/tasks", include_in_schema=False)
    async def view_tasks(
        request: Request,
        auth: bool = Depends(is_authenticated),
    ):
        return templates.TemplateResponse(
            "tasks/list.html",
            {"request": request},
        )

    @app.get("/jobs", include_in_schema=False)
    async def view_jobs(
        request: Request,
        auth: bool = Depends(is_authenticated),
    ):
        return templates.TemplateResponse(
            "jobs/list.html",
            {"request": request},
        )

    @app.get("/jobs/{job_id}", include_in_schema=False)
    async def view_job_detail(
        request: Request,
        job_id: str,
        auth: bool = Depends(is_authenticated),
    ):
        """UI route for job details page"""
        job = await models.Job.get_or_none(id=job_id)
        if not job:
            raise HTTPException(404, f"Job #{job_id} not found")
        return templates.TemplateResponse(
            "jobs/detail.html",
            {"request": request, "job": await job.to_schema()},
        )

    @app.get("/logs", include_in_schema=False)
    async def view_logs(
        request: Request,
        auth: bool = Depends(is_authenticated),
    ):
        return templates.TemplateResponse(
            "logs/list.html",
            {"request": request},
        )

    @app.get("/logs/{log_id}", include_in_schema=False)
    async def view_log_detail(
        request: Request,
        log_id: int,
        auth: bool = Depends(is_authenticated),
    ):
        """UI route for log details page"""
        log = await models.Log.get_or_none(id=log_id)
        if not log:
            raise HTTPException(404, f"Log #{log_id} not found")
        return templates.TemplateResponse(
            "logs/detail.html",
            {"request": request, "log": log},
        )

    # API Routes

    @app.get("/api/analytics/recent-activity", tags=["Analytics"])
    async def get_recent_activity():
        """Get recent job logs for the activity feed."""
        logs = (
            await models.Log.all()
            .prefetch_related("job")
            .limit(3)
            .order_by("-started_at")
        )
        return [await log.to_schema() for log in logs]

    @app.get("/api/analytics/upcoming-executions", tags=["Analytics"])
    async def get_upcoming_executions():
        """Get upcoming scheduled job executions."""
        now = datetime.now(timezone.utc)
        jobs = await models.Job.filter(next_run__gt=now).limit(3).order_by("next_run")
        return [await job.to_schema() for job in jobs]

    @app.get("/api/analytics/execution-history", tags=["Analytics"])
    async def get_execution_history():
        """Get execution history for charting."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)

        logs = (
            await models.Log.filter(
                started_at__gte=start_date, started_at__lte=end_date
            )
            .limit(100)
            .order_by("-started_at")
        )

        history = defaultdict(lambda: defaultdict(int))
        for log in logs:
            date = log.started_at.date()
            history[date][log.status] += 1

        return [
            {
                "date": date.isoformat(),
                "completed": data.get("COMPLETED", 0),
                "failed": data.get("FAILED", 0),
                "total": sum(data.values()),
            }
            for date, data in sorted(history.items())
        ]

    @app.get("/api/analytics/task-distribution", tags=["Analytics"])
    async def get_task_distribution():
        """Get task execution distribution."""
        logs = await models.Log.all().prefetch_related("job").limit(1000)

        distribution = defaultdict(lambda: {"total": 0, "completed": 0, "failed": 0})

        for log in logs:
            task_name = log.job.task_name
            distribution[task_name]["total"] += 1
            if log.status == Status.COMPLETED:
                distribution[task_name]["completed"] += 1
            elif log.status == Status.FAILED:
                distribution[task_name]["failed"] += 1

        return [
            {"task": task_name, **stats} for task_name, stats in distribution.items()
        ]

    @app.get("/api/analytics/error-rate", tags=["Analytics"])
    async def get_error_rate():
        """Get the current error rate."""
        total = await models.Log.all().count()
        failed = await models.Log.filter(status=Status.FAILED).count()

        if total == 0:
            return {"error_rate": 0}
        return {"error_rate": failed / total}

    @app.get("/api/tasks", response_model=List[Task], tags=["Tasks"])
    async def list_tasks():
        return list(get_registered_tasks().values())

    @app.get("/api/tasks/{task_name}", response_model=Task, tags=["Tasks"])
    async def get_task(task_name: str):
        task = get_registered_task(task_name)
        return task

    @app.post("/api/tasks/{task_name}/run", tags=["Tasks"])
    async def run_task(task_name: str, params: Dict[str, Any]):
        """Run a task immediately without scheduling."""
        try:
            task = get_registered_task(task_name)
            result = await task.func(**params)
            # Create a log entry for the manual run
            log = await models.Log.create(
                job=None,
                status=Status.COMPLETED,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                result=result,
            )
            return {"status": "success", "result": result, "log_id": log.id}
        except Exception as e:
            # Log the failure
            await models.Log.create(
                job=None,
                status=Status.FAILED,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                error=str(e),
            )
            raise HTTPException(400, str(e)) from e

    @app.get("/api/jobs", response_model=List[Job], tags=["Jobs"])
    async def list_jobs(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        task: Optional[str] = None,
    ):
        """List jobs with pagination and optional task filter."""
        query = models.Job.all()
        if task:
            query = query.filter(task_name=task)

        jobs = await query.offset(offset).limit(limit)
        return [await job.to_schema() for job in jobs]

    @app.get("/api/jobs/{job_id}", response_model=Job, tags=["Jobs"])
    async def get_job(job_id: str):
        """Get a specific job by ID."""
        job = await models.Job.get_or_none(id=job_id)
        if not job:
            raise HTTPException(404, f"Job #{job_id} not found")
        return await job.to_schema()

    @app.post("/api/jobs", response_model=Job, tags=["Jobs"])
    async def create_job(job_create: JobCreate):
        """Create a new job."""
        try:
            job = await models.Job.create(**job_create.dict())
            return await job.to_schema()
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.put("/api/jobs/{job_id}", response_model=Job, tags=["Jobs"])
    async def update_job(job_id: str, job_update: JobUpdate):
        """Update an existing job."""
        job = await models.Job.get_or_none(id=job_id)
        if not job:
            raise HTTPException(404, f"Job #{job_id} not found")

        try:
            await models.Job.filter(id=job_id).update(
                **job_update.dict(exclude_unset=True)
            )
            updated_job = await models.Job.get(id=job_id)
            return await updated_job.to_schema()
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/jobs/{job_id}", tags=["Jobs"])
    async def delete_job(job_id: str):
        """Delete a job and its related data."""
        job = await models.Job.get_or_none(id=job_id)
        if not job:
            raise HTTPException(404, f"Job #{job_id} not found")

        # Delete related logs and the job using model managers
        await models.Log.filter(job_id=job_id).delete()
        await models.Job.filter(id=job_id).delete()
        return {"status": "success"}

    @app.get("/api/logs", response_model=PaginatedResponse[Log], tags=["Logs"])
    async def list_logs(
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        job_id: Optional[int] = None,
        status: Optional[Status] = None,
    ):
        """List execution logs with pagination and filtering."""
        query = models.Log.all().prefetch_related("job")

        if job_id:
            query = query.filter(job_id=job_id)
        if status:
            query = query.filter(status=status)

        total = await query.count()
        logs = await query.offset(offset).limit(limit).order_by("-started_at")

        return PaginatedResponse(
            items=[await log.to_schema() for log in logs],
            total=total,
            offset=offset,
            limit=limit,
        )

    # Error handler
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error("API error: %s", str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "type": type(exc).__name__,
            },
        )

    return app
