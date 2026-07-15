import os
from typing import List, Dict, Set
from middleware.config import PROJECT_ROOT

KEYWORDS = [
    "oauth", "stripe", "webhook", "postgres", "database", "redis", 
    "graphql", "rest", "api", "auth", "jwt", "payment", 
    "notification", "email", "s3", "upload", "websocket", "cron", "migration"
]

def inspect_codebase(raw_prd: str, project_root: str = None) -> str:
    """
    Performs keyword-based JIT codebase inspection. Walks the project root,
    scans code files for keywords matched in the PRD, and returns a formatted markdown summary.
    """
    if project_root is None:
        project_root = PROJECT_ROOT
        
    project_root = os.path.abspath(project_root)
    if not os.path.exists(project_root):
        return f"Error: Project root path '{project_root}' does not exist."

    # 1. Keyword extraction
    prd_lower = raw_prd.lower()
    matched_keywords = [kw for kw in KEYWORDS if kw in prd_lower]
    
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
