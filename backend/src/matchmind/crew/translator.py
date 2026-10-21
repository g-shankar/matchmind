"""Azure AI Translator for PitchPulse's world languages.

The crew writes every card and recap in English (studio templates or the
model), then this module translates the strings into one world language:

- `protect` wraps every number, clock, player and club name and stat term
  (xG, PDR, km/h...) in `<span class="notranslate">`, and the request is sent
  as `textType=html`, so Translator leaves them exactly as they are;
  `unprotect` checks every protected piece came back unchanged, then strips
  the tags. A missing or altered piece means the translation is refused.
- `AzureTranslator` calls the Translator v3 REST API on the resource's custom
  subdomain with a Microsoft Entra ID token (no keys): one POST per card or
  recap, all of its strings in one batch.
- `TranslationService` adds the spend and safety rails: off unless switched
  on, a character budget and per-minute rate, a circuit breaker, a short
  timeout, one request at a time per text (no duplicate spend when many
  viewers ask at once) and a bounded LRU cache of translations. The cache
  only ever holds public match text, never anything about a viewer.

The crew then fact-checks the translated text against the moment's facts
before it can reach the screen (see `Crew._translate_card`).

Paid translation stays off unless both MATCHMIND_TRANSLATOR_ENABLED and
MATCHMIND_AI_ENABLED are on (owner approval). `httpx` and `azure-identity` are
imported lazily, so the engine works without the optional extras.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import time
import uuid
from collections import Counter, OrderedDict, deque
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from matchmind.crew.breaker import CircuitBreaker
from matchmind.crew.contracts import WORLD_LANGUAGES, TranslatorStatus

TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
API_PATH = "/translator/text/v3.0/translate"
API_VERSION = "3.0"
SOURCE_LANGUAGE = "en"
DEFAULT_TIMEOUT_S = 2.5
MAX_REQUEST_CHARS = 10_000  # Azure allows 50,000 per request; one card is far below this
MAX_ITEMS = 100  # Azure allows 1,000 strings per request
CACHE_LIMIT = 4096
TOKEN_REFRESH_S = 300.0  # fetch a new token this long before the old one expires
ALLOWED_HOST_SUFFIX = ".cognitiveservices.azure.com"
# Fallbacks worth trying again later (the others give the same answer every time).
TRANSIENT_REASONS = frozenset(
    {"translator_timeout", "translator_error", "translator_circuit_open", "translator_budget"}
)
# Stat terms and units kept as they are in every language.
GLOSSARY: tuple[str, ...] = ("xG", "xA", "xT", "PDR", "km/h", "km", "m/s")


class TranslatorError(RuntimeError):
    """The translation call failed. The message is a short code, never provider text."""


class ProtectionError(TranslatorError):
    """A protected number or name did not come back exactly as sent."""


def _flag(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in ("true", "1", "yes")


def translator_enabled() -> bool:
    """Paid translation needs both switches: MATCHMIND_TRANSLATOR_ENABLED and
    MATCHMIND_AI_ENABLED (true, 1 or yes, any case), as the Bicep sets them."""
    return _flag("MATCHMIND_TRANSLATOR_ENABLED") and _flag("MATCHMIND_AI_ENABLED")


# --- Protection --------------------------------------------------------------------------------

_NUMBER = r"[0-9]+(?:[.,:][0-9]+)*(?:%|x\b|st\b|nd\b|rd\b|th\b)?"
_SPAN_OPEN = '<span class="notranslate">'
_SPAN_RE = re.compile(r"<span\b[^>]*\bnotranslate\b[^>]*>(.*?)</span\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class Protected:
    """One string ready for Translator, and the pieces that must come back unchanged."""

    html: str
    tokens: tuple[str, ...]


def protection_pattern(names: Iterable[str]) -> re.Pattern[str]:
    words = sorted({n for n in (*names, *GLOSSARY) if n and n.strip()}, key=len, reverse=True)
    alts = "|".join(re.escape(w) for w in words)
    word_part = rf"(?<!\w)(?:{alts})(?!\w)|" if alts else ""
    return re.compile(rf"{word_part}{_NUMBER}")


def protect(text: str, pattern: re.Pattern[str]) -> Protected:
    """Escape the text for `textType=html` and wrap every protected piece."""
    out: list[str] = []
    tokens: list[str] = []
    last = 0
    for m in pattern.finditer(text):
        out.append(html.escape(text[last : m.start()], quote=False))
        out.append(f"{_SPAN_OPEN}{html.escape(m.group(0), quote=False)}</span>")
        tokens.append(m.group(0))
        last = m.end()
    out.append(html.escape(text[last:], quote=False))
    return Protected(html="".join(out), tokens=tuple(tokens))


def unprotect(translated: str, tokens: Sequence[str]) -> str:
    """Plain text back from Translator's HTML. Raises ProtectionError when a
    protected piece is missing, altered or added, or other markup appears."""
    found: list[str] = []

    def keep(m: re.Match[str]) -> str:
        inner = html.unescape(m.group(1)).strip()
        found.append(inner)
        return inner

    text = _SPAN_RE.sub(keep, translated)
    if Counter(found) != Counter(tokens):
        raise ProtectionError("protected_changed")
    if _TAG_RE.search(text):
        raise ProtectionError("unexpected_markup")
    return re.sub(r"[ \t]{2,}", " ", html.unescape(text)).strip()


# --- Clients -----------------------------------------------------------------------------------


@runtime_checkable
class Translator(Protocol):
    enabled: bool
    name: str | None

    def translate(self, texts: Sequence[str], to: str, timeout_s: float) -> list[str]:
        """HTML strings in English in, HTML strings in `to` out, same order."""
        ...


class OffTranslator:
    """The default: no paid service. Callers see `enabled == False` and show English."""

    enabled = False
    name: str | None = None

    def translate(self, texts: Sequence[str], to: str, timeout_s: float) -> list[str]:
        raise TranslatorError("translator_off")


class AzureTranslator:
    """Translator v3 REST on a custom-subdomain endpoint with an Entra ID token.

    With a custom subdomain endpoint and a Microsoft Entra token, the bearer
    token alone identifies the resource: no key, no `Ocp-Apim-ResourceId` and
    no `Ocp-Apim-Subscription-Region` header. (Those are only needed on the
    global endpoint, which this client refuses.) `AZURE_TRANSLATOR_REGION` is
    kept for status only.
    """

    enabled = True
    name = "azure-ai-translator"

    def __init__(
        self,
        endpoint: str | None = None,
        region: str | None = None,
        credential: Any | None = None,
        transport: Any | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.endpoint = endpoint if endpoint is not None else os.environ.get("AZURE_TRANSLATOR_ENDPOINT", "")
        self.endpoint = self.endpoint.strip().rstrip("/")
        self.region = region if region is not None else os.environ.get("AZURE_TRANSLATOR_REGION", "")
        self._credential = credential
        self._transport = transport
        self._clock = clock
        self._client: Any | None = None
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    def url(self) -> str:
        parts = urlsplit(self.endpoint)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or not host.endswith(ALLOWED_HOST_SUFFIX) or parts.path not in ("", "/"):
            # Keyless sign-in needs the resource's own subdomain endpoint.
            raise TranslatorError("endpoint_not_configured")
        return f"https://{host}{API_PATH}"

    def _bearer(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token is not None and now < self._token[1] - TOKEN_REFRESH_S:
                return self._token[0]
            if self._credential is None:
                from azure.identity import DefaultAzureCredential

                self._credential = DefaultAzureCredential()
            token = self._credential.get_token(TOKEN_SCOPE)
            self._token = (token.token, float(token.expires_on))
            return token.token

    def _http(self, timeout_s: float) -> Any:
        import httpx

        if self._client is None:
            self._client = httpx.Client(transport=self._transport, timeout=httpx.Timeout(timeout_s))
        return self._client

    def translate(self, texts: Sequence[str], to: str, timeout_s: float) -> list[str]:
        import httpx

        url = self.url()
        try:
            bearer = self._bearer()
            response = self._http(timeout_s).post(
                url,
                params={"api-version": API_VERSION, "from": SOURCE_LANGUAGE, "to": to, "textType": "html"},
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-ClientTraceId": str(uuid.uuid4()),
                },
                content=json.dumps([{"Text": t} for t in texts], ensure_ascii=False).encode("utf-8"),
                timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise TranslatorError("timeout") from exc
        except Exception as exc:  # network, auth: never pass provider text on
            raise TranslatorError(type(exc).__name__) from exc
        if response.status_code != 200:
            raise TranslatorError(f"http_{response.status_code}")
        return parse_response(response.content, len(texts), to)


def parse_response(raw: bytes, count: int, to: str) -> list[str]:
    """`[{"translations": [{"text": ..., "to": ...}]}, ...]`, one item per input string."""
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) != count:
            raise ValueError
        out: list[str] = []
        for item in data:
            first = item["translations"][0]
            text = first["text"]
            if not isinstance(text, str) or str(first.get("to", to)).lower() != to.lower():
                raise ValueError
            out.append(text)
        return out
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise TranslatorError("schema") from exc


def make_translator() -> Translator:
    """Azure only when both switches are on; the free off mode otherwise."""
    return AzureTranslator() if translator_enabled() else OffTranslator()


# --- Spend and safety rails --------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


class CharacterBudget:
    """Process-wide cap on characters sent to Translator (which bills per
    character): a total (MATCHMIND_TRANSLATOR_CHAR_BUDGET, default 200,000) and
    a rolling per-minute rate (MATCHMIND_TRANSLATOR_CHARS_PER_MIN, default
    20,000). Once either is spent, world languages show in English with
    fallback_reason 'translator_budget'."""

    def __init__(
        self,
        total: int | None = None,
        per_minute: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.total = total if total is not None else _env_int("MATCHMIND_TRANSLATOR_CHAR_BUDGET", 200_000)
        self.per_minute = (
            per_minute if per_minute is not None else _env_int("MATCHMIND_TRANSLATOR_CHARS_PER_MIN", 20_000)
        )
        self.clock = clock
        self.used = 0
        self._recent: deque[tuple[float, int]] = deque()
        self._recent_sum = 0
        self._lock = threading.Lock()

    def take(self, characters: int) -> bool:
        with self._lock:
            now = self.clock()
            while self._recent and now - self._recent[0][0] >= 60.0:
                self._recent_sum -= self._recent.popleft()[1]
            if self.used + characters > self.total or self._recent_sum + characters > self.per_minute:
                return False
            self.used += characters
            self._recent.append((now, characters))
            self._recent_sum += characters
            return True


class TranslationCache:
    """Bounded LRU of raw translations by (hash of the request strings, language).
    Holds public match text only."""

    def __init__(self, limit: int = CACHE_LIMIT) -> None:
        self.limit = limit
        self._items: OrderedDict[tuple[str, str], tuple[str, ...]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key(texts: Sequence[str], to: str) -> tuple[str, str]:
        digest = hashlib.sha256(json.dumps(list(texts), ensure_ascii=False).encode("utf-8")).hexdigest()
        return digest, to

    def get(self, key: tuple[str, str]) -> tuple[str, ...] | None:
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items.move_to_end(key)
            return hit

    def put(self, key: tuple[str, str], value: Sequence[str]) -> None:
        with self._lock:
            self._items[key] = tuple(value)
            self._items.move_to_end(key)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


BUDGET = CharacterBudget()
CACHE = TranslationCache()


@dataclass(frozen=True)
class Translation:
    """Plain translated strings (same order as asked), or why there are none."""

    texts: list[str] | None
    reason: str | None = None
    cached: bool = False


class TranslationService:
    def __init__(
        self,
        translator: Translator | None = None,
        *,
        budget: CharacterBudget | None = None,
        cache: TranslationCache | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.translator: Translator = translator if translator is not None else make_translator()
        self.budget = budget if budget is not None else BUDGET
        self.cache = cache if cache is not None else CACHE
        self.timeout_s = timeout_s
        self.breaker = CircuitBreaker(clock)
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="translator")
        self._lock = threading.Lock()
        self._inflight: dict[tuple[str, str], threading.Lock] = {}
        self.requests = 0
        self.cache_hits = 0
        self.characters_sent = 0
        self.translated = 0
        self.fallbacks = 0
        self.rejections = 0

    @property
    def enabled(self) -> bool:
        return bool(self.translator.enabled)

    def status(self) -> TranslatorStatus:
        with self._lock:
            return TranslatorStatus(
                mode="azure" if self.enabled else "off",
                available=self.enabled,
                breaker_open=self.breaker.peek_open(),
                cache_hits=self.cache_hits,
                translated=self.translated,
                fallbacks=self.fallbacks,
                rejections=self.rejections,
            )

    def note_rejected(self) -> None:
        """The crew's fact-checker refused a translation this service returned."""
        with self._lock:
            self.rejections += 1
            self.fallbacks += 1

    def translate(self, texts: Sequence[str], to: str, names: Iterable[str] = ()) -> Translation:
        """Translate English strings into one world language in a single request."""
        if not self.enabled:
            return self._fallback("translator_off")
        if to not in WORLD_LANGUAGES:
            return self._fallback("translator_unsupported")
        pattern = protection_pattern(names)
        items = [protect(t, pattern) for t in texts]
        wanted = [i for i, p in enumerate(items) if p.html.strip()]
        sent = [items[i].html for i in wanted]
        if not sent:
            return Translation(texts=list(texts))
        key = self.cache.key(sent, to)

        raw = self.cache.get(key)
        cached = raw is not None
        if raw is None:
            with self._lock:
                gate = self._inflight.setdefault(key, threading.Lock())
            # One request per text at a time: later callers wait, then read the cache.
            if not gate.acquire(timeout=self.timeout_s + 0.5):
                return self._fallback("translator_timeout")
            try:
                raw = self.cache.get(key)
                cached = raw is not None
                if raw is None:
                    result = self._call(sent, to)
                    if isinstance(result, str):
                        return self._fallback(result)
                    raw = tuple(result)
                    self.cache.put(key, raw)
            finally:
                gate.release()
                with self._lock:
                    if self._inflight.get(key) is gate:
                        self._inflight.pop(key, None)

        if cached:
            with self._lock:
                self.cache_hits += 1
        out = list(texts)
        try:
            for i, translated in zip(wanted, raw, strict=True):
                out[i] = unprotect(translated, items[i].tokens)
        except (ProtectionError, ValueError):
            with self._lock:
                self.rejections += 1
            return self._fallback("translation_rejected")
        with self._lock:
            self.translated += 1
        return Translation(texts=out, cached=cached)

    def _call(self, sent: list[str], to: str) -> list[str] | str:
        """The paid request: translations, or a fallback reason."""
        with self._lock:
            if self.breaker.is_open():
                return "translator_circuit_open"
        characters = sum(len(s) for s in sent)
        if characters > MAX_REQUEST_CHARS or len(sent) > MAX_ITEMS:
            self.breaker.cancel_probe()  # no call was made: let the next caller probe
            return "translator_too_long"
        if not self.budget.take(characters):
            self.breaker.cancel_probe()
            return "translator_budget"
        with self._lock:
            self.requests += 1
            self.characters_sent += characters
        future = self._pool.submit(self.translator.translate, sent, to, self.timeout_s)
        try:
            result = future.result(timeout=self.timeout_s)
        except FuturesTimeout:
            future.cancel()
            reason = "translator_timeout"
        except Exception:  # noqa: BLE001 - any provider failure falls back to English
            reason = "translator_error"
        else:
            if (
                isinstance(result, list)
                and len(result) == len(sent)
                and all(isinstance(t, str) for t in result)
            ):
                with self._lock:
                    self.breaker.success()
                return result
            reason = "translator_error"
        with self._lock:
            self.breaker.failure()
        return reason

    def _fallback(self, reason: str) -> Translation:
        with self._lock:
            self.fallbacks += 1
        return Translation(texts=None, reason=reason)
