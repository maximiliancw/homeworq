
from typing import Callable

class MessageQueueAdapter:
    async def publish(self, topic: str, message: dict):
        """Publishes a message to the specified topic."""
        raise NotImplementedError

    async def subscribe(self, topic: str, callback: Callable):
        """Subscribes to a topic and executes the callback upon receiving messages."""
        raise NotImplementedError

    async def acknowledge(self, message_id: str):
        """Acknowledges processing of a specific message."""
        raise NotImplementedError
