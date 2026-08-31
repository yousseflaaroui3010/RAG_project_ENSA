"""The server-rendered interface (CR-02).

ADR-02 as amended by CR-02: the screens are Jinja templates served off the
FastAPI host, with hand-written CSS and no JavaScript toolchain (ADR-10).
`designrag-main/` is a PICTURE of the intended screens, not code to port --
it is React, it is gitignored, and DECISIONS 2026-08-27 records why.

Three modules, split by what changes for what reason:

* `ports.py`   -- builds the real `AgentPorts` for the process (ADR-13:
                  the UI calls `agent.graph.ask` IN-PROCESS, so this is
                  composition, not an HTTP client).
* `runs.py`    -- one question in flight: the real stage the agent has
                  reached, cancellation, and what it read.
* `conversation.py` -- what the screen renders: messages, source cards,
                  and the passages behind them.
"""
