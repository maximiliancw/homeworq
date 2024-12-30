# Homeworq 🏠

A powerful, async-first task scheduling system with an integrated REST API and web interface. Built with Python 3.13+.

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features ✨

- **Task Scheduling**: Flexible scheduling with interval and time-based triggers
- **REST API & Web Interface**: Built-in FastAPI server for task/job management
- **Result Storage**: SQLite-based storage for job execution history
- **Retry Logic**: Configurable retry attempts with exponential backoff
- **Async First**: Built on Python's asyncio for maximum performance
- **Web Dashboard**: Monitor jobs, tasks, and execution results
- **Developer Friendly**: Simple API for task registration and job creation

## Installation 🚀

```bash
pip install homeworq
```

## Quick Start 🎯

Here's a minimal example to get you started:

```python
from homeworq import Homeworq, models, register_task

# Define a task
@register_task(title="Website Health Check")
async def ping(url: str):
    """Ping a website and return its status."""
    import urllib.request
    with urllib.request.urlopen(url) as response:
        return {
            "status": response.status,
            "headers": dict(response.headers)
        }

# Configure settings
settings = models.Settings(
    api_on=True,  # Enable web interface
    api_host="localhost",
    api_port=8000
)

# Define a job
jobs = [
    models.JobCreate(
        task="ping",
        params={"url": "https://example.com"},
        schedule=models.JobSchedule(
            interval=1,
            unit=models.TimeUnit.HOURS
        ),
        options=models.JobOptions(
            timeout=30,
            max_retries=3
        )
    )
]

# Start the scheduler
if __name__ == "__main__":
    Homeworq.run(settings=settings, defaults=jobs)
```

## Task Scheduling 📅

Homeworq supports two types of scheduling:

### Interval-based Scheduling

```python
schedule = models.JobSchedule(
    interval=1,  # Run every...
    unit=models.TimeUnit.HOURS,  # hour
    at="14:30"  # Optional: Run at specific time
)
```

Available time units:

- `SECONDS`
- `MINUTES`
- `HOURS`
- `DAYS`
- `WEEKS`
- `MONTHS`
- `YEARS`

### Cron-like Scheduling

```python
schedule = "*/15 * * * *"  # Run every 15 minutes
```

## Job Configuration ⚙️

Jobs can be configured with various options:

```python
options = models.JobOptions(
    timeout=300,  # 5 minute timeout
    max_retries=3,  # Retry up to 3 times
    start_date=datetime(2024, 1, 1),  # Start date
    end_date=datetime(2024, 12, 31),  # End date
    dependencies=[  # Job dependencies
        models.JobDependency(
            job_name="other_job",
            required_status=models.Status.COMPLETED,
            within_hours=24
        )
    ]
)
```

## Web Interface 🌐

When enabled, Homeworq provides a web interface at `http://localhost:8000` with:

- Dashboard overview
- Task registry
- Job management
- Execution history
- Health monitoring

## API Endpoints 🛣️

The REST API provides these endpoints:

- `GET /api/health` - System health check
- `GET /api/tasks` - List all tasks
- `GET /api/tasks/{task_name}` - Get task details
- `GET /api/jobs` - List all jobs
- `GET /api/jobs/{job_name}` - Get job details
- `GET /api/jobs/{job_name}/history` - Get job execution history

## Development 🛠️

Setup your development environment:

```bash
# Clone the repository
git clone https://github.com/maximiliancw/homeworq.git
cd homeworq

# Create a virtual environment
uv install

# Run tests
pytest
```

## Contributing 🤝

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
