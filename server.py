import os
import uuid
import logging
from typing import Optional, Literal
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from middleware.graph import workflow
from middleware.database import db_manager

# Load environment variables
load_dotenv()

# --- Logging Security Guardrail (Observability Data Masking) ---
class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.msg, str):
            return True
        msg_lower = record.msg.lower()
        # Redact logs containing 'prompt' or 'completion' payloads to prevent telemetry leakage
        if "prompt" in msg_lower or "completion" in msg_lower:
            record.msg = "[REDACTED due to sensitive telemetry policies]"
        return True

# Initialize logging filter
logging.basicConfig(level=logging.INFO)
redact_filter = RedactingFilter()
logging.getLogger().addFilter(redact_filter)
for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(logger_name).addFilter(redact_filter)

logger = logging.getLogger("pm_middleware_api")

# --- Request/Response Models ---
class StartPlanRequest(BaseModel):
    raw_prd: str = Field(..., description="The product requirements document markdown text.")
    source_document: Optional[str] = Field(None, description="Optional upstream source URL (e.g. Notion, Confluence).")
    thread_id: Optional[str] = Field(None, description="Optional thread identifier. Generates a new UUID if not provided.")

class ResumePlanRequest(BaseModel):
    decision: Literal["approve", "revise"] = Field(..., description="The EM's planning decision.")
    comments: Optional[str] = Field(None, description="Comments or revision instructions from the Engineering Manager.")

# --- Lifespan Handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect connection pool & set up schemas
    try:
        await db_manager.connect()
        app.state.graph_db = workflow.compile(checkpointer=db_manager.checkpointer)
        logger.info("[DB] Database connected and PostgresSaver compiled successfully.")
    except Exception as e:
        logger.warning(f"[DB] Database connection failed: {e}. Falling back to MemorySaver (in-memory checking).")
        app.state.graph_db = workflow.compile(checkpointer=MemorySaver())
    yield
    # Shutdown: Close DB connections
    try:
        await db_manager.disconnect()
        logger.info("[DB] Database pool connection closed.")
    except Exception as e:
        logger.error(f"[DB] Error closing database connection pool: {e}")

