import os
import json
import litellm
from typing import List, Optional, Dict, Any
from middleware.config import EMBEDDING_MODEL

# Sample tickets to seed the database
SEED_TICKETS = [
    {
        "ticket_key": "PROJ-101",
        "title": "Implement OAuth2 Login with Google",
        "description": "Create backend routes, database schema changes for users, and integrate Google OAuth2 flow using dynamic state validation.",
        "estimation": 5,
        "priority": "HIGH"
    },
    {
        "ticket_key": "PROJ-102",
        "title": "Set up Stripe Webhook Listener",
        "description": "Configure endpoint to receive webhook events from Stripe, verify signatures, and update user subscription status in postgres.",
        "estimation": 3,
        "priority": "HIGH"
    },
    {
        "ticket_key": "PROJ-103",
        "title": "Create User Profile Database Schema",
        "description": "Define database migrations for user profile tables including indexing on email and provider fields.",
        "estimation": 2,
        "priority": "MEDIUM"
    },
    {
        "ticket_key": "PROJ-104",
        "title": "Email Notification Service Integration",
        "description": "Integrate SendGrid or AWS SES to send transactional emails for user signups, password resets, and subscription updates.",
        "estimation": 2,
        "priority": "LOW"
    },
    {
        "ticket_key": "PROJ-105",
        "title": "Configure Redis Cache for Session Management",
        "description": "Deploy Redis instance and set up session middleware with sliding expiration to cache user session details.",
        "estimation": 3,
        "priority": "MEDIUM"
    }
]

async def generate_embedding(text: str, input_type: Optional[str] = None) -> Optional[List[float]]:
    """
    Generate an embedding using LiteLLM. Returns None on failure.
    """
    try:
        kwargs = {}
        if "cohere" in EMBEDDING_MODEL:
            kwargs["input_type"] = input_type or "search_document"
            
        response = await litellm.aembedding(model=EMBEDDING_MODEL, input=[text], **kwargs)
        if hasattr(response, 'data') and response.data:
            return response.data[0].embedding
        elif isinstance(response, dict) and 'data' in response and response['data']:
            return response['data'][0]['embedding']
        return None
    except Exception as e:
        print(f"[RAG] Failed to generate embedding for text: {e}")
        return None

async def seed_historical_tickets(db) -> None:
    """
    Seeds the database with initial historical tickets. Uses an advisory lock to
    prevent concurrent seeding.
    """
    if not db or not db.pool:
        print("[RAG] Database pool not initialized. Skipping seed.")
        return

    try:
        async with db.pool.connection() as conn:
            async with conn.cursor() as cur:
                # Wrap the seeding process in a single transaction with an advisory lock
                await cur.execute("SELECT pg_try_advisory_xact_lock(10242026);")
                lock_acquired = await cur.fetchone()
                if not lock_acquired or not lock_acquired[0]:
                    print("[RAG] Seeding lock already held by another process. Skipping seeding.")
                    return

                # Check if already seeded
                await cur.execute("SELECT COUNT(*) FROM historical_tickets;")
                count = await cur.fetchone()
                if count and count[0] > 0:
                    print(f"[RAG] historical_tickets table already has {count[0]} records. Skipping seeding.")
                    return

                print("[RAG] Seeding sample historical tickets...")
                for ticket in SEED_TICKETS:
                    text_to_embed = f"{ticket['title']} {ticket['description']}"
                    embedding = await generate_embedding(text_to_embed, input_type="search_document")

                    if db.pgvector_enabled and embedding:
                        val_embedding = "[" + ",".join(map(str, embedding)) + "]"
                    else:
                        val_embedding = json.dumps(embedding) if embedding else None

                    await cur.execute(
                        """
                        INSERT INTO historical_tickets (ticket_key, title, description, estimation, priority, embedding, sprint_plan_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ticket_key) DO NOTHING;
                        """,
                        (ticket["ticket_key"], ticket["title"], ticket["description"], ticket["estimation"], ticket["priority"], val_embedding, "seed-sprint-plan-101")
                    )
                print("[RAG] Seeding complete.")
    except Exception as e:
        print(f"[RAG] Failed during seeding operation: {e}")

