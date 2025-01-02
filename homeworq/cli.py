from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .core import HQ
from .schemas import Settings

# Initialize Typer app
app = typer.Typer(
    name="hq",
    help="Homeworq: A powerful task scheduling system",
    add_completion=False,
)

# Initialize Rich console
console = Console()

EXAMPLE_CONFIG = """from homeworq import Homeworq, Settings, JobCreate, register_task
from homeworq.models import JobSchedule, TimeUnit, JobOptions
from typing import Dict, Any
import urllib.request

@register_task("Ping URL")
async def ping(url: str) -> Dict[str, Any]:
    \"\"\"Ping a URL and return its status\"\"\"
    with urllib.request.urlopen(url) as req:
        return {
            "status": req.status,
            "headers": dict(req.headers),
        }

# Define default jobs
jobs = [
    JobCreate(
        task="ping",
        params={"url": "https://example.com"},
        schedule=JobSchedule(
            interval=1,
            unit=TimeUnit.DAYS,
            at="08:00"
        )
    ),
]

# Define your settings
settings = Settings(
    api_on=True,
    api_host="localhost",
    api_port=8000,
    debug=True,
)

if __name__ == "__main__":
    # Run Homeworq with your configuration
    Homeworq.run(settings=settings, defaults=jobs)
"""


def create_example_config(config_path: Path) -> None:
    """Create example configuration file"""
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(EXAMPLE_CONFIG)


@app.command()
def init(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Path where the configuration should be initialized",
    )
) -> None:
    """Initialize a new Homeworq workspace"""
    try:
        # Create workspace directory if it doesn't exist
        workspace_path = Path(path).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create example configuration
        config_path = workspace_path / "config.py"
        if config_path.exists():
            if not typer.confirm(
                "Configuration file already exists. Do you want to overwrite it?"
            ):
                raise typer.Abort()

        create_example_config(config_path)

        # Show success message
        console.print()
        console.print(
            Panel.fit(
                "[green]✓[/green] Homeworq workspace initialized successfully!\n\n"
                f"[bold]Configuration file created:[/bold] {config_path}\n\n"
                "To get started:\n"
                f"1. Edit the configuration file: {config_path}\n"
                "2. Run Homeworq: [bold]hq run --serve[/bold]",
                title="Homeworq Initialization",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to initialize workspace: {str(e)}")
        raise typer.Exit(1)


@app.command()
def run(
    config: str = typer.Option(
        "config.py",
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    server: bool = typer.Option(
        False,
        "--server",
        "-s",
        help="Start the web server",
    ),
) -> None:
    """Start Homeworq scheduler"""
    try:
        # Get absolute path to config
        config_path = Path(config).resolve()
        if not config_path.exists():
            console.print(
                f"[red]Error:[/red] Configuration file not found: {config_path}"
            )
            raise typer.Exit(1)

        # Add config directory to Python path
        import sys

        sys.path.append(str(config_path.parent))

        # Import configuration
        import importlib.util

        spec = importlib.util.spec_from_file_location("config", config_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load config from {config_path}")

        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)

        # Extract settings and jobs
        settings = getattr(config_module, "settings", Settings())
        jobs = getattr(config_module, "jobs", [])

        # Override API setting if server flag is provided
        if server:
            settings.api_on = True

        # Show startup message
        console.print()
        console.print(
            Panel.fit(
                "[green]✓[/green] Starting Homeworq...\n\n"
                f"[bold]Configuration:[/bold] {config_path}\n"
                f"[bold]Web Server:[/bold] {'Enabled' if settings.api_on else 'Disabled'}\n"
                f"[bold]Debug Mode:[/bold] {'Enabled' if settings.debug else 'Disabled'}\n"
                f"[bold]Jobs:[/bold] {len(jobs)}",
                title="Homeworq Startup",
                border_style="green",
            )
        )

        # Run Homeworq
        HQ.run(settings=settings, defaults=jobs)

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)
