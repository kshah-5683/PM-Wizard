import os
import datetime
from typing import Optional, List
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from cryptography.fernet import Fernet

class DatabaseManager:
    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or os.getenv("DATABASE_URL")
        self.pool = None
        self.checkpointer = None
        self.pgvector_enabled = False
        self.fernet = None

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
            
            # Setup Fernet Encryption
            enc_key = os.getenv("ENCRYPTION_KEY")
            if enc_key:
                try:
                    self.fernet = Fernet(enc_key.encode())
                except Exception as e:
                    print(f"[Database] Invalid ENCRYPTION_KEY format: {e}. Integration tokens will not be secure.")
            else:
                print("[Database] ENCRYPTION_KEY environment variable is not configured. Falling back to temporary encryption key.")
                self.fernet = Fernet(Fernet.generate_key())
                
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
                    
                    # Create user_integrations table
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_integrations (
                            id SERIAL PRIMARY KEY,
                            user_id UUID NOT NULL,
                            provider VARCHAR(50) NOT NULL,
                            access_token TEXT NOT NULL,
                            refresh_token TEXT,
                            token_expires_at TIMESTAMP WITH TIME ZONE,
                            scopes TEXT[],
                            tenant_id TEXT,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE (user_id, provider)
                        );
                        CREATE INDEX IF NOT EXISTS idx_user_integrations_user ON user_integrations(user_id);
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

    def encrypt_token(self, plain_token: str) -> Optional[str]:
        if not self.fernet or not plain_token:
            return plain_token
        return self.fernet.encrypt(plain_token.encode()).decode()

    def decrypt_token(self, encrypted_token: str) -> Optional[str]:
        if not self.fernet or not encrypted_token:
            return encrypted_token
        try:
            return self.fernet.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            print(f"[Database] Decryption failed: {e}")
            return None

    async def save_integration(
        self, user_id: str, provider: str, access_token: str,
        refresh_token: Optional[str] = None, expires_at_timestamp: Optional[float] = None,
        scopes: Optional[List[str]] = None, tenant_id: Optional[str] = None
    ):
        if not self.pool:
            return
        enc_access = self.encrypt_token(access_token)
        enc_refresh = self.encrypt_token(refresh_token) if refresh_token else None
        scopes_val = list(scopes) if scopes else None
        
        expires_at = datetime.datetime.fromtimestamp(expires_at_timestamp, datetime.timezone.utc) if expires_at_timestamp else None

        query = """
            INSERT INTO user_integrations (
                user_id, provider, access_token, refresh_token, token_expires_at, scopes, tenant_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = COALESCE(EXCLUDED.refresh_token, user_integrations.refresh_token),
                token_expires_at = EXCLUDED.token_expires_at,
                scopes = EXCLUDED.scopes,
                tenant_id = COALESCE(EXCLUDED.tenant_id, user_integrations.tenant_id),
                updated_at = NOW();
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    query,
                    (user_id, provider, enc_access, enc_refresh, expires_at, scopes_val, tenant_id)
                )

    async def get_integration(self, user_id: str, provider: str) -> Optional[dict]:
        if not self.pool:
            return None
        query = """
            SELECT * FROM user_integrations WHERE user_id = %s AND provider = %s;
        """
        async with self.get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (user_id, provider))
                row = await cur.fetchone()
                if row:
                    row_copy = dict(row)
                    row_copy["access_token"] = self.decrypt_token(row_copy["access_token"])
                    if row_copy.get("refresh_token"):
                        row_copy["refresh_token"] = self.decrypt_token(row_copy["refresh_token"])
                    return row_copy
                return None

# Global database manager instance
db_manager = DatabaseManager()
