# homeworq 🏠

A powerful, async-first task scheduling system with an integrated JSON API and web interface. Built with Python 3.13+.

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Features ✨

- **Task Scheduling**

  - Super simple task and schedule definition
  - Interval-based scheduling with flexible time units
  - Optional time-of-day execution control

- **Async Engine**

  - Built on Python's asyncio for high performance
  - Automatic retry with exponential backoff
  - Configurable timeouts
  - Concurrent job execution

- **JSON API**

  - Built on the popular [FastAPI](https://fastapi.tiangolo.com) framework
  - Extensive and interactive API documentation using the OpenAPI standard

- **Web Interface**

  - Real-time dashboard
  - Job and task overview
  - Execution history viewer
  - System health monitoring

- **Result Storage**
  - SQLite-based execution history
  - Efficient WAL mode for better concurrency
  - Automatic schema management

## Requirements 📋

- Python 3.13 or higher
- SQLite 3.35+ (included with Python)
- Great ideas to give your machine some _homeworq_ 🤓

## Installation 🚀

You can install `homeworq` via PyPI using your favorite package manager.

For example:

```bash
pip install homeworq
```

## Quick Start 🎯

### 1. Setup Workspace

```bash
# Create a new project directory
mkdir my-homeworq && cd my-homeworq

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows

# Install homeworq
uv pip install homeworq

# Initialize workspace
hq init
```

### 2. Configure Workspace

The `hq init` command will – among other things – create a sample file `config.py` in your workspace to get you started quickly.

```python
from homeworq import Homeworq, models, register_task
from typing import Dict, Any

# Define a task
@register_task(title="Website Health Check")
async def ping(url: str) -> Dict[str, Any]:
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
    api_port=8000,
    debug=True
)

# Define default jobs
jobs = [
    models.JobCreate(
        task="ping",
        params={"url": "https://example.com"},
        schedule=models.JobSchedule(
            interval=1,
            unit=models.TimeUnit.DAYS,
            at="14:30"
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

### 3. Start App

- Without web service: `hq run`

- With web service: `hq run --server`

## Usage

### Task Configuration 📝

Tasks are registered using the `@register_task` decorator:

```python
@register_task(title="Data Processing")
async def process_data(input_path: str, batch_size: int = 1000) -> Dict[str, Any]:
    """Process data in batches."""
    # Task implementation
    ...
```

The `title` can be arbitrary, since it's sole purpose to be displayed in the UI.

### Job Configuration ⚙️

#### Scheduling Options

Available time units:

- `SECONDS`
- `MINUTES`
- `HOURS`
- `DAYS`
- `WEEKS`
- `MONTHS`
- `YEARS`

Time-based execution is supported for daily and weekly intervals:

```python
schedule = models.JobSchedule(
    interval=1,
    unit=models.TimeUnit.DAYS,
    at="14:30"  # Run at 2:30 PM
)
```

#### Job Options

```python
options = models.JobOptions(
    timeout=300,  # 5 minute timeout
    max_retries=3,  # Retry up to 3 times
    start_date=datetime(2024, 1, 1),  # Start date
    end_date=datetime(2024, 12, 31),  # End date
)
```

### Web Interface 🌐

When enabled via the `api_on=True` setting, Homeworq provides a web interface at `http://localhost:8000` with:

- Dashboard overview
- Task registry browser
- Job management interface
- Execution history viewer

The application is based on FastAPI as well as Alpine.js, and runs using `uvicorn`. You can configure the ASGI application using the following setting parameters:

```python
settings = Settings(
    api_on=True,
    api_host="example.com"
    api_port="3000"
)
```

### API Endpoints 🤖

The JSON API provides these endpoints:

- `GET /api/health` - System health check
- `GET /api/tasks` - List all tasks
- `GET /api/tasks/{task_name}` - Get task details
- `GET /api/jobs` - List all jobs
- `GET /api/jobs/{job_uid}` - Get job details
- `GET /api/jobs/{job_uid}/history` - Get job execution history
- `GET /api/results` - Get all job executions / results

## Development 🛠️

```bash
# Clone the repository
git clone https://github.com/maximiliancw/homeworq.git
cd homeworq

# Install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests
pytest
```

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
