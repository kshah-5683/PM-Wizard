import asyncio
import os
import json
import re
from middleware.state import AgentState
from middleware.nodes.codebase_inspector import inspect_codebase, extract_technology_keywords

def has_visual_assets(prd_text: str) -> bool:
    """
    Checks if there are markdown image tags or common image extensions in the PRD text.
    """
    pattern = r'!\[.*?\]\(.*?\)|https?://\S+\.(?:png|jpe?g|gif|webp|svg)'
    return bool(re.search(pattern, prd_text, re.IGNORECASE))

def profile_repository(project_root: str = None) -> str:
    """
    Scans the repository root for lockfiles, package.json dependencies,
    and README headers to generate a tech stack and workspace profile.
    """
    if project_root is None:
        from middleware.config import PROJECT_ROOT
        project_root = PROJECT_ROOT
        
    project_root = os.path.abspath(project_root)
    if not os.path.exists(project_root):
        return "Repository root path does not exist."

    detected_lockfiles = []
    lockfiles = {
        "package-lock.json": "npm (Node.js)",
        "yarn.lock": "yarn (Node.js)",
        "pnpm-lock.yaml": "pnpm (Node.js)",
        "Cargo.lock": "Cargo (Rust)",
        "go.sum": "Go modules",
        "requirements.txt": "pip (Python)",
        "poetry.lock": "Poetry (Python)",
        "Gemfile.lock": "Bundler (Ruby)",
        "composer.lock": "Composer (PHP)"
    }
    
    for filename, desc in lockfiles.items():
        if os.path.exists(os.path.join(project_root, filename)):
            detected_lockfiles.append(desc)

    frameworks = []
    
    # Check package.json for dependencies
    package_json_path = os.path.join(project_root, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
                deps = pkg_data.get("dependencies", {})
                dev_deps = pkg_data.get("devDependencies", {})
                all_deps = {**deps, **dev_deps}
                
                # Check for popular frameworks
                for lib in ["react", "next", "vue", "svelte", "express", "fastapi", "django", "flask", "spring", "laravel"]:
                    if lib in all_deps or any(lib in k for k in all_deps.keys()):
                        frameworks.append(lib.capitalize())
        except Exception:
            pass

    # Read README.md for technology summary (up to 5000 chars)
    readme_summary = ""
    readme_path = os.path.join(project_root, "README.md")
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                readme_content = f.read(5000)
                readme_lines = readme_content.split("\n")
                readme_headers = [line.strip("# ").strip() for line in readme_lines if line.startswith("#")][:3]
                if readme_headers:
                    readme_summary = f"README Headers: {', '.join(readme_headers)}"
        except Exception:
            pass

    other_tech = []
    if os.path.exists(os.path.join(project_root, "Dockerfile")) or os.path.exists(os.path.join(project_root, "docker-compose.yml")):
        other_tech.append("Docker")
    if os.path.exists(os.path.join(project_root, "tsconfig.json")):
        other_tech.append("TypeScript")

    # Construct summary
    summary_parts = []
    if detected_lockfiles:
        summary_parts.append(f"Lockfiles: {', '.join(detected_lockfiles)}")
    if frameworks:
        summary_parts.append(f"Frameworks: {', '.join(frameworks)}")
    if other_tech:
        summary_parts.append(f"Other: {', '.join(other_tech)}")
    if readme_summary:
        summary_parts.append(readme_summary)
        
    if not summary_parts:
        return "Generic Codebase (No standard lockfiles or package.json detected)"
        
    return " | ".join(summary_parts)

async def generate_greenfield_blueprint(raw_prd: str, keywords: list) -> str:
    """
    Generates a foundational system architecture, folder structure, and database schema recommendations
    for Greenfield projects based on the PRD and key technology concepts.
    """
    from middleware.config import PRIMARY_MODEL
    from middleware.llm import aresilient_completion
    
    system_prompt = (
        "You are a Principal Software Architect. The user is starting a brand new project (Greenfield Mode) from scratch.\n"
        "Analyze the provided Product Requirements Document (PRD) and tech stack keywords.\n"
        "Generate a foundational design blueprint containing:\n"
        "1. Recommended System Architecture (monolith, serverless, SPA/Backend structure, etc.).\n"
        "2. Database Schema Recommendations (tables, relations, primary/foreign keys, types) suitable for Postgres/Supabase.\n"
        "3. Recommended Folder Structure / Repository Layout.\n"
        "4. Technology stack alignment.\n"
        "Make it extremely structured, concise, and professional. Return markdown format."
    )
    
    user_prompt = f"PRD:\n{raw_prd}\n\nKeywords: {', '.join(keywords) if keywords else 'None'}"
    
    try:
        response = await aresilient_completion(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Ingestion] Greenfield blueprint generation failed: {e}")
        return "Greenfield Mode: Recommended architecture and database schema blueprint placeholder."

async def ingestion_node(state: AgentState):
    print("\n--- [Ingestion Node] Ingesting Upstream PRD ---")
    print("Ingested PRD Content successfully.")
    
    raw_prd = state.get("raw_prd", "")
    
    # 1. Visual model bypass check
    if has_visual_assets(raw_prd):
        # Extract images found
        urls = re.findall(r'!\[.*?\]\(((?:https?://)?\S+\.(?:png|jpe?g|gif|webp|svg))\)|((?:https?://)?\S+\.(?:png|jpe?g|gif|webp|svg))', raw_prd, re.IGNORECASE)
        image_urls = []
        for match in urls:
            url = match[0] or match[1]
            if url:
                image_urls.append(url)
        prd_images_context = [
            {"image_url": url, "description": f"Visual asset at {url} analyzed. Wireframe/UI description placeholder."}
            for url in image_urls
        ]
        print(f"[Ingestion] Detected {len(prd_images_context)} visual asset(s). Mapped placeholder contexts.")
    else:
        print("[Ingestion] No visual media detected. Skipping visual analysis node (bypass logic).")
        prd_images_context = []

    # 2. Dynamic Keyword Extraction
    try:
        keywords = await extract_technology_keywords(raw_prd)
        print(f"[Ingestion] Dynamically extracted technology keywords: {', '.join(keywords)}")
    except Exception as e:
        print(f"[Ingestion] Failed to extract technology keywords: {e}. Falling back to static list.")
        keywords = None
    
    # 3. Retrieve GitHub credentials & repo if available
    user_id = state.get("user_id")
    org_id = state.get("org_id", "default-org")
    github_repo = state.get("github_repo")
    github_token = None
    
    if user_id:
        try:
            from middleware.oauth import get_valid_token
            github_token = await get_valid_token(user_id, "github", org_id)
            
            # Fallback auto-detection if GitHub is connected but no specific repo is selected
            if github_token and not github_repo:
                import httpx
                headers = {
                    "Authorization": f"token {github_token}",
                    "Accept": "application/json",
                    "User-Agent": "PM-Wizard-App"
                }
                async with httpx.AsyncClient() as client:
                    res = await client.get("https://api.github.com/user/repos?sort=updated&per_page=1", headers=headers)
                    if res.is_success:
                        repos = res.json()
                        if repos:
                            github_repo = repos[0].get("full_name")
                            print(f"[Ingestion] Auto-detected default GitHub repository: {github_repo}")
        except Exception as e:
            print(f"[Ingestion] Failed to resolve GitHub repository details: {e}")

    # Determine project_mode: Greenfield vs Brownfield
    project_mode = state.get("project_mode")
    if not project_mode:
        if github_repo:
            project_mode = "BROWNFIELD"
        else:
            project_mode = "GREENFIELD"
    print(f"[Ingestion] Planning Mode resolved to: {project_mode}")

    # 4. Parallel codebase scan and repository profiling OR Greenfield architecture generation
    if project_mode == "GREENFIELD":
        print("[Ingestion] Greenfield Mode active. Skipping codebase inspection and generating foundational architecture blueprint...")
        try:
            codebase_summary = await generate_greenfield_blueprint(raw_prd, keywords)
            workspace_profile = "Greenfield Project: Zero-to-One Lifecycle (No repository or codebase template connected)"
            print("[Ingestion] Greenfield architectural blueprint generated.")
        except Exception as e:
            print(f"[Ingestion] Failed to generate Greenfield blueprint ({e}), continuing with defaults.")
            codebase_summary = "Greenfield Mode: Recommended architecture and database schema blueprint placeholder."
            workspace_profile = "Greenfield Project: Zero-to-One Lifecycle"
    else:
        try:
            # inspect_codebase is async, profile_repository is sync (CPU-bound local scan fallback)
            codebase_task = inspect_codebase(raw_prd, None, keywords, github_repo, github_token)
            profile_task = asyncio.to_thread(profile_repository)
            
            codebase_summary, workspace_profile = await asyncio.gather(codebase_task, profile_task)
            print(f"[Ingestion] Codebase scan & repository profiling completed.")
        except Exception as e:
            print(f"[Ingestion] Ingestion tasks failed ({e}), continuing with defaults.")
            codebase_summary = None
            workspace_profile = "Workspace profiling failed."
        
    return {
        "attempt_count": state.get("attempt_count", 0),
        "codebase_summary": codebase_summary,
        "workspace_profile": workspace_profile,
        "prd_images_context": prd_images_context,
        "github_repo": github_repo,
        "project_mode": project_mode
    }

