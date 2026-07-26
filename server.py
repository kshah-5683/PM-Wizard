import os
import uuid
import logging
from typing import Optional, Literal, List
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends
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

# --- Role-Based Access Control (RBAC) Dependency ---
async def get_current_role(x_user_role: str = Header(default="PM", description="The simulated user role (PM, EM, DEV)")) -> str:
    role = x_user_role.upper()
    if role not in ("PM", "EM", "DEV"):
        raise HTTPException(status_code=400, detail="Invalid X-User-Role header value. Must be 'PM', 'EM', or 'DEV'.")
    return role

async def get_current_org(x_org_id: str = Header(default="default-org", description="The tenant organization ID")) -> str:
    return x_org_id

# --- Request/Response Models ---
class StartPlanRequest(BaseModel):
    raw_prd: str = Field(..., description="The product requirements document markdown text.")
    source_document: Optional[str] = Field(None, description="Optional upstream source URL (e.g. Notion, Confluence).")
    thread_id: Optional[str] = Field(None, description="Optional thread identifier. Generates a new UUID if not provided.")
    sprint_constraints: Optional[str] = Field(None, description="Optional dynamic engineering or business constraints.")
    custom_tags: Optional[List[str]] = Field(None, description="Optional custom tags list.")

class ResumePlanRequest(BaseModel):
    decision: Optional[Literal["approve", "revise"]] = Field(None, description="The EM's planning decision.")
    comments: Optional[str] = Field(None, description="Comments or revision instructions from the Engineering Manager.")
    status: Optional[str] = Field(None, description="Alternative field for decision status.")
    feedback: Optional[str] = Field(None, description="Alternative field for feedback comments.")
    action: Optional[Literal["bypass", "amend"]] = Field(None, description="Decision action for critic resolution.")
    amended_prd: Optional[str] = Field(None, description="Amended PRD content if action is 'amend'.")

class ChangeRequestPayload(BaseModel):
    ticket_key: str = Field(..., description="The key of the ticket to modify, e.g. TICKET-1")
    developer_name: str = Field(..., description="The name of the developer requesting the change.")
    original_points: Optional[int] = Field(None, description="Original story points estimation.")
    original_description: Optional[str] = Field(None, description="Original description text.")
    requested_points: Optional[int] = Field(None, description="Requested story points estimation.")
    requested_description: Optional[str] = Field(None, description="Requested description text.")

class ResolveChangeRequestPayload(BaseModel):
    status: Literal["APPROVED", "REJECTED"] = Field(..., description="Decision: APPROVED or REJECTED")

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
        # Paused at an interrupt (human_approval or critic_resolution)
        values = snapshot.values
        tickets = values.get("jira_tickets", []) or []
        
        # Determine which interrupt it is
        interrupt_type = "human_approval_required"
        if snapshot.tasks:
            for task in snapshot.tasks:
                if task.interrupts:
                    val = task.interrupts[0].value
                    if isinstance(val, dict):
                        interrupt_type = val.get("type", "human_approval_required")
                    break
        
        status_str = "AWAITING_EM_APPROVAL"
        if interrupt_type == "critic_resolution_required":
            status_str = "AWAITING_CRITIC_RESOLUTION"
            
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
            org_id = values.get("org_id", "default-org")
            await db_manager.save_project_history(
                thread_id=thread_id,
                title=title,
                source_doc=None,
                status=status_str,
                metrics={
                    "total_epics": total_epics,
                    "total_stories": total_stories,
                    "total_story_points": total_story_points
                },
                ai_summary=ai_summary_trimmed,
                org_id=org_id
            )
            logger.info(f"[PLAN] Session {thread_id} status updated to {status_str}.")
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
async def start_plan(request: StartPlanRequest, background_tasks: BackgroundTasks, role: str = Depends(get_current_role), org_id: str = Depends(get_current_org)):
    if role != "PM":
        raise HTTPException(status_code=403, detail="Access denied. Only Product Managers (PM) can initiate new sprint plans.")
    thread_id = request.thread_id or str(uuid.uuid4())
    
    # Try fetching project history to avoid duplicate runs
    try:
        existing = await db_manager.get_project_history(thread_id, org_id=org_id)
        if existing:
            raise HTTPException(status_code=400, detail=f"Planning session with thread_id {thread_id} already exists in this organization.")
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
        "attempt_count": 0,
        "workspace_profile": None,
        "sprint_constraints": request.sprint_constraints,
        "custom_tags": request.custom_tags,
        "org_id": org_id
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
            ai_summary="",
            org_id=org_id
        )
    except Exception as e:
        logger.warning(f"[DB] Skipping history write (running in memory): {e}")

    # Kickoff graph thread asynchronously
    background_tasks.add_task(run_graph_background, app.state.graph_db, thread_id, initial_state)
    
    return {"thread_id": thread_id, "status": "PROCESSING"}

