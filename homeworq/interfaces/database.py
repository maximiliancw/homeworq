
class DatabaseAdapter:
    async def save_task(self, task_data: dict):
        """Saves task data to the database."""
        raise NotImplementedError

    async def fetch_task(self, task_id: str) -> dict:
        """Fetches a task by its ID."""
        raise NotImplementedError

    async def update_task_status(self, task_id: str, status: str):
        """Updates the status of a task."""
        raise NotImplementedError
