import uuid
from asyncio import create_task, sleep
from typing import Any, Dict, List

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket
from fastapi.responses import HTMLResponse

from .routes import router

app = FastAPI()


app.include_router(router)