import logging
import os
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core import Homeworq
from .models import Job, JobExecution, Task
from .tasks import REGISTRY

logger = logging.getLogger(__name__)


async def create_api(hq: Homeworq) -> FastAPI:
    """
    Create a FastAPI application for a running Homeworq instance.
    Provides read-only endpoints for monitoring and inspecting the task scheduler.

    Args:
        hq: Running Homeworq instance to attach to the API

    Returns:
        FastAPI: Configured FastAPI instance
    """
    # Create FastAPI application
    app = FastAPI(
        title="Homeworq",
        description="A read-only API for the Homeworq task scheduler",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Store Homeworq instance
    app.state.hq = hq

    # Add CORS middleware with restrictive settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Consider restricting this in production
        allow_credentials=False,  # No credentials needed for read-only API
        allow_methods=["GET"],  # Only allow GET requests
        allow_headers=["*"],
    )

    app.mount(
        "/static",
        app=StaticFiles(
            directory=os.path.join(
                os.path.dirname(__file__),
                "static",
            )
        ),
        name="static",
    )

    templates = Jinja2Templates(
        directory=os.path.join(
            os.path.dirname(__file__),
            "templates",
        )
    )

    @app.get("/")
    async def view_dashboard(request: Request):
        """Application dashboard"""
        return templates.TemplateResponse("dashboard.html", {"request": request})

    @app.get("/tasks")
    async def view_tasks(request: Request):
        """Application dashboard"""
        return templates.TemplateResponse("tasks.html", {"request": request})

    @app.get("/jobs")
    async def view_jobs(request: Request):
        """Application dashboard"""
        return templates.TemplateResponse("jobs.html", {"request": request})

    @app.get("/results")
    async def view_results(request: Request):
        """Application dashboard"""
        return templates.TemplateResponse("results.html", {"request": request})

    # Health check endpoint
    @app.get("/api/health")
    async def health_check():
        """System health check endpoint"""
        return {
            "status": "healthy" if app.state.hq.live else "unhealthy",
        }

    # List all tasks
    @app.get("/api/tasks", response_model=Dict[str, Task])
    async def list_tasks():
        """List all available tasks and their descriptions"""
        return {
            k: {"name": k, "title": v.title, "description": v.description}
            for k, v in REGISTRY.items()
        }

    # List all results
    @app.get("/api/results", response_model=List[JobExecution])
    async def list_results():
        """List all available job executions and their results"""
        return [result for job in app.state.hq.jobs for result in job.history]

    # Get task details
    @app.get("/api/tasks/{task_name}", response_model=Task)
    async def get_task(task_name: str):
        """Get details for a specific task"""
        if task_name not in REGISTRY:
            raise HTTPException(status_code=404, detail=f"Task {task_name} not found")

        task = REGISTRY[task_name]
        return {
            "name": task_name,
            "title": task.title,
            "description": task.description,
        }

    # List all jobs
    @app.get("/api/jobs", response_model=List[Job])
    async def list_jobs():
        """List all configured jobs"""
        return app.state.hq.jobs

    # Get job details
    @app.get("/api/jobs/{job_uid}", response_model=Job)
    async def get_job(job_uid: str):
        """Get details for a specific job"""
        job = next((j for j in app.state.hq.jobs if j.uid == job_uid), None)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job #{job_uid} not found")
        return job

    # Get job execution history
    @app.get("/api/jobs/{job_uid}/history", response_model=List[JobExecution])
    async def get_job_history(job_uid: str, limit: int = 100):
        """Get execution history for a specific job"""
        job = next((j for j in app.state.hq.jobs if j.uid == job_uid), None)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job #{job_uid} not found")

        history = await app.state.hq.get_job_history(job_uid, limit=limit)
        return history

    # Error handler for common exceptions
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected errors gracefully"""
        logger.error(f"Unexpected error in API: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": type(exc).__name__,
            },
        )

    return app
