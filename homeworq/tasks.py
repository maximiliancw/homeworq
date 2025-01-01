from functools import lru_cache
from inspect import iscoroutinefunction
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field


class Task(BaseModel):
    name: str
    title: str
    description: Optional[str] = None
    func: Optional[Callable] = Field(None, exclude=True)


_REGISTRY: Dict[str, Task] = {}


def register_task(title: str = None):
    """Decorator to register an async task with metadata."""

    def decorator(func: Callable):
        if not iscoroutinefunction(func):
            raise ValueError(f"Task {func.__name__} must be an async function")

        _REGISTRY[func.__name__] = Task(
            name=func.__name__,
            title=title or func.__name__,
            description=func.__doc__,
            func=func,
        )
        return func

    return decorator


@lru_cache
def get_registered_tasks() -> Dict[str, Task]:
    return _REGISTRY


def get_registered_task(name: str) -> Task:
    if name not in _REGISTRY:
        raise KeyError(f"Task {name} not found in registry")
    return _REGISTRY[name]


async def execute_task(task_name: str, params: Dict[str, Any]) -> Any:
    """Execute a registered task with parameters."""
    task = get_registered_task(task_name)
    return await task.func(**params)
