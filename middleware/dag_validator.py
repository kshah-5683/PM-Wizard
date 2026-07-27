from typing import List, Dict, Any, Tuple

def validate_and_sanitize_dag(tickets: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Validates parent_key and blocked_by relationships across generated Jira tickets.
    1. Prunes orphan parent_key and blocked_by references to non-existent keys.
    2. Detects and breaks circular dependency cycles (e.g. A blocked by B, B blocked by A).
    Returns (sanitized_tickets, warnings).
    """
    if not tickets:
        return tickets, []

    sanitized = [dict(t) for t in tickets]
    valid_keys = {t.get("key") or t.get("ticket_key") for t in sanitized if t.get("key") or t.get("ticket_key")}
    warnings = []

    # 1. Prune Orphan References
    for t in sanitized:
        key = t.get("key") or t.get("ticket_key")
        
        # Parent Key Check
        parent = t.get("parent_key")
        if parent and parent not in valid_keys:
            t["parent_key"] = None
            warnings.append({
                "code": "ORPHAN_PARENT",
                "message": f"Parent key '{parent}' for ticket '{key}' does not exist in plan. Cleared parent reference."
            })
            
        # Blocked By Check
        blocked_by = t.get("blocked_by") or []
        cleaned_blocked = []
        for blocker in blocked_by:
            if blocker in valid_keys and blocker != key:
                cleaned_blocked.append(blocker)
            elif blocker not in valid_keys:
                warnings.append({
                    "code": "ORPHAN_BLOCKER",
                    "message": f"Blocker key '{blocker}' for ticket '{key}' does not exist in plan. Pruned reference."
                })
        t["blocked_by"] = cleaned_blocked

    # 2. Circular Dependency Cycle Detection & Pruning using DFS
    # Graph edge: u -> v means u is blocked by v
    adj = {}
    for t in sanitized:
        key = t.get("key") or t.get("ticket_key")
        adj[key] = list(t.get("blocked_by") or [])

    visited = {}  # 0: unvisited, 1: visiting, 2: visited
    for k in valid_keys:
        visited[k] = 0

    cycles_pruned = set()

    def dfs(node: str, path: List[str]):
        visited[node] = 1  # Mark visiting
        path.append(node)

        neighbors = list(adj.get(node, []))
        for neighbor in neighbors:
            if visited.get(neighbor) == 1:
                # Cycle detected! Break edge node -> neighbor
                cycle_pair = (node, neighbor)
                if cycle_pair not in cycles_pruned:
                    cycles_pruned.add(cycle_pair)
                    adj[node].remove(neighbor)
                    warnings.append({
                        "code": "CIRCULAR_DEPENDENCY",
                        "message": f"Circular dependency detected between '{node}' and '{neighbor}'. Pruned link from '{node}'."
                    })
            elif visited.get(neighbor) == 0:
                dfs(neighbor, path)

        path.pop()
        visited[node] = 2  # Mark visited

    for key in list(valid_keys):
        if visited.get(key) == 0:
            dfs(key, [])

    # Apply pruned blocked_by lists back to tickets
    for t in sanitized:
        key = t.get("key") or t.get("ticket_key")
        if key in adj:
            t["blocked_by"] = adj[key]

    return sanitized, warnings
