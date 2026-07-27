import os
import json
import asyncio
from typing import List, Dict, Set, Optional
import httpx
from middleware.config import PROJECT_ROOT
from middleware.llm import aresilient_completion

KEYWORDS = [
    "oauth", "stripe", "webhook", "postgres", "database", "redis", 
    "graphql", "rest", "api", "auth", "jwt", "payment", 
    "notification", "email", "s3", "upload", "websocket", "cron", "migration"
]

async def extract_technology_keywords(raw_prd: str) -> List[str]:
    """
    Calls the lightweight LLM to extract technology and architectural keywords from the PRD.
    """
    from middleware.config import LIGHTWEIGHT_MODEL
    
    system_prompt = (
        "You are an expert software architect. Analyze the provided PRD text and extract a list "
        "of key technology keywords, programming languages, database names, communication protocols, "
        "or service integrations mentioned (e.g. 'postgres', 'redis', 'stripe', 'oauth', 'jwt', 'websocket'). "
        "Respond ONLY with a JSON list of strings. Do not include markdown wraps."
    )
    
    try:
        response = await aresilient_completion(
            model=LIGHTWEIGHT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"PRD content:\n{raw_prd}"}
            ]
        )
        content = response.choices[0].message.content.strip()
        # Clean up any potential markdown wraps
        if content.startswith("```json"):
            content = content.split("```json", 1)[1].rsplit("```", 1)[0].strip()
        elif content.startswith("```"):
            content = content.split("```", 1)[1].rsplit("```", 1)[0].strip()
            
        keywords = json.loads(content)
        if isinstance(keywords, list):
            # Clean and normalize keywords
            return [str(kw).strip().lower() for kw in keywords if kw]
    except Exception as e:
        print(f"[Codebase Inspector] Failed to dynamically extract keywords ({e}). Falling back to static list.")
        
    # Fallback to static list
    return KEYWORDS

def inspect_codebase_local(raw_prd: str, project_root: str = None, keywords: List[str] = None) -> str:
    """
    Performs keyword-based JIT codebase inspection locally. Walks the project root,
    scans code files for keywords matched in the PRD, and returns a formatted markdown summary.
    """
    if project_root is None:
        project_root = PROJECT_ROOT
        
    project_root = os.path.abspath(project_root)
    if not os.path.exists(project_root):
        return f"Error: Project root path '{project_root}' does not exist."

    # 1. Keyword extraction
    if keywords is None:
        prd_lower = raw_prd.lower()
        matched_keywords = [kw for kw in KEYWORDS if kw in prd_lower]
    else:
        prd_lower = raw_prd.lower()
        matched_keywords = [kw for kw in keywords if kw in prd_lower]
        if not matched_keywords:
            matched_keywords = [kw for kw in keywords if kw in KEYWORDS or kw in prd_lower]
    
    if not matched_keywords:
        return "No relevant technology keywords detected in the PRD for JIT codebase inspection."
        
    # 2. Directory walk and file scanning
    excluded_dirs = {".venv", "node_modules", ".next", ".git", "__pycache__", ".env", ".cache"}
    allowed_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".sql", ".yaml", ".yml", ".json"}
    
    keyword_to_files = {kw: [] for kw in matched_keywords}
    all_matched_files = set()
    
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        
        for file in files:
            _, ext = os.path.splitext(file)
            if ext.lower() not in allowed_extensions:
                continue
                
            filepath = os.path.join(root, file)
            try:
                if os.path.getsize(filepath) > 100 * 1024:  # 100KB limit
                    continue
                    
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    
                file_matched = False
                rel_path = os.path.relpath(filepath, project_root).replace(os.sep, '/')
                for kw in matched_keywords:
                    if kw in content:
                        keyword_to_files[kw].append(rel_path)
                        file_matched = True
                        
                if file_matched:
                    all_matched_files.add(rel_path)
            except Exception:
                continue

    if not all_matched_files:
        return f"Detected keywords: {', '.join(matched_keywords)}, but no matching codebase files were found."

    # Top 20 files matching cap
    total_matched = len(all_matched_files)
    truncated_files_count = 0
    if total_matched > 20:
        sorted_files = sorted(list(all_matched_files))
        kept_files = set(sorted_files[:20])
        truncated_files_count = total_matched - 20
        for kw in matched_keywords:
            keyword_to_files[kw] = [f for f in keyword_to_files[kw] if f in kept_files]
        all_matched_files = kept_files

    # 4. Summary generation
    summary_lines = []
    summary_lines.append("### Codebase Context Summary")
    summary_lines.append(f"**Detected Keywords in PRD:** {', '.join(matched_keywords)}")
    summary_lines.append("\n**Matched Files by Keyword:**")
    
    for kw in matched_keywords:
        files_for_kw = sorted(keyword_to_files[kw])
        if files_for_kw:
            summary_lines.append(f"- **{kw}**:")
            for f in files_for_kw[:10]:
                summary_lines.append(f"  - 📄 `{f}`")
            if len(files_for_kw) > 10:
                summary_lines.append(f"  - ... and {len(files_for_kw) - 10} more")
                
    summary_lines.append("\n**Affected Directories Structure:**")
    
    # Build tree
    dirs = {}
    for path in sorted(list(all_matched_files)):
        parts = path.split('/')
        if len(parts) == 1:
            dirs.setdefault("", []).append(parts[0])
        else:
            dir_path = "/".join(parts[:-1])
            dirs.setdefault(dir_path, []).append(parts[-1])
            
    tree_lines = []
    if "" in dirs:
        for file in dirs[""]:
            tree_lines.append(f"- 📄 {file}")
            
    for dir_path in sorted(dirs.keys()):
        if dir_path == "":
            continue
        tree_lines.append(f"- 📁 {dir_path}/")
        for file in sorted(dirs[dir_path]):
            tree_lines.append(f"  - 📄 {file}")
            
    summary_lines.extend(tree_lines)
    summary = "\n".join(summary_lines)
    
    # 5. Output length cap (2000 chars limit)
    if len(summary) > 2000 or truncated_files_count > 0:
        extra_count = truncated_files_count
        if len(summary) > 2000:
            trunc_msg = f"\n\n[...truncated, {extra_count} more files matched]"
            summary = summary[:2000 - len(trunc_msg)] + trunc_msg
        else:
            summary += f"\n\n[...truncated, {extra_count} more files matched]"
        
    return summary

