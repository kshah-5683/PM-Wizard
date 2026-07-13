import os
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

class DatabaseManager:
    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or os.getenv("DATABASE_URL")
        self.pool = None
        self.checkpointer = None

    async def connect(self):
        if not self.connection_string:
            raise ValueError("DATABASE_URL environment variable is not set. Please configure it in your .env file.")
        
        if not self.pool:
            # We initialize psycopg's AsyncConnectionPool
            self.pool = AsyncConnectionPool(
                conninfo=self.connection_string,
                open=False,
                min_size=1,
                max_size=10
            )
            await self.pool.open()
            self.checkpointer = AsyncPostgresSaver(self.pool)
            # Automatically set up standard LangGraph checkpointer schemas
            await self.checkpointer.setup()
            # Automatically create project_history table if it doesn't exist
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS project_history (
                            thread_id TEXT PRIMARY KEY,
                            title TEXT,
                            source_document TEXT,
                            status TEXT,
                            total_epics INTEGER DEFAULT 0,
                            total_stories INTEGER DEFAULT 0,
                            total_story_points INTEGER DEFAULT 0,
                            ai_summary TEXT,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                    """)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
            self.checkpointer = None

    @asynccontextmanager
    async def get_connection(self):
        if not self.pool:
            await self.connect()
        async with self.pool.connection() as conn:
            yield conn

    async def save_project_history(self, thread_id: str, title: str, source_doc: str, status: str, metrics: dict, ai_summary: str):
        query = """
            INSERT INTO project_history (
                thread_id, title, source_document, status, total_epics, total_stories, total_story_points, ai_summary
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (thread_id) DO UPDATE SET
                status = EXCLUDED.status,
                total_epics = EXCLUDED.total_epics,
                total_stories = EXCLUDED.total_stories,
                total_story_points = EXCLUDED.total_story_points,
                ai_summary = EXCLUDED.ai_summary,
                updated_at = NOW();
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    query,
                    (
                        thread_id,
                        title,
                        source_doc,
                        status,
                        metrics.get("total_epics", 0),
                        metrics.get("total_stories", 0),
                        metrics.get("total_story_points", 0),
                        ai_summary
                    )
                )

    async def update_project_status(self, thread_id: str, status: str):
        query = """
            UPDATE project_history
            SET status = %s, updated_at = NOW()
            WHERE thread_id = %s;
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (status, thread_id))

    async def get_project_history(self, thread_id: str):
        query = """
            SELECT * FROM project_history WHERE thread_id = %s;
        """
        async with self.get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (thread_id,))
                return await cur.fetchone()

    async def list_project_history(self, limit: int = 50):
        query = """
            SELECT * FROM project_history ORDER BY updated_at DESC LIMIT %s;
        """
        async with self.get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                return await cur.fetchall()

# Global database manager instance
db_manager = DatabaseManager()