# --- Initialize App ---
app = FastAPI(
    title="AI-Driven PM & Engineering Middleware API",
    description="Backend API powering the transitions between upstream PRDs and downstream Jira backlogs.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for Next.js UI integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Background Task Helpers ---
async def handle_after_execution(graph, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config)
    
    if snapshot and snapshot.next:
        # Paused at an interrupt (usually human_approval)
        values = snapshot.values
        tickets = values.get("jira_tickets", []) or []
        
        # Calculate stats
        total_story_points = sum(t.get("estimation", 0) for t in tickets if isinstance(t, dict))
        total_epics = sum(1 for t in tickets if isinstance(t, dict) and t.get("type") == "Epic")
        total_stories = sum(1 for t in tickets if isinstance(t, dict) and t.get("type") == "Story")
        ai_summary = values.get("missing_edge_cases", "")
        
        # Limit size to prevent database row-limit warnings
        ai_summary_trimmed = ai_summary[:500] + ("..." if len(ai_summary) > 500 else "")
        
        # Retrieve original title
        title = values.get("raw_prd", "").splitlines()[0].lstrip("#* ").strip()[:100] or "Sprint Plan"
        
        # Save state metrics to project history table (Track B)
        try:
            await db_manager.save_project_history(
                thread_id=thread_id,
                title=title,
                source_doc=None,
                status="AWAITING_EM_APPROVAL",
                metrics={
                    "total_epics": total_epics,
                    "total_stories": total_stories,
                    "total_story_points": total_story_points
                },
                ai_summary=ai_summary_trimmed
            )
            logger.info(f"[PLAN] Session {thread_id} status updated to AWAITING_EM_APPROVAL.")
        except Exception as e:
            logger.error(f"[DB] Failed to save metadata to project_history: {e}")
    else:
        # Graph completed execution
        values = snapshot.values if snapshot else {}
        status = "COMPLETED"
        if values.get("em_approval_status") == "APPROVED":
            status = "COMPLETED_SYNCED"
        
        try:
            await db_manager.update_project_status(thread_id, status)
            logger.info(f"[PLAN] Session {thread_id} completed successfully with status: {status}.")
        except Exception as e:
            logger.error(f"[DB] Failed to update project completion status: {e}")

async def run_graph_background(graph, thread_id: str, initial_state: dict):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        await graph.ainvoke(initial_state, config=config)
        await handle_after_execution(graph, thread_id)
    except Exception as e:
        logger.error(f"[PLAN] Exception in background graph thread {thread_id}: {e}")
        try:
            await db_manager.update_project_status(thread_id, "FAILED")
        except Exception:
            pass

async def run_graph_resume_background(graph, thread_id: str, resume_cmd: Command):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        await graph.ainvoke(resume_cmd, config=config)
        await handle_after_execution(graph, thread_id)
    except Exception as e:
        logger.error(f"[PLAN] Exception in background resume thread {thread_id}: {e}")
        try:
            await db_manager.update_project_status(thread_id, "FAILED")
        except Exception:
            pass

# --- API Endpoints ---
@app.post("/api/v1/plan/start")
async def start_plan(request: StartPlanRequest, background_tasks: BackgroundTasks):
    thread_id = request.thread_id or str(uuid.uuid4())
    
    # Try fetching project history to avoid duplicate runs
    try:
        existing = await db_manager.get_project_history(thread_id)
        if existing:
            raise HTTPException(status_code=400, detail=f"Planning session with thread_id {thread_id} already exists.")
    except Exception:
        # If DB is not connected/offline, allow running in-memory fallback
        pass
        
    initial_state = {
        "raw_prd": request.raw_prd,
        "codebase_summary": None,
        "missing_edge_cases": None,
        "jira_tickets": None,
        "em_approval_status": "PENDING",
        "em_feedback_comments": None,
        "attempt_count": 0
    }
    
    title = f"Plan for {request.raw_prd.splitlines()[0][:50]}" if request.raw_prd else "New Sprint Plan"
    title = title.lstrip("#* ").strip()
    
    # Write initial project metadata row
    try:
        await db_manager.save_project_history(
            thread_id=thread_id,
            title=title,
            source_doc=request.source_document,
            status="PROCESSING",
            metrics={},
            ai_summary=""
        )
    except Exception as e:
        logger.warning(f"[DB] Skipping history write (running in memory): {e}")

    # Kickoff graph thread asynchronously
    background_tasks.add_task(run_graph_background, app.state.graph_db, thread_id, initial_state)
    
    return {"thread_id": thread_id, "status": "PROCESSING"}

@app.get("/api/v1/plan/{thread_id}/status")
async def get_plan_status(thread_id: str):
    # Fetch from lightweight history metadata first
    try:
        history = await db_manager.get_project_history(thread_id)
    except Exception:
        history = None
        
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await app.state.graph_db.aget_state(config)
    
    if not snapshot or not snapshot.values:
        if not history:
            raise HTTPException(status_code=404, detail="Planning session not found.")
            
    values = snapshot.values if snapshot else {}
    
    # Construct combined response
    return {
        "thread_id": thread_id,
        "status": history["status"] if history else ("AWAITING_EM_APPROVAL" if snapshot.next else "COMPLETED"),
        "title": history["title"] if history else "In-Memory Session",
        "source_document": history["source_document"] if history else None,
        "metrics": {
            "total_epics": history["total_epics"] if history else 0,
            "total_stories": history["total_stories"] if history else 0,
            "total_story_points": history["total_story_points"] if history else 0
        },
        "ai_summary": history["ai_summary"] if history else values.get("missing_edge_cases", ""),
        "draft_tickets": values.get("jira_tickets"),
        "missing_edge_cases": values.get("missing_edge_cases"),
        "em_feedback_comments": values.get("em_feedback_comments"),
        "attempt_count": values.get("attempt_count", 0),
        "paused_waiting_input": bool(snapshot.next) if snapshot else False
    }

@app.post("/api/v1/plan/{thread_id}/resume")
async def resume_plan(thread_id: str, request: ResumePlanRequest, background_tasks: BackgroundTasks):
    config = {"configurable": {"thread_id": thread_id}}
    graph = app.state.graph_db
    
    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.next:
        raise HTTPException(status_code=400, detail="Planning session is not currently paused and cannot be resumed.")
        
    resume_payload = {
        "decision": request.decision,
        "comments": request.comments or ""
    }
    
    # Update status to PROCESSING
    try:
        await db_manager.update_project_status(thread_id, "PROCESSING")
    except Exception as e:
        logger.warning(f"[DB] Skipping history status update (running in memory): {e}")
        
    # Resume the workflow asynchronously
    background_tasks.add_task(
        run_graph_resume_background, 
        graph, 
        thread_id, 
        Command(resume=resume_payload)
    )
    
    return {"status": "resumed_and_processing"}

@app.get("/api/v1/projects")
async def list_projects():
    try:
        projects = await db_manager.list_project_history()
        return {"projects": projects}
    except Exception as e:
        logger.error(f"[DB] Failed to list projects: {e}")
        return {"projects": []}
