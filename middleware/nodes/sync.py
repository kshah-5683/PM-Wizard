import httpx
from typing import Optional
from middleware.state import AgentState
from middleware.database import db_manager
from middleware.rag import store_approved_tickets
from langgraph.types import RunnableConfig

def string_to_adf(text: str) -> dict:
    if not text:
        text = "No description provided."
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
        ]
    }

async def discover_story_points_field(cloud_id: str, access_token: str, client: httpx.AsyncClient) -> str:
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/field"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    try:
        res = await client.get(url, headers=headers)
        if res.is_success:
            fields = res.json()
            for f in fields:
                name = f.get("name", "").lower()
                if "story point" in name or "story points" in name:
                    return f.get("id", "customfield_10016")
    except Exception as e:
        print(f"[Jira] Error discovering story points field: {e}")
    return "customfield_10016"

async def fetch_default_jira_project(cloud_id: str, access_token: str, client: httpx.AsyncClient) -> str:
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/project"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    try:
        res = await client.get(url, headers=headers)
        if res.is_success:
            projects = res.json()
            if projects:
                return projects[0].get("key", "PROJ")
    except Exception as e:
        print(f"[Jira] Error fetching fallback project key: {e}")
    return "PROJ"

async def publish_tickets_to_jira(tickets: list, cloud_id: str, access_token: str, project_key: str = None) -> list:
    """
    Creates Epic, Story, and Subtask issues in Jira Cloud using the Atlassian OAuth credentials.
    Supports idempotency and dynamic Epic link resolution/creation.
    """
    async with httpx.AsyncClient() as client:
        # 1. Resolve project key
        if not project_key:
            project_key = await fetch_default_jira_project(cloud_id, access_token, client)
            print(f"[Jira] Resolved fallback project key: {project_key}")
            
        # 2. Discover estimation field key
        est_field = await discover_story_points_field(cloud_id, access_token, client)
        print(f"[Jira] Using estimation field: {est_field}")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        jira_keys = {}
        last_epic_key = None
        last_story_key = None
        
        # Check if any explicit Epic ticket exists in the backlog
        has_epic = any(t.get("type") == "Epic" for t in tickets)
        
        # If stories exist but no Epic exists in the plan, dynamically create a feature Epic first
        if not has_epic and any(t.get("type") == "Story" for t in tickets):
            # Check if any ticket already has a created Epic key
            existing_epic_key = next((t.get("jira_issue_id") or t.get("jira_key") for t in tickets if t.get("type") == "Epic"), None)
            if existing_epic_key:
                last_epic_key = existing_epic_key
            else:
                epic_summary = f"Feature Sprint Plan [{project_key}]"
                epic_fields = {
                    "project": {"key": project_key},
                    "summary": epic_summary,
                    "description": string_to_adf("Feature epic dynamically created for sprint plan execution."),
                    "issuetype": {"name": "Epic"}
                }
                url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue"
                try:
                    res = await client.post(url, headers=headers, json={"fields": epic_fields})
                    if res.is_success:
                        created_epic = res.json()
                        last_epic_key = created_epic.get("key")
                        print(f"[Jira] Dynamically created parent Epic: {last_epic_key}")
                    else:
                        print(f"[Jira] Warning: Failed to create dynamic Epic: {res.text}")
                except Exception as e:
                    print(f"[Jira] Exception creating dynamic Epic: {e}")

        for ticket in tickets:
            temp_key = ticket.get("key") or ticket.get("ticket_key")
            # Idempotency check: Skip if already published to Jira
            existing_id = ticket.get("jira_issue_id") or ticket.get("jira_key")
            if existing_id:
                print(f"[Jira] Skipping already published ticket [{temp_key} -> {existing_id}]")
                jira_keys[temp_key] = existing_id
                if ticket.get("type") == "Epic":
                    last_epic_key = existing_id
                elif ticket.get("type") == "Story":
                    last_story_key = existing_id
                continue
                
            ticket_type = ticket.get("type", "Story")
            summary = ticket.get("title", "")
            description = ticket.get("description", "")
            estimation = ticket.get("estimation")
            priority = ticket.get("priority", "Medium")
            parent_key_ref = ticket.get("parent_key")
            
            jira_type = "Story"
            if ticket_type == "Epic":
                jira_type = "Epic"
            elif ticket_type == "Subtask":
                jira_type = "Sub-task"
                
            fields = {
                "project": {
                    "key": project_key
                },
                "summary": summary,
                "description": string_to_adf(description),
                "issuetype": {
                    "name": jira_type
                },
                "priority": {
                    "name": priority
                }
            }
            
            if estimation is not None and jira_type in ("Story", "Epic"):
                try:
                    fields[est_field] = float(estimation)
                except (ValueError, TypeError):
                    pass
            
            # Resolve parent linking
            resolved_parent = None
            if parent_key_ref and parent_key_ref in jira_keys:
                resolved_parent = jira_keys[parent_key_ref]
            elif jira_type == "Story" and last_epic_key:
                resolved_parent = last_epic_key
            elif jira_type == "Sub-task" and last_story_key:
                resolved_parent = last_story_key

            if resolved_parent:
                fields["parent"] = {"key": resolved_parent}
                
            url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue"
            try:
                res = await client.post(url, headers=headers, json={"fields": fields})
                if res.is_success:
                    created_issue = res.json()
                    created_key = created_issue.get("key")
                    print(f"[Jira] Created {jira_type} successfully: {created_key}")
                    
                    if temp_key:
                        jira_keys[temp_key] = created_key
                    if jira_type == "Epic":
                        last_epic_key = created_key
                    elif jira_type == "Story":
                        last_story_key = created_key
                else:
                    print(f"[Jira] Failed to create {jira_type} '{summary}': {res.text}")
            except Exception as e:
                print(f"[Jira] HTTP Exception creating issue: {e}")
                
        updated_tickets = []
        for ticket in tickets:
            t_copy = dict(ticket)
            temp_key = ticket.get("key") or ticket.get("ticket_key")
            if temp_key in jira_keys:
                t_copy["jira_key"] = jira_keys[temp_key]
                t_copy["jira_issue_id"] = jira_keys[temp_key]
                t_copy["jira_url"] = f"https://api.atlassian.com/ex/jira/{cloud_id}/browse/{jira_keys[temp_key]}"
            updated_tickets.append(t_copy)
            
        return updated_tickets

