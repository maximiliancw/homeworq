import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core import Homeworq
from .schemas import Job, JobCreate, JobExecution, JobUpdate, PaginatedResponse
from .tasks import Task, get_registered_task, get_registered_tasks

logger = logging.getLogger(__name__)


async def create_api(hq: Homeworq) -> FastAPI:
    app = FastAPI(
        title="homeworq",
        description="Task scheduling and job management API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.state.hq = hq

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

    # UI Routes
    @app.get("/", include_in_schema=False)
    async def view_dashboard(request: Request):
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request},
        )

    @app.get("/tasks", include_in_schema=False)
    async def view_tasks(request: Request):
        return templates.TemplateResponse(
            "tasks/list.html",
            {"request": request},
        )

    @app.get("/jobs", include_in_schema=False)
    async def view_jobs(request: Request):
        return templates.TemplateResponse(
            "jobs/list.html",
            {"request": request},
        )

    @app.get("/results", include_in_schema=False)
    async def view_results(request: Request):
        return templates.TemplateResponse(
            "results/list.html",
            {"request": request},
        )

    # API Routes

    @app.get("/api/analytics/recent-activity", tags=["Analytics"])
    async def get_recent_activity():
        """Get recent job executions for the activity feed."""
        results = await app.state.hq.get_job_executions(skip=0, limit=10)
        return sorted(results, key=lambda x: x.started_at, reverse=True)

    @app.get("/api/analytics/upcoming-executions", tags=["Analytics"])
    async def get_upcoming_executions():
        """Get upcoming scheduled job executions."""
        jobs = await app.state.hq.list_jobs(offset=0, limit=100)
        now = datetime.now(timezone.utc)
        return [job for job in jobs if job.next_run and job.next_run > now]

    @app.get("/api/analytics/execution-history", tags=["Analytics"])
    async def get_execution_history():
        """Get execution history for charting."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)

        executions = await app.state.hq.get_job_executions(skip=0, limit=1000)

        filtered_executions = [
            e
            for e in executions
            if start_date <= e.started_at.replace(tzinfo=timezone.utc) <= end_date
        ]

        history = defaultdict(lambda: defaultdict(int))
        for exec in filtered_executions:
            date = exec.started_at.date()
            history[date][exec.status] += 1

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
        executions = await app.state.hq.get_job_executions(skip=0, limit=1000)

        distribution = defaultdict(lambda: {"total": 0, "completed": 0, "failed": 0})

        for exec in executions:
            task_name = exec.job.task.name
            distribution[task_name]["total"] += 1
            if exec.status == "COMPLETED":
                distribution[task_name]["completed"] += 1
            elif exec.status == "FAILED":
                distribution[task_name]["failed"] += 1

        return [
            {"task": task_name, **stats} for task_name, stats in distribution.items()
        ]

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
            return {"status": "success", "result": result}
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/jobs", response_model=Job, tags=["Jobs"])
    async def create_job(job_create: JobCreate):
        try:
            return await app.state.hq.create_job(job_create)
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/jobs", response_model=PaginatedResponse[Job], tags=["Jobs"])
    async def list_jobs(
        offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)
    ):
        jobs = await app.state.hq.list_jobs(offset=offset, limit=limit)
        total = len(jobs)  # TODO: Add count query
        return PaginatedResponse(
            items=jobs,
            total=total,
            offset=offset,
            limit=limit,
        )

    @app.get("/api/jobs/{job_id}", response_model=Job, tags=["Jobs"])
    async def get_job(job_id: int):
        job = await app.state.hq.get_job(job_id)
        if not job:
            raise HTTPException(404, f"Job #{job_id} not found")
        return job

    @app.put("/api/jobs/{job_id}", response_model=Job, tags=["Jobs"])
    async def update_job(job_id: int, job_update: JobUpdate):
        try:
            return await app.state.hq.update_job(job_id, job_update)
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/jobs/{job_id}", tags=["Jobs"])
    async def delete_job(job_id: int):
        await app.state.hq.delete_job(job_id)
        return {"status": "success"}

    # Results endpoints
    @app.get(
        "/api/results",
        response_model=PaginatedResponse[JobExecution],
        tags=["Results"],
    )
    async def list_results(
        offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)
    ):
        """List all job execution results with pagination."""
        results = await app.state.hq.get_job_executions(
            skip=offset,
            limit=limit,
        )
        total = len(results)  # TODO: Add count query
        return PaginatedResponse(
            items=results,
            total=total,
            offset=offset,
            limit=limit,
        )

    @app.get(
        "/api/results/{job_id}",
        response_model=PaginatedResponse[JobExecution],
        tags=["Results"],
    )
    async def get_job_results(
        job_id: int,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
    ):
        """Get paginated execution results for a specific job."""
        results = await app.state.hq.get_job_executions(
            job_id,
            skip=offset,
            limit=limit,
        )
        total = len(results)  # TODO: Add count query
        return PaginatedResponse(
            items=results,
            total=total,
            offset=offset,
            limit=limit,
        )

    @app.get("/api/health", tags=["Miscellaneous"])
    async def health_check():
        return {
            "timestamp": datetime.now().isoformat(),
            "healthy": app.state.hq.is_running,
        }

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