@app.get("/api/v1/plan/{thread_id}/status")
async def get_plan_status(thread_id: str, org_id: str = Depends(get_current_org)):
    # Fetch from lightweight history metadata first
    try:
        history = await db_manager.get_project_history(thread_id, org_id=org_id)
    except Exception:
        history = None
        
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await app.state.graph_db.aget_state(config)
    
    # Secure validation check: Verify snapshot org matches request org
    if snapshot and snapshot.values:
        snapshot_org = snapshot.values.get("org_id", "default-org")
        if snapshot_org != org_id:
            raise HTTPException(status_code=403, detail="Access denied. This session belongs to another organization.")
            
    if not snapshot or not snapshot.values:
        if not history:
            raise HTTPException(status_code=404, detail="Planning session not found in this organization.")
            
    values = snapshot.values if snapshot else {}
    
    # Extract interrupt payload if paused
    interrupt_payload = None
    if snapshot and snapshot.tasks:
        for task in snapshot.tasks:
            if task.interrupts:
                interrupt_payload = task.interrupts[0].value
                break

    # Determine status
    if history:
        db_status = history["status"]
        if db_status == "PROCESSING":
            status_str = "RUNNING"
        elif db_status == "AWAITING_EM_APPROVAL":
            status_str = "AWAITING_APPROVAL"
        elif db_status == "AWAITING_CRITIC_RESOLUTION":
            status_str = "AWAITING_CRITIC_RESOLUTION"
        elif db_status in ("COMPLETED", "COMPLETED_SYNCED"):
            status_str = "COMPLETED"
        else:
            status_str = db_status
    else:
        if snapshot and snapshot.next:
            interrupt_type = "human_approval_required"
            if snapshot.tasks:
                for task in snapshot.tasks:
                    if task.interrupts:
                        val = task.interrupts[0].value
                        if isinstance(val, dict):
                            interrupt_type = val.get("type", "human_approval_required")
                        break
            if interrupt_type == "critic_resolution_required":
                status_str = "AWAITING_CRITIC_RESOLUTION"
            else:
                status_str = "AWAITING_APPROVAL"
        else:
            status_str = "COMPLETED"
        
    # Construct combined response
    return {
        "thread_id": thread_id,
        "status": status_str,
        "title": history["title"] if history else "In-Memory Session",
        "source_document": history["source_document"] if history else None,
        "metrics": {
            "total_epics": history["total_epics"] if history else 0,
            "total_stories": history["total_stories"] if history else 0,
            "total_story_points": history["total_story_points"] if history else 0
        },
        "ai_summary": history["ai_summary"] if history else values.get("missing_edge_cases", ""),
        "raw_prd": values.get("raw_prd"),
        "draft_tickets": values.get("jira_tickets"),
        "missing_edge_cases": values.get("missing_edge_cases"),
        "em_feedback_comments": values.get("em_feedback_comments"),
        "attempt_count": values.get("attempt_count", 0),
        "paused_waiting_input": bool(snapshot.next) if snapshot else False,
        "interrupt_payload": interrupt_payload
    }

