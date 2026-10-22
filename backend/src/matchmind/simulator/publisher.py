"""Where simulated events go: JSONL files, stdout, or Azure Event Hubs."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from matchmind.schema import Event

Sink = Callable[[Event], None]


def write_jsonl(events: Iterable[Event], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(event.to_json() + "\n")
    return path


def read_jsonl(path: str | Path) -> list[Event]:
    with Path(path).open(encoding="utf-8") as fh:
        return [Event.model_validate_json(line) for line in fh if line.strip()]


def replay(
    events: Iterable[Event],
    sink: Sink,
    speed: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Send events to a sink at match pace. speed=60 plays 90 minutes in 1.5."""
    if speed <= 0:
        raise ValueError("speed must be positive")
    count, last = 0, None
    for event in events:
        if last is not None and event.period == last.period:
            gap = (event.clock_s - last.clock_s) / speed
            if gap > 0:
                sleep(gap)
        sink(event)
        last = event
        count += 1
    return count


def stdout_sink(event: Event) -> None:
    sys.stdout.write(event.to_json() + "\n")
    sys.stdout.flush()


class EventHubSink:
    """Publishes each event to Azure Event Hubs, partitioned by match.

    Keyless only, here and in the deployed simulator job: Microsoft Entra ID via
    `DefaultAzureCredential` (`az login` locally, the job's managed identity in Azure).
    Set EVENTHUB_FULLY_QUALIFIED_NAMESPACE and EVENTHUB_NAME. There is no
    connection-string path: the namespace has local (key) auth switched off.
    """

    def __init__(self) -> None:
        try:
            from azure.eventhub import EventData, EventHubProducerClient
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SystemExit("Install the Azure extras: pip install -e '.[azure]'") from exc
        self._event_data = EventData
        hub = os.environ.get("EVENTHUB_NAME")
        namespace = os.environ.get("EVENTHUB_FULLY_QUALIFIED_NAMESPACE")
        if not hub:
            raise SystemExit("Set EVENTHUB_NAME")
        if not namespace:
            raise SystemExit("Set EVENTHUB_FULLY_QUALIFIED_NAMESPACE and sign in with az login")
        from azure.identity import DefaultAzureCredential

        self._client = EventHubProducerClient(
            fully_qualified_namespace=namespace,
            eventhub_name=hub,
            credential=DefaultAzureCredential(),
        )

    def __call__(self, event: Event) -> None:
        batch = self._client.create_batch(partition_key=event.match_id)
        data = self._event_data(event.to_json())
        data.content_type = "application/json"
        data.properties = {"type": event.type.value, "schema_version": event.schema_version}
        batch.add(data)
        self._client.send_batch(batch)

    def close(self) -> None:
        self._client.close()
