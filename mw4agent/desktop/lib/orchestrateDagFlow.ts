/**
 * DAG ↔ @xyflow/react 转换（与网关 dag_spec 语义一致：边 source→target 表示 target dependsOn source）。
 */

import type { Edge, Node } from "@xyflow/react";

import type { OrchestrateDagSpec } from "@/lib/gateway";

export type DagNodeData = {
  agentId: string;
  title: string;
  listedAgents: { agentId: string }[];
};

export const DAG_AGENT_NODE_TYPE = "dagAgent" as const;

export function specToFlow(spec: OrchestrateDagSpec): { nodes: Node<DagNodeData>[]; edges: Edge[] } {
  const list = spec.nodes || [];
  const nodes: Node<DagNodeData>[] = list.map((n, i) => ({
    id: n.id,
    type: DAG_AGENT_NODE_TYPE,
    position: n.position ?? { x: (i % 4) * 200 + 40, y: Math.floor(i / 4) * 140 + 40 },
    data: {
      agentId: (n.agentId || "main").trim() || "main",
      title: (n.title || n.id || "").trim() || n.id,
      listedAgents: [],
    },
  }));
  const edges: Edge[] = [];
  for (const n of list) {
    const nid = n.id;
    for (const d of n.dependsOn || []) {
      const ds = String(d).trim();
      if (!ds || ds === nid) continue;
      edges.push({
        id: `e-${ds}-${nid}`,
        source: ds,
        target: nid,
        type: "smoothstep",
      });
    }
  }
  return { nodes, edges };
}

export function flowToSpec(
  nodes: Node<DagNodeData>[],
  edges: Edge[],
  parallelism: number
): OrchestrateDagSpec {
  const incoming = new Map<string, string[]>();
  for (const n of nodes) {
    incoming.set(n.id, []);
  }
  for (const e of edges) {
    const t = e.target;
    const s = e.source;
    if (!t || !s || t === s) continue;
    if (!incoming.has(t)) incoming.set(t, []);
    const arr = incoming.get(t)!;
    if (!arr.includes(s)) arr.push(s);
  }
  for (const [, arr] of incoming) {
    arr.sort();
  }
  const specNodes = [...nodes]
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((n) => {
      const d = n.data;
      return {
        id: n.id,
        agentId: (d?.agentId || "main").trim() || "main",
        title: (d?.title || n.id).trim() || n.id,
        dependsOn: incoming.get(n.id) || [],
        position: { x: n.position.x, y: n.position.y },
      };
    });
  const p = Math.max(1, Math.min(32, Math.floor(parallelism) || 4));
  return { nodes: specNodes, parallelism: p };
}

/** 若存在环则返回 true（Kahn） */
export function specHasCycle(spec: OrchestrateDagSpec): boolean {
  const nodes = spec.nodes || [];
  const ids = new Set(nodes.map((n) => n.id));
  const indeg = new Map<string, number>();
  for (const n of nodes) {
    const deps = (n.dependsOn || []).filter((d) => ids.has(String(d).trim()));
    indeg.set(n.id, deps.length);
  }
  const children = new Map<string, string[]>();
  for (const n of nodes) {
    for (const d of n.dependsOn || []) {
      const ds = String(d).trim();
      if (!ids.has(ds)) continue;
      if (!children.has(ds)) children.set(ds, []);
      children.get(ds)!.push(n.id);
    }
  }
  const q = [...indeg.entries()].filter(([, v]) => v === 0).map(([k]) => k);
  let seen = 0;
  while (q.length) {
    const cur = q.shift()!;
    seen += 1;
    for (const ch of children.get(cur) || []) {
      const v = (indeg.get(ch) || 0) - 1;
      indeg.set(ch, v);
      if (v === 0) q.push(ch);
    }
  }
  return seen !== nodes.length;
}
