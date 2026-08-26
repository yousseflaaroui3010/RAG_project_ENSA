"""The Sanad agent (architecture section 4: the `agent` module).

Six files, and the split is by who owns what next:

| File        | What it holds                                             |
|-------------|-----------------------------------------------------------|
| `graph.py`  | section 5.2 wired up, and `ask`, the one entry point      |
| `nodes.py`  | one function per box in section 5.2, plus the two routers |
| `ports.py`  | the eight seams ST-22 to ST-25 fill in                    |
| `state.py`  | the `Answer` contract (openapi) and the graph's scratchpad|
| `stores.py` | the one port that is NOT deferred: reading parent sections|
| `trace.py`  | the per-answer trace collector (ADR-09, F-10)             |

Deliberately empty of re-exports: `from agent.graph import ask` says
where the thing lives, and a package that re-exports everything pulls
LangGraph in for a caller who only wanted a trace object.
"""
