from typing import Callable

REGISTRY = {}


def register_task(title: str = None):
    """
    Decorator to register a task with its metadata in the task registry.

    Args:
        title (str): A human-readable name for the task. Defaults to the function's __name__.
    """
    from .models import Task

    def decorator(func: Callable):
        REGISTRY[func.__name__] = Task(
            name=func.__name__,
            title=title or func.__name__,
            description=func.__doc__,
        )
        return func

    return decorator
