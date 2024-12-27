
from typing import Callable, Optional

class Task:
    def __init__(self, func: Callable, schedule: Optional[str] = None):
        self.func = func
        self.schedule = schedule

    async def run(self, *args, **kwargs):
        return await self.func(*args, **kwargs)

def task(schedule: Optional[str] = None):
    def decorator(func: Callable):
        return Task(func=func, schedule=schedule)
    return decorator
