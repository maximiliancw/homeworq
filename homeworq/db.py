import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

from .models import Job, JobExecution, JobOptions, JobSchedule, Status, Task, TimeUnit
from .serialization import JSONEncoder

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS job_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    task_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration REAL,
    params TEXT NOT NULL,
    result TEXT,
    error TEXT,
    retries INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_job_executions_job_uid ON job_executions(job_uid);
CREATE INDEX IF NOT EXISTS idx_job_executions_status ON job_executions(status);
CREATE INDEX IF NOT EXISTS idx_job_executions_started_at ON job_executions(started_at);
"""


class Database:
    """Async SQLite storage for job execution results"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Create database connection and initialize schema"""
        if self._connection is not None:
            return

        try:
            self._connection = await aiosqlite.connect(
                self.db_path, detect_types=1  # Parse timestamps
            )

            # Enable foreign keys and WAL mode for better concurrency
            await self._connection.execute("PRAGMA foreign_keys = ON")
            await self._connection.execute("PRAGMA journal_mode = WAL")

            # Create schema
            await self._connection.executescript(SCHEMA)
            await self._connection.commit()

            logger.info(f"Connected to database at {self.db_path}")

        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise

    async def disconnect(self):
        """Close database connection"""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("Disconnected from database")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def store_execution(self, execution: JobExecution) -> int:
        """Store a job execution result"""
        if self._connection is None:
            raise RuntimeError("Database not connected")

        try:
            query = """
                INSERT INTO job_executions (
                    job_uid,
                    task_name,
                    status,
                    started_at,
                    completed_at,
                    duration,
                    params,
                    result,
                    error,
                    retries
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            # Convert complex objects to JSON
            params_json = json.dumps(execution.job.params, cls=JSONEncoder)
            result_json = (
                json.dumps(execution.result, cls=JSONEncoder)
                if execution.result
                else None
            )

            values = (
                execution.job.uid,
                execution.job.task.name,
                execution.status.value,
                execution.started_at.isoformat(),
                execution.completed_at.isoformat() if execution.completed_at else None,
                execution.duration,
                params_json,
                result_json,
                execution.error,
                execution.retries,
            )

            async with self._connection.execute(query, values) as cursor:
                await self._connection.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to store execution result: {str(e)}")
            raise

    async def get_job_history(
        self,
        job_name: str,
        limit: int = 100,
        status: Optional[Status] = None,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get execution history for a job"""
        if self._connection is None:
            raise RuntimeError("Database not connected")

        try:
            query = """
                SELECT *
                FROM job_executions
                WHERE job_name = ?
            """
            params = [job_name]

            if status:
                query += " AND status = ?"
                params.append(status.value)

            if since:
                query += " AND started_at >= ?"
                params.append(since.isoformat())

            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)

            async with self._connection.execute(query, params) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()

                results = []
                for row in rows:
                    result = dict(zip(columns, row))

                    # Parse JSON fields
                    if result.get("params"):
                        result["params"] = json.loads(
                            result["params"],
                            cls=JSONEncoder,
                        )
                    if result.get("result"):
                        result["result"] = json.loads(
                            result["result"],
                            cls=JSONEncoder,
                        )

                    # Parse timestamps
                    for field in ["started_at", "completed_at", "created_at"]:
                        if result.get(field):
                            field = result[field]
                            result[field] = datetime.fromisoformat(field)

                    results.append(result)

                return results

        except Exception as e:
            logger.error(f"Failed to get job history: {str(e)}")
            raise

    async def get_last_execution(self, job_uid: str) -> Optional[JobExecution]:
        """Get the last execution of a job"""
        if self._connection is None:
            raise RuntimeError("Database not connected")

        try:
            query = """
                SELECT *
                FROM job_executions
                WHERE job_uid = ?
                ORDER BY id DESC
                LIMIT 1
            """

            async with self._connection.execute(query, [job_uid]) as cursor:
                row = await cursor.fetchone()

                if not row:
                    return None

                columns = [col[0] for col in cursor.description]
                result = dict(zip(columns, row))

                # Parse JSON fields
                if result.get("params"):
                    result["params"] = json.loads(result["params"], cls=JSONEncoder)
                if result.get("result"):
                    result["result"] = json.loads(result["result"], cls=JSONEncoder)

                # Parse timestamps
                for field in ["started_at", "completed_at", "created_at"]:
                    if result.get(field):
                        result[field] = datetime.fromisoformat(result[field])

                return JobExecution(
                    id=result["id"],
                    job=Job(
                        uid=result["job_uid"],
                        task=Task(name=result["task_name"]),
                        params=result["params"],
                        options=JobOptions(),
                        schedule=JobSchedule(interval=1, unit=TimeUnit.MINUTES),
                    ),
                    status=Status(result["status"]),
                    started_at=result["started_at"],
                    completed_at=result.get("completed_at"),
                    duration=result.get("duration"),
                    result=result.get("result"),
                    error=result.get("error"),
                    retries=result["retries"],
                )
        except Exception as e:
            logger.error(f"Failed to get last execution: {str(e)}")
            raise

    async def get_recent_failures(
        self, limit: int = 100, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get recent failed job executions"""
        if self._connection is None:
            raise RuntimeError("Database not connected")

        try:
            query = """
                SELECT *
                FROM job_executions
                WHERE status = ?
            """
            params = [Status.FAILED.value]

            if since:
                query += " AND started_at >= ?"
                params.append(since.isoformat())

            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)

            async with self._connection.execute(query, params) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()

                results = []
                for row in rows:
                    result = dict(zip(columns, row))

                    # Parse JSON fields
                    if result.get("params"):
                        result["params"] = json.loads(result["params"], cls=JSONEncoder)
                    if result.get("result"):
                        result["result"] = json.loads(result["result"], cls=JSONEncoder)

                    # Parse timestamps
                    for field in ["started_at", "completed_at", "created_at"]:
                        if result.get(field):
                            result[field] = datetime.fromisoformat(result[field])

                    results.append(result)

                return results

        except Exception as e:
            logger.error(f"Failed to get recent failures: {str(e)}")
            raise

    async def cleanup_old_records(self, days: int = 30):
        """Delete old execution records"""
        if self._connection is None:
            raise RuntimeError("Database not connected")

        try:
            query = """
                DELETE FROM job_executions
                WHERE created_at < datetime('now', ?)
            """

            async with self._connection.execute(query, [f"-{days} days"]):
                await self._connection.commit()

        except Exception as e:
            logger.error(f"Failed to cleanup old records: {str(e)}")
            raise
