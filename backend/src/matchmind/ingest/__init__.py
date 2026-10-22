"""Event ingest adapter: external synthetic feeds and the live Event Hubs stream.

Every way a match gets in (a JSON-lines file in our schema, the generic CSV with a
mapping file, or the live stream) passes the same strict checks in `validate.py`
before the session plays it. docs/DATASET.md describes the formats.
"""

from .errors import IngestError
from .feed import Feed, load_feed
from .validate import DEFAULT_LIMITS, Limits, validate_events

__all__ = ["DEFAULT_LIMITS", "Feed", "IngestError", "Limits", "load_feed", "validate_events"]
