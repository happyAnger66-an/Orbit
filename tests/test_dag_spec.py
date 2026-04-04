"""Unit tests for DAG orchestration spec normalization."""

from __future__ import annotations

import pytest

from orbit.gateway.dag_spec import normalize_dag_dict, topological_order


def test_normalize_simple_chain() -> None:
    spec = normalize_dag_dict(
        {
            "nodes": [
                {"id": "a", "agentId": "main", "dependsOn": []},
                {"id": "b", "agentId": "main", "dependsOn": ["a"]},
            ],
            "parallelism": 2,
        }
    )
    assert spec["parallelism"] == 2
    assert len(spec["nodes"]) == 2
    order = spec["topologicalOrder"]
    assert order.index("a") < order.index("b")


def test_normalize_position_passthrough() -> None:
    spec = normalize_dag_dict(
        {
            "nodes": [
                {"id": "n1", "agentId": "main", "position": {"x": 10, "y": 20}},
            ]
        }
    )
    assert spec["nodes"][0].get("position") == {"x": 10.0, "y": 20.0}


def test_reject_cycle() -> None:
    with pytest.raises(ValueError, match="cycle"):
        normalize_dag_dict(
            {
                "nodes": [
                    {"id": "a", "agentId": "main", "dependsOn": ["b"]},
                    {"id": "b", "agentId": "main", "dependsOn": ["a"]},
                ]
            }
        )


def test_reject_unknown_dependency() -> None:
    with pytest.raises(ValueError, match="unknown"):
        normalize_dag_dict(
            {
                "nodes": [
                    {"id": "a", "agentId": "main", "dependsOn": ["missing"]},
                ]
            }
        )


def test_topological_order_returns_none_on_cycle() -> None:
    nodes = [
        {"id": "a", "agentId": "m", "dependsOn": ["b"]},
        {"id": "b", "agentId": "m", "dependsOn": ["a"]},
    ]
    assert topological_order(nodes) is None
