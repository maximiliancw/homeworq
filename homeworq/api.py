import logging
import os
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from .core import Homeworq
from .models import Job, JobExecution, Task

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
        return app.state.hq.tasks

    # Get task details
    @app.get("/api/tasks/{task_name}", response_model=Task)
    async def get_task(task_name: str):
        """Get details for a specific task"""
        tasks = app.state.hq.tasks
        if task_name not in tasks:
            raise HTTPException(status_code=404, detail=f"Task {task_name} not found")
        return tasks[task_name]

    # List all jobs
    @app.get("/api/jobs", response_model=Dict[str, Job])
    async def list_jobs():
        """List all configured jobs"""
        return app.state.hq.jobs

    # Get job details
    @app.get("/api/jobs/{job_name}", response_model=Job)
    async def get_job(job_name: str):
        """Get details for a specific job"""
        jobs = app.state.hq.jobs
        if job_name not in jobs:
            raise HTTPException(status_code=404, detail=f"Job {job_name} not found")
        return jobs[job_name]

    # Get job execution history
    @app.get("/api/jobs/{job_name}/history", response_model=List[JobExecution])
    async def get_job_history(job_name: str, limit: int = 100):
        """Get execution history for a specific job"""
        if job_name not in app.state.hq.jobs:
            raise HTTPException(status_code=404, detail=f"Job {job_name} not found")

        history = await app.state.hq.db.get_job_history(job_name, limit=limit)
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