async def inspect_codebase_remote(raw_prd: str, github_repo: str, access_token: str, keywords: List[str] = None) -> str:
    """
    Performs keyword-based JIT codebase inspection remotely using GitHub's recursive Trees API and raw file fetches.
    """
    # 1. Keywords extraction
    if keywords is None:
        prd_lower = raw_prd.lower()
        matched_keywords = [kw for kw in KEYWORDS if kw in prd_lower]
    else:
        prd_lower = raw_prd.lower()
        matched_keywords = [kw for kw in keywords if kw in prd_lower]
        if not matched_keywords:
            matched_keywords = [kw for kw in keywords if kw in KEYWORDS or kw in prd_lower]
            
    if not matched_keywords:
        return "No relevant technology keywords detected in the PRD for JIT codebase inspection."

    # 2. Query GitHub recursive tree API to get file listing
    branch = "main"
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/json",
        "User-Agent": "PM-Wizard-App"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            repo_url = f"https://api.github.com/repos/{github_repo}"
            res_repo = await client.get(repo_url, headers=headers)
            if res_repo.is_success:
                branch = res_repo.json().get("default_branch", "main")
                
            tree_url = f"https://api.github.com/repos/{github_repo}/git/trees/{branch}?recursive=1"
            res_tree = await client.get(tree_url, headers=headers)
            if not res_tree.is_success:
                return f"Error: Failed to fetch directory structure from GitHub repository '{github_repo}'. Status: {res_tree.status_code}"
                
            tree_data = res_tree.json()
            tree_entries = tree_data.get("tree", [])
        except Exception as e:
            return f"Error connecting to GitHub repository '{github_repo}': {e}"

    # 3. Filter files by extensions and folders
    excluded_dirs = {".venv", "node_modules", ".next", ".git", "__pycache__", ".env", ".cache"}
    allowed_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".sql", ".yaml", ".yml", ".json"}
    
    candidate_files = []
    for entry in tree_entries:
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        parts = path.split('/')
        if any(p in excluded_dirs for p in parts):
            continue
        _, ext = os.path.splitext(path)
        if ext.lower() not in allowed_extensions:
            continue
        size = entry.get("size", 0)
        if size > 100 * 1024:
            continue
        candidate_files.append(path)

    # 4. Fetch content for candidate files to scan keywords concurrently
    # Cap at 20 files to prevent API rate limits or excessive concurrent requests
    # Sort candidate files so that files with keywords in their paths are processed first
    def get_priority(p: str) -> int:
        p_lower = p.lower()
        priority = 0
        for kw in matched_keywords:
            if kw in p_lower:
                priority += 10
        if p.endswith((".py", ".ts", ".js", ".tsx", ".jsx")):
            priority += 2
        return priority
        
    candidate_files.sort(key=get_priority, reverse=True)
    candidate_paths = candidate_files[:20]
    
    matched_files = set()
    keyword_to_files = {kw: [] for kw in matched_keywords}
    
    async def fetch_and_scan(client_conn, path: str) -> Optional[dict]:
        raw_url = f"https://raw.githubusercontent.com/{github_repo}/{branch}/{path}"
        try:
            res_content = await client_conn.get(raw_url, headers=headers)
            if res_content.is_success:
                return {"path": path, "content": res_content.text.lower()}
        except Exception:
            pass
        return None

    async with httpx.AsyncClient() as client:
        tasks = [fetch_and_scan(client, path) for path in candidate_paths]
        results = await asyncio.gather(*tasks)
        
    for res in results:
        if res:
            path = res["path"]
            content = res["content"]
            file_matched = False
            for kw in matched_keywords:
                if kw in content:
                    keyword_to_files[kw].append(path)
                    file_matched = True
            if file_matched:
                matched_files.add(path)

    if not matched_files:
        return f"Detected keywords: {', '.join(matched_keywords)} inside GitHub repository '{github_repo}', but no matching file contents were found."

    # Top 20 files matching cap
    total_matched = len(matched_files)
    truncated_files_count = 0
    if total_matched > 20:
        sorted_files = sorted(list(matched_files))
        kept_files = set(sorted_files[:20])
        truncated_files_count = total_matched - 20
        for kw in matched_keywords:
            keyword_to_files[kw] = [f for f in keyword_to_files[kw] if f in kept_files]
        matched_files = kept_files

    summary_lines = []
    summary_lines.append("### Codebase Context Summary (GitHub Remote)")
    summary_lines.append(f"**Repository:** `{github_repo}` (branch: `{branch}`)")
    summary_lines.append(f"**Detected Keywords in PRD:** {', '.join(matched_keywords)}")
    summary_lines.append("\n**Matched Files by Keyword:**")
    
    for kw in matched_keywords:
        files_for_kw = sorted(keyword_to_files[kw])
        if files_for_kw:
            summary_lines.append(f"- **{kw}**:")
            for f in files_for_kw[:10]:
                summary_lines.append(f"  - 📄 `{f}`")
            if len(files_for_kw) > 10:
                summary_lines.append(f"  - ... and {len(files_for_kw) - 10} more")
                
    summary_lines.append("\n**Affected Directories Structure:**")
    
    dirs = {}
    for path in sorted(list(matched_files)):
        parts = path.split('/')
        if len(parts) == 1:
            dirs.setdefault("", []).append(parts[0])
        else:
            dir_path = "/".join(parts[:-1])
            dirs.setdefault(dir_path, []).append(parts[-1])
            
    tree_lines = []
    if "" in dirs:
        for file in dirs[""]:
            tree_lines.append(f"- 📄 {file}")
            
    for dir_path in sorted(dirs.keys()):
        if dir_path == "":
            continue
        tree_lines.append(f"- 📁 {dir_path}/")
        for file in sorted(dirs[dir_path]):
            tree_lines.append(f"  - 📄 {file}")
            
    summary_lines.extend(tree_lines)
    summary = "\n".join(summary_lines)
    
    if len(summary) > 2000 or truncated_files_count > 0:
        extra_count = truncated_files_count
        if len(summary) > 2000:
            trunc_msg = f"\n\n[...truncated, {extra_count} more files matched]"
            summary = summary[:2000 - len(trunc_msg)] + trunc_msg
        else:
            summary += f"\n\n[...truncated, {extra_count} more files matched]"
        
    return summary

async def inspect_codebase(
    raw_prd: str, 
    project_root: str = None, 
    keywords: List[str] = None, 
    github_repo: str = None, 
    github_token: str = None
) -> str:
    """
    Performs JIT codebase inspection. If github_repo and github_token are provided,
    it queries the remote GitHub repository. Otherwise, it performs a local keyword scan.
    """
    if github_repo and github_token:
        return await inspect_codebase_remote(raw_prd, github_repo, github_token, keywords)
    else:
        # Run local codebase scan in a thread pool to avoid blocking the asyncio event loop
        return await asyncio.to_thread(inspect_codebase_local, raw_prd, project_root, keywords)
