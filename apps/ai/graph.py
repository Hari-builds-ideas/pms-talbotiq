"""
A tiny deterministic node-sequence runner — the in-repo stand-in for a LangGraph
``StateGraph``. Each agent's "graph" is an ordered list of node callables over a
shared ``state`` dict; a node returns the (mutated) state and may set
``state["_halt"] = reason`` to short-circuit the remaining nodes (e.g. an
anonymity-breach gate). This keeps the agent NODE SEQUENCES explicit, ordered, and
fully testable with no external dependency.

PRODUCTION SWAP: when the ``langgraph`` package is added (see
NEEDS_HARI_llm_provider.md), each node function becomes a LangGraph node and this
runner is replaced by ``StateGraph(...).compile().invoke(state)`` — the node
functions (the real logic) are unchanged.
"""
from __future__ import annotations


def run_graph(nodes, state: dict) -> dict:
    """Run ``nodes`` in order over ``state``; stop early if a node sets
    ``state['_halt']``. Returns the final state."""
    for node in nodes:
        state = node(state) or state
        if state.get("_halt"):
            break
    return state
