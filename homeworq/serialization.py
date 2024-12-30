"""
JSON serialization utilities for homeworq.

This module provides custom JSON encoding functionality to handle all Python-native datatypes
including datetime, timedelta, sets, and other common types that aren't JSON-serializable by default.
"""

import datetime
import decimal
import json
import uuid
from enum import Enum
from pathlib import Path
from typing import Any


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles common Python types."""

    def default(self, obj: Any) -> Any:
        # Handle datetime objects
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()

        # Handle time objects
        if isinstance(obj, datetime.time):
            return obj.isoformat()

        # Handle timedelta objects
        if isinstance(obj, datetime.timedelta):
            return str(obj)

        # Handle sets
        if isinstance(obj, set):
            return list(obj)

        # Handle Decimal
        if isinstance(obj, decimal.Decimal):
            return str(obj)

        # Handle bytes
        if isinstance(obj, bytes):
            return obj.decode("utf-8")

        # Handle Path objects
        if isinstance(obj, Path):
            return str(obj)

        # Handle UUIDs
        if isinstance(obj, uuid.UUID):
            return str(obj)

        # Handle Enums
        if isinstance(obj, Enum):
            return obj.value

        # Handle objects with a custom serialization method
        if hasattr(obj, "to_json"):
            return obj.to_json()

        # Handle objects with __dict__ attribute
        if hasattr(obj, "__dict__"):
            return obj.__dict__

        # Let the base class handle anything else
        return super().default(obj)


def serialize(obj: Any) -> str:
    """
    Serialize any Python object to a JSON string.

    Args:
        obj: Any Python object to serialize

    Returns:
        str: JSON-encoded string representation

    Example:
        >>> data = {'timestamp': datetime.datetime.now(), 'values': {1, 2, 3}}
        >>> json_str = serialize(data)
    """
    return json.dumps(obj, cls=JSONEncoder)


def deserialize(json_str: str) -> Any:
    """
    Deserialize a JSON string back into Python objects.

    Args:
        json_str: JSON-encoded string

    Returns:
        Any: Decoded Python object

    Example:
        >>> json_str = '{"timestamp": "2024-01-01T00:00:00", "values": [1, 2, 3]}'
        >>> data = deserialize(json_str)
    """
    return json.loads(json_str)
