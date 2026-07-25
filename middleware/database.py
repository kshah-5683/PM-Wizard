import os
from typing import Optional
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

class DatabaseManager:
    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or os.getenv("DATABASE_URL")
        self.pool = None
        self.checkpointer = None
        self.pgvector_enabled = False

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
                    
                    # Attempt pgvector extension
                    try:
                        await cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                        self.pgvector_enabled = True
                    except Exception as e:
                        print(f"[Database] pgvector extension not available/enabled: {e}. Falling back to text-based embeddings & ILIKE search.")
                        self.pgvector_enabled = False
                        
                    # Create historical_tickets table
                    from middleware.config import EMBEDDING_DIMENSION
                    embedding_type = f"vector({EMBEDDING_DIMENSION})" if self.pgvector_enabled else "TEXT"
                    await cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS historical_tickets (
                            id SERIAL PRIMARY KEY,
                            ticket_key VARCHAR(50) UNIQUE,
                            title TEXT,
                            description TEXT,
                            estimation INTEGER,
                            priority VARCHAR(20),
                            embedding {embedding_type},
                            sprint_plan_id TEXT,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    
                    try:
                        await cur.execute("ALTER TABLE historical_tickets ADD COLUMN IF NOT EXISTS sprint_plan_id TEXT;")
                    except Exception as e:
                        print(f"[Database] Failed to alter historical_tickets: {e}")
                        
                    # Create ticket_change_requests table
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS ticket_change_requests (
                            id SERIAL PRIMARY KEY,
                            thread_id TEXT NOT NULL REFERENCES project_history(thread_id) ON DELETE CASCADE,
                            ticket_key VARCHAR(50) NOT NULL,
                            developer_name TEXT NOT NULL,
                            original_points INTEGER,
                            original_description TEXT,
                            requested_points INTEGER,
                            requested_description TEXT,
                            status TEXT DEFAULT 'PENDING',
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_change_requests_thread ON ticket_change_requests(thread_id);
                    """)
            
            # Seed historical tickets
            try:
                from middleware.rag import seed_historical_tickets
                await seed_historical_tickets(self)
            except Exception as e:
                print(f"[Database] Error seeding historical tickets: {e}")

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

    async def create_change_request(
        self, thread_id: str, ticket_key: str, developer_name: str,
        original_points: Optional[int], original_description: Optional[str],
        requested_points: Optional[int], requested_description: Optional[str]
    ) -> Optional[int]:
        if not self.pool:
            return None
        query = """
            INSERT INTO ticket_change_requests (
                thread_id, ticket_key, developer_name,
                original_points, original_description,
                requested_points, requested_description
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    query,
                    (
                        thread_id, ticket_key, developer_name,
                        original_points, original_description,
                        requested_points, requested_description
                    )
                )
                res = await cur.fetchone()
                return res[0] if res else None

    async def resolve_change_request(self, request_id: int, status: str):
        if not self.pool:
            return
        query = """
            UPDATE ticket_change_requests
            SET status = %s, updated_at = NOW()
            WHERE id = %s;
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (status, request_id))

    async def get_change_requests(self, thread_id: str):
        if not self.pool:
            return []
        query = """
            SELECT * FROM ticket_change_requests
            WHERE thread_id = %s
            ORDER BY created_at ASC;
        """
        async with self.get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (thread_id,))
                return await cur.fetchall()

# Global database manager instance
db_manager = DatabaseManager()
