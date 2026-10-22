"""The studio crew as Microsoft Agent Framework workflows.

Two workflows, with one typed executor per agent:

    process:  Spotter -> Analyst -> Fact-checker --(next moment)--> Analyst ...
    render:   Commentator -> Fact-checker -> Producer

Each executor calls the crew's own step for that agent (`Crew.spot_step`,
`Crew.analyst_step`, `Crew.fact_check_explanation`, ...), so the agents, the
model client (`crew/llm.py`: timeout, repair retry, circuit breaker, budget),
the fact-checker gate and the traces are exactly the ones the in-process
orchestrator uses. Only the chaining moves into Agent Framework, which routes
the typed messages between executors. The process workflow loops from the
Fact-checker back to the Analyst once per moment, so moments are explained
and checked one after another, in the same order as in process; a test checks
that both orchestrators produce identical bundles, cards and traces.

Workflows run on the caller's thread (the crew is called from worker
threads), each thread with its own workflow instances, because one instance
runs one request at a time.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from matchmind.crew.contracts import Explanation, MomentBundle, Narrative, OverlayCard, ViewerProfile
from matchmind.crew.crew import AnalystDraft, CommentatorDraft, Crew, Spotted
from matchmind.schema import Event
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

# ------------------------------------------------------------------ messages


@dataclass
class SpotRequest:
    """Process workflow input: one event and the stats engine's numbers."""

    event: Event
    metrics: EventMetrics
    snapshot: MatchStateSnapshot
    players: dict[str, PlayerStats]


@dataclass
class MomentQueue:
    """The Spotter's moments, worked through one at a time."""

    request: SpotRequest
    spotted: Spotted
    done: list[MomentBundle] = field(default_factory=list)

    @property
    def next_index(self) -> int:
        return len(self.done)


@dataclass
class AnalystDraftMessage:
    queue: MomentQueue
    draft: AnalystDraft


@dataclass
class ProcessResult:
    bundles: list[MomentBundle]


@dataclass
class VoiceRequest:
    """Render workflow input: one moment for one viewer profile."""

    bundle: MomentBundle
    profile: ViewerProfile
    key: tuple


@dataclass
class CommentatorDraftMessage:
    request: VoiceRequest
    draft: CommentatorDraft


@dataclass
class CheckedNarrative:
    request: VoiceRequest
    draft: CommentatorDraft
    narrative: Narrative


@dataclass
class VoiceResult:
    card: OverlayCard | None


# ----------------------------------------------------------------- executors


class SpotterExecutor(Executor):
    def __init__(self, crew: Crew) -> None:
        super().__init__(id="spotter")
        self.crew = crew

    @handler
    async def spot(self, request: SpotRequest, ctx: WorkflowContext[MomentQueue, ProcessResult]) -> None:
        spotted = self.crew.spot_step(request.event, request.metrics, request.snapshot, request.players)
        if spotted.repeat is not None:
            await ctx.yield_output(ProcessResult(spotted.repeat))
            return
        if not spotted.moments:
            await ctx.yield_output(ProcessResult([]))
            return
        await ctx.send_message(MomentQueue(request, spotted))


class AnalystExecutor(Executor):
    def __init__(self, crew: Crew) -> None:
        super().__init__(id="analyst")
        self.crew = crew

    @handler
    async def explain(self, queue: MomentQueue, ctx: WorkflowContext[AnalystDraftMessage]) -> None:
        moment = queue.spotted.moments[queue.next_index]
        self.crew.trace_spotted(moment, queue.spotted.ms)
        await ctx.send_message(AnalystDraftMessage(queue, self.crew.analyst_step(moment)))


class FactCheckerExecutor(Executor):
    """The gate on every model text: one handler per kind of draft."""

    def __init__(self, crew: Crew) -> None:
        super().__init__(id="fact_checker")
        self.crew = crew

    @handler
    async def check_explanation(
        self, message: AnalystDraftMessage, ctx: WorkflowContext[MomentQueue, ProcessResult]
    ) -> None:
        queue = message.queue
        moment = queue.spotted.moments[queue.next_index]
        explanation: Explanation = self.crew.fact_check_explanation(moment, message.draft)
        queue.done.append(self.crew.keep_bundle(moment, explanation, queue.request.metrics))
        if queue.next_index < len(queue.spotted.moments):
            await ctx.send_message(queue)  # back to the Analyst for the next moment
        else:
            await ctx.yield_output(ProcessResult(queue.done))

    @handler
    async def check_narrative(
        self, message: CommentatorDraftMessage, ctx: WorkflowContext[CheckedNarrative, VoiceResult]
    ) -> None:
        narrative = self.crew.fact_check_narrative(message.draft)
        if narrative is None:
            await ctx.yield_output(VoiceResult(None))  # not even the template passed
            return
        await ctx.send_message(CheckedNarrative(message.request, message.draft, narrative))


