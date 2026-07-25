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
    
    # 3. Parallel codebase scan and repository profiling
    try:
        codebase_task = asyncio.to_thread(inspect_codebase, raw_prd, None, keywords)
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
        "prd_images_context": prd_images_context
    }