async def push_to_jira_node(state: AgentState, config: RunnableConfig):
    print("\n--- [Push to Jira Node] Synchronizing Backlog ---")
    tickets = state.get("jira_tickets", []) or []
    thread_id = config.get("configurable", {}).get("thread_id")
    user_id = state.get("user_id")
    org_id = state.get("org_id", "default-org")
    jira_project_key = state.get("jira_project_key")
    
    # 1. Fetch approved Developer change requests to apply
    approved_changes = []
    if thread_id:
        try:
            all_changes = await db_manager.get_change_requests(thread_id)
            approved_changes = [c for c in all_changes if c.get("status") == "APPROVED"]
            if approved_changes:
                print(f"[Push to Jira] Found {len(approved_changes)} APPROVED developer change requests. Merging into plan...")
        except Exception as e:
            print(f"[Push to Jira] Failed to fetch change requests from DB: {e}")

    # 2. Merge changes into the tickets
    synced_tickets = []
    for ticket in tickets:
        ticket_copy = dict(ticket)
        ticket_key = ticket_copy.get("key") or ticket_copy.get("ticket_key")
        
        for cr in approved_changes:
            if cr.get("ticket_key") == ticket_key:
                print(f"  Applying change request for {ticket_key}:")
                if cr.get("requested_points") is not None:
                    print(f"    Est story points: {ticket_copy.get('estimation')} -> {cr.get('requested_points')}")
                    ticket_copy["estimation"] = cr["requested_points"]
                if cr.get("requested_description") is not None:
                    print(f"    Description: Updated to developer request")
                    ticket_copy["description"] = cr["requested_description"]
                break
        synced_tickets.append(ticket_copy)

    # 3. Publish to live Jira Cloud if credentials exist
    final_tickets = synced_tickets
    if user_id:
        try:
            integration = await db_manager.get_integration(user_id, "atlassian", org_id)
            if integration and integration.get("tenant_id"):
                cloud_id = integration["tenant_id"]
                from middleware.oauth import get_valid_token
                access_token = await get_valid_token(user_id, "atlassian", org_id)
                if access_token:
                    print(f"[Push to Jira] Publishing {len(synced_tickets)} tickets to Jira Cloud...")
                    final_tickets = await publish_tickets_to_jira(synced_tickets, cloud_id, access_token, jira_project_key)
        except Exception as e:
            print(f"[Push to Jira] Active sync failed: {e}")

    print(f"[OK] Successfully synchronized {len(final_tickets)} tickets!")
    
    # RAG feedback loop: Store approved/merged tickets in Postgres historical_tickets
    try:
        await store_approved_tickets(db_manager, final_tickets, sprint_plan_id=thread_id, org_id=org_id)
    except Exception as e:
        print(f"[Push to Jira] Failed to store approved tickets in RAG history ({e}).")
        
    return {
        "jira_tickets": final_tickets,
        "em_approval_status": "COMPLETED"
    }