async def search_similar_tickets(db, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Performs Vector-Time Graph Retrieval:
    1. Finds the single most relevant Seed Ticket using semantic or text search.
    2. Expands the search to a cluster:
       - If the Seed Ticket has a sprint_plan_id, retrieves all tickets sharing it.
       - Otherwise/fallback: retrieves tickets that are semantically close (cosine distance < 0.25)
         and temporally close (+/- 21 days) to the Seed Ticket.
    """
    if not db or not db.pool:
        print("[RAG] No active database pool. Returning empty list.")
        return []

    # Step 1: Find the Seed Ticket
    embedding = await generate_embedding(query, input_type="search_query")
    seed_ticket = None

    if db.pgvector_enabled and embedding:
        emb_str = "[" + ",".join(map(str, embedding)) + "]"
        query_sql = """
            SELECT ticket_key, title, description, estimation, priority, sprint_plan_id, created_at, embedding::text as embedding_text
            FROM historical_tickets
            ORDER BY embedding <=> %s::vector
            LIMIT 1;
        """
        try:
            async with db.pool.connection() as conn:
                from psycopg.rows import dict_row
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(query_sql, (emb_str,))
                    seed_ticket = await cur.fetchone()
        except Exception as e:
            print(f"[RAG] Seed ticket vector search failed: {e}. Trying text fallback.")
            
    # Text-based fallback to find Seed Ticket
    if not seed_ticket:
        keywords = [kw.strip().lower() for kw in query.split() if len(kw.strip()) > 3]
        keywords = keywords[:5]
        
        if not keywords:
            query_sql = """
                SELECT ticket_key, title, description, estimation, priority, sprint_plan_id, created_at
                FROM historical_tickets
                ORDER BY created_at DESC
                LIMIT 1;
            """
            params = ()
        else:
            conditions = []
            params = []
            for kw in keywords:
                conditions.append("(title ILIKE %s OR description ILIKE %s)")
                params.append(f"%{kw}%")
                params.append(f"%{kw}%")
            cond_str = " OR ".join(conditions)
            query_sql = f"""
                SELECT ticket_key, title, description, estimation, priority, sprint_plan_id, created_at
                FROM historical_tickets
                WHERE {cond_str}
                ORDER BY created_at DESC
                LIMIT 1;
            """
            params = tuple(params)
        try:
            async with db.pool.connection() as conn:
                from psycopg.rows import dict_row
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(query_sql, params)
                    seed_ticket = await cur.fetchone()
        except Exception as e:
            print(f"[RAG] Seed ticket text search failed: {e}")

    if not seed_ticket:
        print("[RAG] No seed ticket found in database.")
        return []

    print(f"[RAG] Found Seed Ticket: {seed_ticket['ticket_key']} (Sprint Plan: {seed_ticket.get('sprint_plan_id')})")

    # Step 2: Cluster Expansion
    sprint_plan_id = seed_ticket.get("sprint_plan_id")
    cluster_tickets = []

    # If the seed ticket belongs to a sprint plan, retrieve all tickets in that plan
    if sprint_plan_id:
        print(f"[RAG] Expanding cluster using sprint_plan_id: {sprint_plan_id}")
        query_sql = """
            SELECT ticket_key, title, description, estimation, priority
            FROM historical_tickets
            WHERE sprint_plan_id = %s
            LIMIT %s;
        """
        try:
            async with db.pool.connection() as conn:
                from psycopg.rows import dict_row
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(query_sql, (sprint_plan_id, top_k))
                    cluster_tickets = await cur.fetchall()
        except Exception as e:
            print(f"[RAG] Cluster fetch by sprint_plan_id failed: {e}")

    # Fallback to temporal & semantic close check if plan-based fetch yielded nothing/too little
    if len(cluster_tickets) < 2:
        print("[RAG] Expanding cluster using temporal/semantic proximity...")
        created_at = seed_ticket["created_at"]
        
        if db.pgvector_enabled and seed_ticket.get("embedding_text"):
            # Semantic closeness (cosine distance < 0.25) AND temporal closeness (+/- 21 days)
            query_sql = """
                SELECT ticket_key, title, description, estimation, priority
                FROM historical_tickets
                WHERE (embedding <=> %s::vector) < 0.25
                  AND created_at BETWEEN (%s::timestamp with time zone - INTERVAL '21 days') AND (%s::timestamp with time zone + INTERVAL '21 days')
                LIMIT %s;
            """
            params = (seed_ticket["embedding_text"], created_at, created_at, top_k)
        else:
            # Temporal closeness fallback only
            query_sql = """
                SELECT ticket_key, title, description, estimation, priority
                FROM historical_tickets
                WHERE created_at BETWEEN (%s::timestamp with time zone - INTERVAL '21 days') AND (%s::timestamp with time zone + INTERVAL '21 days')
                LIMIT %s;
            """
            params = (created_at, created_at, top_k)

        try:
            async with db.pool.connection() as conn:
                from psycopg.rows import dict_row
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(query_sql, params)
                    cluster_tickets = await cur.fetchall()
        except Exception as e:
            print(f"[RAG] Proximity cluster fetch failed: {e}")

    # Ensure the seed ticket itself is included in the list and deduplicated
    all_tickets = {t["ticket_key"]: t for t in cluster_tickets}
    clean_seed = {
        "ticket_key": seed_ticket["ticket_key"],
        "title": seed_ticket["title"],
        "description": seed_ticket["description"],
        "estimation": seed_ticket["estimation"],
        "priority": seed_ticket["priority"]
    }
    all_tickets[seed_ticket["ticket_key"]] = clean_seed

    return list(all_tickets.values())

async def store_approved_tickets(db, tickets: List[Dict[str, Any]], sprint_plan_id: Optional[str] = None) -> None:
    """
    Stores or updates approved tickets in the historical_tickets table, closing the feedback loop.
    """
    if not db or not db.pool:
        print("[RAG] No active database pool. Skipping storage of approved tickets.")
        return

    print(f"[RAG] Storing {len(tickets)} approved tickets to historical_tickets...")
    for ticket in tickets:
        title = ticket.get("title", "")
        description = ticket.get("description", "")
        ticket_key = ticket.get("ticket_key")
        estimation = ticket.get("estimation") or ticket.get("story_points")
        priority = ticket.get("priority", "MEDIUM")

        if not ticket_key or not title:
            continue

        try:
            estimation = int(estimation) if estimation is not None else 0
        except ValueError:
            estimation = 0

        text_to_embed = f"{title} {description}"
        embedding = await generate_embedding(text_to_embed, input_type="search_document")

        if db.pgvector_enabled and embedding:
            val_embedding = "[" + ",".join(map(str, embedding)) + "]"
        else:
            val_embedding = json.dumps(embedding) if embedding else None

        query_sql = """
            INSERT INTO historical_tickets (ticket_key, title, description, estimation, priority, embedding, sprint_plan_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticket_key) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                estimation = EXCLUDED.estimation,
                priority = EXCLUDED.priority,
                embedding = COALESCE(EXCLUDED.embedding, historical_tickets.embedding),
                sprint_plan_id = COALESCE(EXCLUDED.sprint_plan_id, historical_tickets.sprint_plan_id);
        """
        try:
            async with db.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query_sql, (ticket_key, title, description, estimation, priority, val_embedding, sprint_plan_id))
        except Exception as e:
            print(f"[RAG] Failed to store approved ticket {ticket_key}: {e}")
