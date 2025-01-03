import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def get_auth_credentials() -> tuple[str, str]:
    """Get authentication credentials from environment variables."""
    username = os.getenv("HQ_ADMIN_USERNAME", "admin")
    password = os.getenv("HQ_ADMIN_PASSWORD", "admin")
    return username, password


def authenticate(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)]
) -> bool:
    """Verify admin authentication credentials"""
    correct_username, correct_password = get_auth_credentials()

    current_username_bytes = credentials.username.encode("utf8")
    current_password_bytes = credentials.password.encode("utf8")
    correct_username_bytes = correct_username.encode("utf8")
    correct_password_bytes = correct_password.encode("utf8")

    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True
