"""Event Hubs consumer: the API plays the live stream the simulator publishes.

Off by default. `MATCHMIND_SOURCE=eventhubs` switches it on; then the session
reads `EVENTHUB_FULLY_QUALIFIED_NAMESPACE` and `EVENTHUB_NAME` and signs in with
`DefaultAzureCredential` (managed identity in Azure, `az login` locally). There
is no connection-string path: the namespace has local (key) auth switched off,
and the app identity needs only the Azure Event Hubs Data Receiver role, which
the template grants only when this mode is switched on.

The simulator publishes with `partition_key=match_id`, so one match stays on one
partition and keeps its order there. The consumer reads every partition from
the latest position (`@latest`, or `MATCHMIND_EVENTHUBS_START=-1` for the
earliest retained event), follows one match (`MATCHMIND_EVENTHUBS_MATCH_ID`, or
the first match_start it sees) and hands each message to the shared LiveFeed,
which checks it with the same rules as a file and blocks the callback when the
session is behind (backpressure).
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any, Protocol

from .live import LiveFeed

logger = logging.getLogger("pitchpulse.ingest")

PUT_TIMEOUT_S = 30.0


class ConsumerLike(Protocol):
    def receive(self, on_event: Callable[..., None], **kwargs: Any) -> None: ...
    def close(self) -> None: ...


def default_consumer() -> ConsumerLike:  # pragma: no cover - needs Azure
    try:
        from azure.eventhub import EventHubConsumerClient
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise RuntimeError("Event Hubs mode needs the Azure extras: pip install '.[azure]'") from exc
    namespace = os.environ.get("EVENTHUB_FULLY_QUALIFIED_NAMESPACE", "").strip()
    hub = os.environ.get("EVENTHUB_NAME", "").strip()
    if not namespace or not hub:
        raise RuntimeError("Event Hubs mode needs EVENTHUB_FULLY_QUALIFIED_NAMESPACE and EVENTHUB_NAME")
    return EventHubConsumerClient(
        fully_qualified_namespace=namespace,
        eventhub_name=hub,
        consumer_group=os.environ.get("EVENTHUB_CONSUMER_GROUP", "$Default"),
        credential=DefaultAzureCredential(),
    )


def _body(event: Any) -> str | bytes | None:
    if event is None:
        return None
    reader = getattr(event, "body_as_str", None)
    if callable(reader):
        return reader(encoding="UTF-8")
    body = getattr(event, "body", None)
    return body if isinstance(body, str | bytes) else None


class EventHubsSource:
    """Runs the consumer on a daemon thread and feeds a LiveFeed."""

    def __init__(
        self,
        feed: LiveFeed,
        consumer_factory: Callable[[], ConsumerLike] = default_consumer,
        starting_position: str | None = None,
    ) -> None:
        self.feed = feed
        self._factory = consumer_factory
        self.starting_position = starting_position or os.environ.get("MATCHMIND_EVENTHUBS_START", "@latest")
        self._client: ConsumerLike | None = None
        self._thread: threading.Thread | None = None
        self._stopping = False

    def start(self) -> None:
        self._client = self._factory()
        self._thread = threading.Thread(target=self._run, name="eventhubs-consumer", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._client is not None
        error = None
        try:
            self._client.receive(
                on_event=self._on_event,
                starting_position=self.starting_position,
                max_wait_time=5,
            )
        except Exception:  # noqa: BLE001 - surfaced through the feed status
            if not self._stopping:
                logger.exception("Event Hubs consumer stopped")
                error = "The live stream stopped; the match ends at the last event received."
        self.feed.close(error)

    def _on_event(self, partition_context: Any, event: Any) -> None:
        body = _body(event)
        if body is None:
            return  # max_wait_time tick with no message
        # Blocks while the session is behind (backpressure); gives up only when closing.
        while not self.feed.put(body, timeout=PUT_TIMEOUT_S):
            if self._stopping or self.feed.closed:
                return

    def close(self) -> None:
        self._stopping = True
        self.feed.close()
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                logger.warning("Event Hubs consumer did not close cleanly")
