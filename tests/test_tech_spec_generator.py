import pytest
from middleware.tech_spec_generator import generate_ticket_tech_spec, TechSpecOutput

@pytest.mark.asyncio
async def test_tech_spec_generator_output(monkeypatch):
    test_ticket = {
        "key": "TICKET-101",
        "type": "Story",
        "title": "Build User Profile Modal",
        "description": "Create interactive modal for user profile settings",
        "estimation": 5
    }
    
    # Run tech spec generator with mock fallback or structured model
    spec = await generate_ticket_tech_spec(
        ticket=test_ticket,
        codebase_summary="Next.js frontend with TailwindCSS and FastAPI backend.",
        raw_prd="# User Profile PRD\nAllow users to edit profile and avatar."
    )
    
    assert spec["ticket_key"] == "TICKET-101"
    assert isinstance(spec["target_file_paths"], list)
    assert isinstance(spec["developer_checklist"], list)
    assert len(spec["target_file_paths"]) > 0
    assert len(spec["developer_checklist"]) > 0
    assert "### 🛠️ Developer Technical Specification" in spec["markdown_summary"]