class CommentatorExecutor(Executor):
    def __init__(self, crew: Crew) -> None:
        super().__init__(id="commentator")
        self.crew = crew

    @handler
    async def voice(
        self, request: VoiceRequest, ctx: WorkflowContext[CommentatorDraftMessage, VoiceResult]
    ) -> None:
        draft = self.crew.commentator_step(request.bundle, request.profile)
        if draft is None:
            await ctx.yield_output(VoiceResult(None))  # no template fits this moment
            return
        await ctx.send_message(CommentatorDraftMessage(request, draft))


class ProducerExecutor(Executor):
    def __init__(self, crew: Crew) -> None:
        super().__init__(id="producer")
        self.crew = crew

    @handler
    async def produce(self, message: CheckedNarrative, ctx: WorkflowContext[Never, VoiceResult]) -> None:
        card = self.crew.producer_step(message.draft, message.narrative, message.request.key)
        await ctx.yield_output(VoiceResult(card))


# ------------------------------------------------------------------ workflows


def build_process_workflow(crew: Crew) -> Workflow:
    spotter, analyst, checker = SpotterExecutor(crew), AnalystExecutor(crew), FactCheckerExecutor(crew)
    return (
        WorkflowBuilder(
            name="pitchpulse-process",
            description="Spotter -> Analyst -> Fact-checker, once per moment in an event",
            start_executor=spotter,
        )
        .add_edge(spotter, analyst)
        .add_edge(analyst, checker)
        .add_edge(checker, analyst)
        .build()
    )


def build_render_workflow(crew: Crew) -> Workflow:
    commentator, checker = CommentatorExecutor(crew), FactCheckerExecutor(crew)
    producer = ProducerExecutor(crew)
    return (
        WorkflowBuilder(
            name="pitchpulse-render",
            description="Commentator -> Fact-checker -> Producer, for one moment and one viewer profile",
            start_executor=commentator,
        )
        .add_edge(commentator, checker)
        .add_edge(checker, producer)
        .build()
    )


class CrewWorkflows:
    """Runs a crew's process and render chains as Agent Framework workflows."""

    name = "agent_framework"

    def __init__(self, crew: Crew) -> None:
        self.crew = crew
        self._local = threading.local()

    def _workflow(self, kind: str) -> Workflow:
        workflow = getattr(self._local, kind, None)
        if workflow is None:
            build = build_process_workflow if kind == "process" else build_render_workflow
            workflow = build(self.crew)
            setattr(self._local, kind, workflow)
        return workflow

    def _run(self, kind: str, message: Any) -> Any:
        workflow = self._workflow(kind)
        try:
            result = _run_sync(workflow.run(message))
        except BaseException:
            setattr(self._local, kind, None)  # never reuse an instance a failure left behind
            raise
        outputs = result.get_outputs()
        if len(outputs) != 1:
            raise RuntimeError(f"the {kind} workflow gave {len(outputs)} outputs, expected 1")
        return outputs[0]

    def process(
        self,
        event: Event,
        metrics: EventMetrics,
        snapshot: MatchStateSnapshot,
        players: dict[str, PlayerStats],
    ) -> list[MomentBundle]:
        out: ProcessResult = self._run("process", SpotRequest(event, metrics, snapshot, players))
        return out.bundles

    def voice(self, bundle: MomentBundle, profile: ViewerProfile, key: tuple) -> OverlayCard | None:
        out: VoiceResult = self._run("render", VoiceRequest(bundle, profile, key))
        return out.card


_spare = ThreadPoolExecutor(max_workers=2, thread_name_prefix="crew-workflow")


def _run_sync(coro: Any) -> Any:
    """Run a workflow to the end from synchronous code. The crew is called from
    worker threads (no event loop), so this is normally `asyncio.run`; a caller
    already inside an event loop gets the run on a spare thread instead."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return _spare.submit(asyncio.run, coro).result()
