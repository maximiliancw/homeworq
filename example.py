import asyncio
import typing
import urllib.request
from typing import Any, Dict

from homeworq import Homeworq, models, register_task


@register_task(title="Website Health Check")
async def ping(url: str) -> Dict[str, Any]:
    """
    Ping a website and return its status.

    Args:
        url: The URL to check

    Returns:
        Dict containing status code and headers
    """
    with urllib.request.urlopen(url) as response:
        return {
            "status": response.status,
            "headers": dict(response.headers),
        }


@register_task(title="Data Processing")
async def process_data(
    input_path: str,
    batch_size: int = 100,
) -> Dict[str, typing.Any]:
    """
    Process data in batches.

    Args:
        input_path: Path to input data
        batch_size: Size of each processing batch

    Returns:
        Dict containing processing statistics
    """
    asyncio.sleep(5)  # Simulate processing time
    return {
        "processed_records": batch_size,
        "input_path": input_path,
    }


if __name__ == "__main__":
    # Define settings
    settings = models.Settings(
        api_on=True,  # Enable the web interface
        api_host="localhost",  # Host for the web interface
        api_port=8000,  # Port for the web interface
        debug=True,  # Enable debug logging
    )

    # Optional: Define default jobs which will be loaded on startup
    default_jobs = [
        # Job 1: Health check every hour
        models.JobCreate(
            task="ping",
            params={"url": "https://example.com"},
            schedule=models.JobSchedule(
                interval=1,
                unit=models.TimeUnit.HOURS,
            ),
            options=models.JobOptions(
                timeout=30,  # 30 second timeout
                max_retries=3,  # Retry up to 3 times
            ),
        ),
        # Job 2: Data processing daily at 2 AM
        models.JobCreate(
            task="process_data",
            params={
                "input_path": "/data/daily_import",
                "batch_size": 1000,
            },
            schedule=models.JobSchedule(
                interval=1,
                unit=models.TimeUnit.DAYS,
                at="02:00",  # Run at 2 AM
            ),
            options=models.JobOptions(
                timeout=3600,  # 1 hour timeout
                max_retries=2,  # Retry up to 2 times
            ),
        ),
    ]

    # Let's go! 🚀
    Homeworq.run(settings=settings, defaults=default_jobs)
