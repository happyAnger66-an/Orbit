"""DAG orchestration spec: validation and normalization (stable JSON for Web + RPC)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


MAX_UPSTREAM_SNIPPET = 24_000
_DEFAULT_PARALLELISM = 4


def normalize_dag_dict(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a canonical dict with keys: nodes, parallelism. Raises ValueError on bad input."""
    if not raw or not isinstance(raw, dict):
        raise ValueError("dag must be an object")
    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("dag.nodes must be a non-empty array")
    nodes_out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for i, item in enumerate(raw_nodes):
        if not isinstance(item, dict):
            raise ValueError(f"dag.nodes[{i}] must be an object")
        nid = str(item.get("id") or "").strip()
        if not nid:
            raise ValueError(f"dag.nodes[{i}].id is required")
        if nid in seen:
            raise ValueError(f"duplicate dag node id: {nid}")
        seen.add(nid)
        aid = str(item.get("agentId") or item.get("agent_id") or "").strip()
        if not aid:
            raise ValueError(f"dag.nodes[{nid}].agentId is required")
        raw_deps = item.get("dependsOn")
        if raw_deps is None:
            raw_deps = item.get("depends_on")
        deps: List[str] = []
        if isinstance(raw_deps, list):
            for d in raw_deps:
                s = str(d).strip()
                if s:
                    deps.append(s)
        title = item.get("title")
        title_s = str(title).strip() if title is not None else ""
        node: Dict[str, Any] = {"id": nid, "agentId": aid, "dependsOn": deps}
        if title_s:
            node["title"] = title_s
        pos = item.get("position")
        if isinstance(pos, dict):
            px = pos.get("x")
            py = pos.get("y")
            try:
                node["position"] = {"x": float(px), "y": float(py)}
            except (TypeError, ValueError):
                pass
        nodes_out.append(node)

    for n in nodes_out:
        for d in n["dependsOn"]:
            if d not in seen:
                raise ValueError(f"dag node {n['id']!r} depends on unknown id {d!r}")
        if n["id"] in n["dependsOn"]:
            raise ValueError(f"dag node {n['id']!r} cannot depend on itself")

    par = raw.get("parallelism")
    try:
        p = int(par) if par is not None and str(par).strip() else _DEFAULT_PARALLELISM
    except (TypeError, ValueError):
        p = _DEFAULT_PARALLELISM
    p = max(1, min(32, p))

    order = topological_order(nodes_out)
    if order is None:
        raise ValueError("dag contains a cycle or unsatisfiable dependencies")

    return {"nodes": nodes_out, "parallelism": p, "topologicalOrder": order}


def topological_order(nodes: List[Dict[str, Any]]) -> Optional[List[str]]:
    """Kahn topological sort; return None if cycle."""
    ids = [str(n["id"]) for n in nodes]
    id_set = set(ids)
    children: Dict[str, List[str]] = {i: [] for i in ids}
    indegree: Dict[str, int] = {i: 0 for i in ids}
    for n in nodes:
        nid = str(n["id"])
        for d in n.get("dependsOn") or []:
            ds = str(d)
            if ds in id_set:
                children[ds].append(nid)
                indegree[nid] += 1
    q = [i for i in ids if indegree[i] == 0]
    out: List[str] = []
    while q:
        cur = q.pop(0)
        out.append(cur)
        for ch in children.get(cur) or []:
            indegree[ch] -= 1
            if indegree[ch] == 0:
                q.append(ch)
    if len(out) != len(ids):
        return None
    return out
