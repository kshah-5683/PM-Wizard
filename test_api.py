import time
import uuid
import sys

# Try importing requests, fallback to urllib if not installed
try:
    import requests
    USE_REQUESTS = True
except ImportError:
    import urllib.request
    import json
    USE_REQUESTS = False

API_BASE_URL = "http://127.0.0.1:8000/api/v1"

def post_req(url, data):
    if USE_REQUESTS:
        response = requests.post(url, json=data)
        return response.status_code, response.json()
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

def get_req(url):
    if USE_REQUESTS:
        response = requests.get(url)
        return response.status_code, response.json()
    else:
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

def run_test():
    print("==================================================")
    print("Starting PM Middleware API Lifecycle Test Client")
    print("==================================================")
    
    # 1. Start the planning loop
    thread_id = str(uuid.uuid4())
    print(f"\n1. Triggering planning loop for thread: {thread_id}")
    
    sample_prd = (
        "# Project: Google OAuth login integration\n\n"
        "We need to add Google OAuth login to our web app. Users should see a "
        "'Sign in with Google' button, which redirects to Google's authentication page, "
        "and handles the redirect callback securely to log them in.\n"
    )
    
    payload = {
        "raw_prd": sample_prd,
        "source_document": "https://notion.so/test-oauth-prd",
        "thread_id": thread_id
    }
    
    status_code, data = post_req(f"{API_BASE_URL}/plan/start", payload)
    if status_code != 200:
        print(f"[FAIL] Start API returned status {status_code}: {data}")
        sys.exit(1)
        
    print(f"[OK] Plan started. Initial status: {data.get('status')}")
    
    # 2. Poll for AWAITING_EM_APPROVAL status
    print("\n2. Polling status endpoint. Waiting for AI agent to pause for approval...")
    attempts = 0
    max_attempts = 30
    
    while attempts < max_attempts:
        status_code, status_data = get_req(f"{API_BASE_URL}/plan/{thread_id}/status")
        if status_code != 200:
            print(f"[FAIL] Status API returned error: {status_data}")
            sys.exit(1)
            
        current_status = status_data.get("status")
        print(f"   [Poll {attempts+1}] Status: {current_status}")
        
        if current_status == "AWAITING_EM_APPROVAL":
            print("\n--- AI Agent Paused & Awaiting Review ---")
            print(f"Title: {status_data.get('title')}")
            print(f"Metrics: {status_data.get('metrics')}")
            print("\nDraft Tickets:")
            tickets = status_data.get("draft_tickets") or []
            for t in tickets:
                print(f" - [{t.get('key')}] ({t.get('type')}) {t.get('title')} - Estimation: {t.get('estimation')} pts")
            break
            
        elif current_status == "FAILED":
            print("[FAIL] The planning process failed.")
            sys.exit(1)
            
        time.sleep(3)
        attempts += 1
        
    if attempts >= max_attempts:
        print("[FAIL] Polling timed out waiting for EM approval state.")
        sys.exit(1)
        
    # 3. Resume the plan (Decision point)
    print("\n==================================================")
    print("DECISION PORTAL (Interactive Simulation):")
    print("1. Approve & Sync (Pushes to Jira)")
    print("2. Request Revision (Prompts AI to regenerate)")
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        resume_payload = {"decision": "approve", "comments": "Looks perfect, go ahead!"}
    else:
        comments = input("Provide revision comments for the AI: ")
        resume_payload = {"decision": "revise", "comments": comments}
        
    print(f"\n3. Sending resume decision to API...")
    status_code, resume_data = post_req(f"{API_BASE_URL}/plan/{thread_id}/resume", resume_payload)
    if status_code != 200:
        print(f"[FAIL] Resume API returned error: {resume_data}")
        sys.exit(1)
        
    print(f"[OK] Resume command sent successfully: {resume_data}")
    
    # 4. Final polling loop
    print("\n4. Polling for final completion status...")
    attempts = 0
    while attempts < max_attempts:
        status_code, status_data = get_req(f"{API_BASE_URL}/plan/{thread_id}/status")
        current_status = status_data.get("status")
        print(f"   [Poll {attempts+1}] Status: {current_status}")
        
        if current_status in ("COMPLETED", "COMPLETED_SYNCED"):
            print(f"\n[SUCCESS] Planning loop completed fully! Final Status: {current_status}")
            sys.exit(0)
        elif current_status == "FAILED":
            print("[FAIL] The planning process failed during resume execution.")
            sys.exit(1)
            
        time.sleep(3)
        attempts += 1

if __name__ == "__main__":
    run_test()
