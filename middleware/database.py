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
                max_size=10,
                kwargs={"autocommit": True}
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
                            org_id TEXT DEFAULT 'default-org',
                            title TEXT,
                            source_document TEXT,
                            status TEXT,
                            total_epics INTEGER DEFAULT 0,
                            total_stories INTEGER DEFAULT 0,
                            total_story_points INTEGER DEFAULT 0,
                            ai_summary TEXT,
                            sent_to_em BOOLEAN DEFAULT FALSE,
                            shared_with_dev BOOLEAN DEFAULT FALSE,
                            project_mode TEXT,
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
                            org_id TEXT DEFAULT 'default-org',
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
                        
                    try:
                        await cur.execute("ALTER TABLE project_history ADD COLUMN IF NOT EXISTS project_mode TEXT;")
                    except Exception as e:
                        print(f"[Database] Failed to alter project_history for project_mode: {e}")

                        
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
                            org_id TEXT DEFAULT 'default-org',
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

                    # Execute alterations to add org_id dynamically to existing databases
                    try:
                        await cur.execute("ALTER TABLE project_history ADD COLUMN IF NOT EXISTS org_id TEXT DEFAULT 'default-org';")
                        await cur.execute("ALTER TABLE historical_tickets ADD COLUMN IF NOT EXISTS org_id TEXT DEFAULT 'default-org';")
                        await cur.execute("ALTER TABLE user_integrations ADD COLUMN IF NOT EXISTS org_id TEXT DEFAULT 'default-org';")
                        await cur.execute("ALTER TABLE project_history ADD COLUMN IF NOT EXISTS sent_to_em BOOLEAN DEFAULT FALSE;")
                        await cur.execute("ALTER TABLE project_history ADD COLUMN IF NOT EXISTS shared_with_dev BOOLEAN DEFAULT FALSE;")
                    except Exception as alt_err:
                        print(f"[Database] Failed to dynamically alter tables for multi-tenancy & visibility: {alt_err}")
                    
                    # Safe conditional Row-Level Security (RLS) policies for Supabase environments
                    try:
                        # Check if Supabase's auth schema exists to avoid local/CI test crashes
                        await cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth';")
                        has_auth_schema = await cur.fetchone()
                        
                        if has_auth_schema:
                            print("[Database] Supabase Auth schema detected. Initializing Row-Level Security policies.")
                            
                            # Enable RLS
                            await cur.execute("ALTER TABLE project_history ENABLE ROW LEVEL SECURITY;")
                            await cur.execute("ALTER TABLE user_integrations ENABLE ROW LEVEL SECURITY;")
                            await cur.execute("ALTER TABLE ticket_change_requests ENABLE ROW LEVEL SECURITY;")
                            
                            # Project History RLS Policies
                            await cur.execute("DROP POLICY IF EXISTS select_project_history ON project_history;")
                            await cur.execute("""
                                CREATE POLICY select_project_history ON project_history
                                FOR SELECT USING (
                                    (auth.jwt() ->> 'role' = 'product_manager') OR 
                                    (auth.jwt() -> 'user_metadata' ->> 'role' = 'PM') OR
                                    (((auth.jwt() ->> 'role' = 'engineering_manager') OR (auth.jwt() -> 'user_metadata' ->> 'role' = 'EM')) AND sent_to_em = TRUE) OR
                                    (((auth.jwt() ->> 'role' = 'developer') OR (auth.jwt() -> 'user_metadata' ->> 'role' = 'DEV')) AND shared_with_dev = TRUE)
                                );
                            """)
                            
                            await cur.execute("DROP POLICY IF EXISTS insert_project_history ON project_history;")
                            await cur.execute("""
                                CREATE POLICY insert_project_history ON project_history
                                FOR INSERT WITH CHECK (
                                    (auth.jwt() ->> 'role' = 'product_manager') OR 
                                    (auth.jwt() -> 'user_metadata' ->> 'role' = 'PM')
                                );
                            """)
                            
                            await cur.execute("DROP POLICY IF EXISTS update_project_history ON project_history;")
                            await cur.execute("""
                                CREATE POLICY update_project_history ON project_history
                                FOR UPDATE USING (
                                    (auth.jwt() ->> 'role' = 'product_manager') OR 
                                    (auth.jwt() -> 'user_metadata' ->> 'role' = 'PM') OR
                                    ((auth.jwt() ->> 'role' = 'engineering_manager') OR (auth.jwt() -> 'user_metadata' ->> 'role' = 'EM'))
                                );
                            """)

                            # User Integrations RLS: Only allow users to read/write their own OAuth tokens
                            await cur.execute("DROP POLICY IF EXISTS select_own_integrations ON user_integrations;")
                            await cur.execute("""
                                CREATE POLICY select_own_integrations ON user_integrations
                                FOR ALL USING (auth.uid() = user_id);
                            """)
                            
                            # Ticket Change Requests RLS: Everyone read, Devs write, EMs modify
                            await cur.execute("DROP POLICY IF EXISTS select_change_requests ON ticket_change_requests;")
                            await cur.execute("""
                                CREATE POLICY select_change_requests ON ticket_change_requests
                                FOR SELECT USING (true);
                            """)
                            
                            await cur.execute("DROP POLICY IF EXISTS insert_dev_change_requests ON ticket_change_requests;")
                            await cur.execute("""
                                CREATE POLICY insert_dev_change_requests ON ticket_change_requests
                                FOR INSERT WITH CHECK (
                                    (auth.jwt() ->> 'role' = 'developer') OR (auth.jwt() ->> 'role' = 'authenticated')
                                );
                            """)
                            
                            await cur.execute("DROP POLICY IF EXISTS resolve_em_change_requests ON ticket_change_requests;")
                            await cur.execute("""
                                CREATE POLICY resolve_em_change_requests ON ticket_change_requests
                                FOR ALL USING (
                                    (auth.jwt() ->> 'role' = 'engineering_manager') OR (auth.jwt() ->> 'role' = 'authenticated')
                                );
                            """)
                        else:
                            print("[Database] Standard Postgres detected. Skipping Supabase RLS configurations.")
                    except Exception as rls_err:
                        print(f"[Database] Row-Level Security policy initialization skipped: {rls_err}")
            
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

    async def save_project_history(self, thread_id: str, title: str, source_doc: str, status: str, metrics: dict, ai_summary: str, org_id: str = 'default-org', project_mode: Optional[str] = None):
        query = """
            INSERT INTO project_history (
                thread_id, org_id, title, source_document, status, total_epics, total_stories, total_story_points, ai_summary, project_mode
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (thread_id) DO UPDATE SET
                org_id = EXCLUDED.org_id,
                status = EXCLUDED.status,
                total_epics = EXCLUDED.total_epics,
                total_stories = EXCLUDED.total_stories,
                total_story_points = EXCLUDED.total_story_points,
                ai_summary = EXCLUDED.ai_summary,
                project_mode = COALESCE(EXCLUDED.project_mode, project_history.project_mode),
                updated_at = NOW();
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    query,
                    (
                        thread_id,
                        org_id,
                        title,
                        source_doc,
                        status,
                        metrics.get("total_epics", 0),
                        metrics.get("total_stories", 0),
                        metrics.get("total_story_points", 0),
                        ai_summary,
                        project_mode
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

    async def get_project_history(self, thread_id: str, org_id: Optional[str] = None):
        if org_id:
            query = """
                SELECT * FROM project_history WHERE thread_id = %s AND org_id = %s;
            """
            params = (thread_id, org_id)
        else:
            query = """
                SELECT * FROM project_history WHERE thread_id = %s;
            """
            params = (thread_id,)
        async with self.get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                return await cur.fetchone()

    async def list_project_history(self, limit: int = 50, org_id: str = 'default-org', role: str = None):
        if role == 'DEV':
            query = """
                SELECT * FROM project_history 
                WHERE org_id = %s AND shared_with_dev = TRUE 
                ORDER BY updated_at DESC LIMIT %s;
            """
        elif role == 'EM':
            query = """
                SELECT * FROM project_history 
                WHERE org_id = %s AND sent_to_em = TRUE 
                ORDER BY updated_at DESC LIMIT %s;
            """
        else:
            query = """
                SELECT * FROM project_history 
                WHERE org_id = %s 
                ORDER BY updated_at DESC LIMIT %s;
            """
        async with self.get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (org_id, limit))
                return await cur.fetchall()

    async def update_project_visibility(self, thread_id: str, sent_to_em: Optional[bool] = None, shared_with_dev: Optional[bool] = None) -> bool:
        if not self.pool:
            return False
        
        updates = []
        params = []
        if sent_to_em is not None:
            updates.append("sent_to_em = %s")
            params.append(sent_to_em)
        if shared_with_dev is not None:
            updates.append("shared_with_dev = %s")
            params.append(shared_with_dev)
            
        if not updates:
            return False
            
        query = f"""
            UPDATE project_history 
            SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE thread_id = %s;
        """
        params.append(thread_id)
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, tuple(params))
                return True

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
        scopes: Optional[List[str]] = None, tenant_id: Optional[str] = None, org_id: str = 'default-org'
    ):
        if not self.pool:
            return
            
        import uuid
        try:
            user_uuid = uuid.UUID(str(user_id))
        except ValueError:
            user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(user_id))

        enc_access = self.encrypt_token(access_token)
        enc_refresh = self.encrypt_token(refresh_token) if refresh_token else None
        scopes_val = list(scopes) if scopes else None
        
        expires_at = datetime.datetime.fromtimestamp(expires_at_timestamp, datetime.timezone.utc) if expires_at_timestamp else None
 
        query = """
            INSERT INTO user_integrations (
                user_id, provider, access_token, refresh_token, token_expires_at, scopes, tenant_id, org_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = COALESCE(EXCLUDED.refresh_token, user_integrations.refresh_token),
                token_expires_at = EXCLUDED.token_expires_at,
                scopes = EXCLUDED.scopes,
                tenant_id = COALESCE(EXCLUDED.tenant_id, user_integrations.tenant_id),
                org_id = EXCLUDED.org_id,
                updated_at = NOW();
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    query,
                    (user_uuid, provider, enc_access, enc_refresh, expires_at, scopes_val, tenant_id, org_id)
                )

    async def get_integration(self, user_id: str, provider: str, org_id: str = 'default-org') -> Optional[dict]:
        if not self.pool:
            return None
            
        import uuid
        try:
            user_uuid = uuid.UUID(str(user_id))
        except ValueError:
            user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(user_id))

        query = """
            SELECT * FROM user_integrations WHERE user_id = %s AND provider = %s AND org_id = %s;
        """
        async with self.get_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (user_uuid, provider, org_id))
                row = await cur.fetchone()
                if row:
                    row_copy = dict(row)
                    row_copy["access_token"] = self.decrypt_token(row_copy["access_token"])
                    if row_copy.get("refresh_token"):
                        row_copy["refresh_token"] = self.decrypt_token(row_copy["refresh_token"])
                    return row_copy
                return None

    async def delete_integration(self, user_id: str, provider: str, org_id: str = 'default-org') -> bool:
        if not self.pool:
            return False
            
        import uuid
        try:
            user_uuid = uuid.UUID(str(user_id))
        except ValueError:
            user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(user_id))

        query = """
            DELETE FROM user_integrations WHERE user_id = %s AND provider = %s AND org_id = %s;
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (user_uuid, provider, org_id))
                return True

# Global database manager instance
db_manager = DatabaseManager()
