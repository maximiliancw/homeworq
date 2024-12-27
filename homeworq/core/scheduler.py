
from typing import List, Dict
from asyncio import create_task, sleep

class Scheduler:
    def __init__(self):
        self.tasks: Dict[str, List] = {}

    def register_task(self, name: str, task):
        if name not in self.tasks:
            self.tasks[name] = []
        self.tasks[name].append(task)

    async def start(self):
        while True:
            for task_list in self.tasks.values():
                for task in task_list:
                    create_task(task.run())
            await sleep(1)  # Schedule every second for simplicity
