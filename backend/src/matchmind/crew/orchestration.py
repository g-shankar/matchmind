"""Which orchestrator chains the crew's agents.

- `in_process` (default): `Crew.process` and `Crew.render` call the agent steps
  one after another.
- `agent_framework`: the same steps run as typed executors in Microsoft Agent
  Framework workflows (`crew.workflow`). Free and local: no Azure service is
  involved, so it is not behind the paid-AI switch.

`MATCHMIND_ORCHESTRATOR` picks one. If Agent Framework is asked for in the
environment but its package (`agent-framework-core`, the `agent-framework`
extra) is missing, the crew logs it and stays in process rather than stopping
the match. Asking for it in code with the package missing raises.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from matchmind.crew.crew import Crew

ORCHESTRATORS = ("in_process", "agent_framework")

logger = logging.getLogger(__name__)


def orchestrator_setting() -> str:
    """MATCHMIND_ORCHESTRATOR: in_process (default) or agent_framework."""
    value = os.environ.get("MATCHMIND_ORCHESTRATOR", "").strip().lower() or "in_process"
    if value not in ORCHESTRATORS:
        logger.warning("MATCHMIND_ORCHESTRATOR=%r is not one of %s; using in_process", value, ORCHESTRATORS)
        return "in_process"
    return value


def make_workflows(crew: Crew, orchestrator: str | None) -> Any | None:
    """Agent Framework workflows for this crew, or None for the in-process chain."""
    explicit = orchestrator is not None
    name = orchestrator if explicit else orchestrator_setting()
    if name not in ORCHESTRATORS:
        raise ValueError(f"orchestrator must be one of {ORCHESTRATORS}")
    if name == "in_process":
        return None
    try:
        from matchmind.crew.workflow import CrewWorkflows
    except ImportError:
        if explicit:
            raise
        logger.warning(
            "MATCHMIND_ORCHESTRATOR=agent_framework but agent-framework-core is not installed; "
            "the crew runs in process"
        )
        return None
    return CrewWorkflows(crew)
