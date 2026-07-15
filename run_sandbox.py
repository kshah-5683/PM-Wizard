import os
import json
import uuid
from dotenv import load_dotenv
from langgraph.types import Command
from middleware.graph import graph

# Load environment variables
load_dotenv()

async def run_local_sandbox():
    print("==================================================")
    print("Starting PM Middleware Local Sandbox Stateful Loop")
    print("==================================================")
    
    raw_prd_content = (
        "# Project: Stripe checkout subscription integration\n\n"
        "We need to add a checkout form to our web app so users can purchase our Premium Subscriptions. "
        "The system should present payment options, load Stripe Elements securely, and handle payment events.\n\n"
        "### Subscription Pricing Structure\n"
        "| Tier Name | Price | Features Included |\n"
        "| :--- | :--- | :--- |\n"
        "| Basic Tier | $5/month | Single user access, basic product reports |\n"
        "| Premium Tier | $15/month | Up to 5 users, custom webhooks, premium analytics |\n"
        "| Enterprise Tier | $99/month | Unlimited users, dedicated DB support, 24/7 SLA |\n"
    )
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "raw_prd": raw_prd_content,
        "codebase_summary": None,
        "missing_edge_cases": None,
        "jira_tickets": None,
        "em_approval_status": "PENDING",
        "em_feedback_comments": None,
        "attempt_count": 0
    }
    
    # Execute graph up to the first interrupt
    print("\n--- Running AI Ingester -> Critic -> Estimator loop ---")
    await graph.ainvoke(initial_state, config=config)
    
    # Poll State Snapshot from Checkpointer
    snapshot = await graph.aget_state(config)
    
    while snapshot.next:
        print("\n==================================================")
        print("ENGINEERING MANAGER DECISION PORTAL:")
        print("1. Approve and Push to Jira")
        print("2. Request Revision (Provide Comments)")
        choice = input("Enter choice (1 or 2): ").strip()
        
        if choice == "1":
            print("\nResuming workflow with EM approval...")
            await graph.ainvoke(
                Command(resume={"decision": "approve", "comments": ""}),
                config=config
            )
        elif choice == "2":
            comments = input("\nEnter feedback / revision instructions: ").strip()
            print("\nResuming workflow with revision feedback...")
            await graph.ainvoke(
                Command(resume={"decision": "revise", "comments": comments}),
                config=config
            )
        else:
            print("Invalid input, please enter 1 or 2.")
            continue
            
        snapshot = await graph.aget_state(config)
        
    print("\n==================================================")
    final_snapshot = await graph.aget_state(config)
    final_values = final_snapshot.values
    print(f"Workflow Completed! Final approval status: {final_values.get('em_approval_status')}")
    print("==================================================")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_local_sandbox())