@app.post("/api/v1/plan/{thread_id}/resume")
async def resume_plan(thread_id: str, request: ResumePlanRequest, background_tasks: BackgroundTasks, role: str = Depends(get_current_role), org_id: str = Depends(get_current_org)):
    config = {"configurable": {"thread_id": thread_id}}
    graph = app.state.graph_db
    
    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.next:
        raise HTTPException(status_code=400, detail="Planning session is not currently paused and cannot be resumed.")
        
    # Verify organization ownership
    if snapshot.values:
        snapshot_org = snapshot.values.get("org_id", "default-org")
        if snapshot_org != org_id:
            raise HTTPException(status_code=403, detail="Access denied. This session belongs to another organization.")
        
    # Check what type of interrupt we are resuming from
    interrupt_type = "human_approval_required"
    if snapshot.tasks:
        for task in snapshot.tasks:
            if task.interrupts:
                val = task.interrupts[0].value
                if isinstance(val, dict):
                    interrupt_type = val.get("type", "human_approval_required")
                break

    if interrupt_type == "critic_resolution_required":
        action = request.action
        if action is None:
            # Try mapping decision/status to action for compatibility
            dec = (request.decision or "").lower()
            stat = (request.status or "").lower()
            if dec == "approve" or "approve" in stat or dec == "bypass" or stat == "bypass" or request.action == "bypass":
                action = "bypass"
            else:
                action = "amend"
                
        # Role verification for critic resolution
        if action == "bypass" and role != "EM":
            raise HTTPException(status_code=403, detail="Access denied. Only Engineering Managers (EM) can bypass Critic blocker gates.")
        if action == "amend" and role not in ("PM", "EM"):
            raise HTTPException(status_code=403, detail="Access denied. Developers (DEV) cannot submit PRD amendments.")

        amended_prd = request.amended_prd or request.comments or request.feedback
        if action == "amend" and not amended_prd:
            raise HTTPException(status_code=400, detail="Amended PRD content (amended_prd or feedback comments) is required for 'amend' action.")
            
        resume_payload = {
            "action": action,
            "amended_prd": amended_prd
        }
    else:
        # Default human_approval_required
        if role != "EM":
            raise HTTPException(status_code=403, detail="Access denied. Only Engineering Managers (EM) can approve or revise the sprint backlog.")
        decision = request.decision
        if decision is None and request.status:
            status_val = request.status.lower()
            if "approve" in status_val or status_val == "approved":
                decision = "approve"
            elif "revise" in status_val or status_val == "revision":
                decision = "revise"
                
        if decision is None:
            raise HTTPException(status_code=400, detail="Could not determine decision from request payload.")
            
        comments = request.comments or request.feedback or ""
        
        resume_payload = {
            "decision": decision,
            "comments": comments
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
    
    return {"status": "RESUMING"}

@app.post("/api/v1/plan/{thread_id}/change-request")
async def create_change_request(thread_id: str, request: ChangeRequestPayload, role: str = Depends(get_current_role), org_id: str = Depends(get_current_org)):
    if role != "DEV":
        raise HTTPException(status_code=403, detail="Access denied. Only Developers (DEV) can submit change requests.")
        
    # Verify organization ownership of thread
    try:
        history = await db_manager.get_project_history(thread_id, org_id=org_id)
        if not history:
            raise HTTPException(status_code=404, detail="Session not found in this organization.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        request_id = await db_manager.create_change_request(
            thread_id=thread_id,
            ticket_key=request.ticket_key,
            developer_name=request.developer_name,
            original_points=request.original_points,
            original_description=request.original_description,
            requested_points=request.requested_points,
            requested_description=request.requested_description
        )
        return {"status": "SUCCESS", "request_id": request_id}
    except Exception as e:
        logger.error(f"[API] Failed to create change request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/plan/{thread_id}/change-requests")
async def get_change_requests(thread_id: str, org_id: str = Depends(get_current_org)):
    # Verify organization ownership of thread
    try:
        history = await db_manager.get_project_history(thread_id, org_id=org_id)
        if not history:
            raise HTTPException(status_code=404, detail="Session not found in this organization.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        requests = await db_manager.get_change_requests(thread_id)
        return {"change_requests": requests}
    except Exception as e:
        logger.error(f"[API] Failed to get change requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/plan/{thread_id}/change-request/{request_id}")
async def resolve_change_request(thread_id: str, request_id: int, request: ResolveChangeRequestPayload, role: str = Depends(get_current_role), org_id: str = Depends(get_current_org)):
    if role != "EM":
        raise HTTPException(status_code=403, detail="Access denied. Only Engineering Managers (EM) can resolve change requests.")
        
    # Verify organization ownership of thread
    try:
        history = await db_manager.get_project_history(thread_id, org_id=org_id)
        if not history:
            raise HTTPException(status_code=404, detail="Session not found in this organization.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        await db_manager.resolve_change_request(request_id, request.status)
        return {"status": "SUCCESS", "message": f"Change request {request_id} resolved to {request.status}"}
    except Exception as e:
        logger.error(f"[API] Failed to resolve change request {request_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/projects")
async def list_projects(org_id: str = Depends(get_current_org)):
    try:
        projects = await db_manager.list_project_history(limit=50, org_id=org_id)
        return {"projects": projects}
    except Exception as e:
        logger.error(f"[DB] Failed to list projects: {e}")
        return {"projects": []}
