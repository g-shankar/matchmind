"""Fact-checker: every number on screen must come from the stats engine.

`check(text, facts, language)` passes only when
- every number in the text (integers, decimals, percentages, "3.1x", any
  script's digits, including Arabic-Indic and full-width) matches a numeric
  fact within printing tolerance,
- the text fits the length rules for its field, and
- no real club, player or competition name appears.

String facts (names, clocks such as "67:28") are removed from the text before
numbers are read, so the digits inside a clock never need their own fact.

This is the ONLY module allowed to contain real names: they are here so the
checker can block them. Everything else in the codebase stays synthetic.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Literal

from matchmind.crew.contracts import FactCheck, FactValue

Field = Literal["headline", "body", "why", "paragraph", "text"]

HEADLINE_MAX_WORDS = 8
HEADLINE_MAX_CHARS = 80
HEADLINE_MAX_CJK_UNITS = 22  # each CJK character or Latin word is one unit
BODY_MAX_CHARS = 400
BODY_MAX_SENTENCES = 2
WHY_MAX_CHARS = 320
PARAGRAPH_MAX_CHARS = 700
TEXT_MAX_CHARS = 1200

# Real top-flight English clubs, famous players and competition or broadcaster
# brands. Generated text must never contain them (case-insensitive, whole word).
BANNED_NAMES: tuple[str, ...] = (
    # clubs
    "Arsenal",
    "Aston Villa",
    "Bournemouth",
    "Brentford",
    "Brighton",
    "Burnley",
    "Chelsea",
    "Crystal Palace",
    "Everton",
    "Fulham",
    "Leeds United",
    "Liverpool",
    "Manchester City",
    "Manchester United",
    "Man City",
    "Man United",
    "Man Utd",
    "Newcastle",
    "Nottingham Forest",
    "Sunderland",
    "Tottenham",
    "West Ham",
    "Wolverhampton",
    "Leicester",
    "Southampton",
    "Ipswich",
    # players
    "Haaland",
    "Salah",
    "Saka",
    "Kane",
    "Rashford",
    "Fernandes",
    "De Bruyne",
    "Rooney",
    "Shearer",
    "Henry",
    "Gerrard",
    "Lampard",
    "Ronaldo",
    "Messi",
    "Odegaard",
    "Palmer",
    "Rice",
    "Son Heung-min",
    "Van Dijk",
    "Alisson",
    # competitions and broadcasters
    "Premier League",
    "Champions League",
    "Europa League",
    "FA Cup",
    "Sky Sports",
    "BBC",
    # common non-Latin spellings
    "أرسنال",
    "تشيلسي",
    "ليفربول",
    "مانشستر",
    "توتنهام",
    "هالاند",
    "アーセナル",
    "チェルシー",
    "リバプール",
    "マンチェスター",
    "トッテナム",
    "ハーランド",
    "プレミアリーグ",
)

_BANNED_RE = [
    (
        name,
        re.compile(rf"(?<!\w){re.escape(name)}(?!\w)" if name.isascii() else re.escape(name), re.IGNORECASE),
    )
    for name in BANNED_NAMES
]

_SENTENCE_END = re.compile(r"[。！？]+|[.!?؟]+(?=\s|$|[\"'”’)])")
_CJK = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]")


def normalise_digits(text: str) -> str:
    """Map every Unicode decimal digit (Arabic-Indic, full-width, ...) to 0-9
    and the Arabic decimal and thousands separators to ASCII."""
    out = []
    for ch in text:
        if unicodedata.category(ch) == "Nd":
            out.append(str(unicodedata.decimal(ch)))
        elif ch == "٫":  # Arabic decimal separator
            out.append(".")
        elif ch == "٬":  # Arabic thousands separator
            out.append(",")
        elif ch == "٪":  # Arabic percent sign
            out.append("%")
        else:
            out.append(ch)
    return "".join(out)


def extract_numbers(text: str, language: str = "en") -> list[str]:
    """Numbers as printed (strings, '.' as decimal point)."""
    t = normalise_digits(text)
    if language in ("es", "fr"):
        t = re.sub(r"(?<=\d),(?=\d)", ".", t)  # decimal comma
        t = re.sub(r"(?<=\d)[   ](?=\d{3}(?!\d))", "", t)  # 1 000
    else:
        t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)  # 1,000
    return re.findall(r"\d+(?:\.\d+)?", t)


def _numeric_facts(facts: Mapping[str, FactValue]) -> list[float]:
    return [abs(float(v)) for v in facts.values() if isinstance(v, int | float) and not isinstance(v, bool)]


def _string_facts(facts: Mapping[str, FactValue]) -> list[str]:
    return sorted({v for v in facts.values() if isinstance(v, str) and v}, key=len, reverse=True)


def _matches(token: str, values: list[float]) -> bool:
    n = float(token)
    decimals = len(token.split(".")[1]) if "." in token else 0
    tol = 0.5 * 10**-decimals + 1e-9
    return any(abs(n - v) <= tol for v in values)


def _word_count(text: str) -> int:
    return sum(1 for tok in text.split() if any(ch.isalnum() for ch in tok))


def sentence_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    ends = len(_SENTENCE_END.findall(stripped))
    last = stripped.rstrip("\"'”’)")[-1:]
    trailing = 0 if last and last in ".!?。！？؟" else 1
    return ends + trailing


def length_problems(text: str, field: Field) -> list[str]:
    reasons: list[str] = []
    if not text.strip():
        return ["empty text"]
    if field == "headline":
        if len(text) > HEADLINE_MAX_CHARS:
            reasons.append(f"headline longer than {HEADLINE_MAX_CHARS} characters")
        if _CJK.search(text):
            units = len(_CJK.findall(text)) + _word_count(_CJK.sub(" ", text))
            if units > HEADLINE_MAX_CJK_UNITS:
                reasons.append(f"headline longer than {HEADLINE_MAX_CJK_UNITS} characters")
        elif _word_count(text) > HEADLINE_MAX_WORDS:
            reasons.append(f"headline longer than {HEADLINE_MAX_WORDS} words")
    elif field == "body":
        if len(text) > BODY_MAX_CHARS:
            reasons.append(f"body longer than {BODY_MAX_CHARS} characters")
        if sentence_count(text) > BODY_MAX_SENTENCES:
            reasons.append(f"body longer than {BODY_MAX_SENTENCES} sentences")
    elif field == "why":
        if len(text) > WHY_MAX_CHARS:
            reasons.append(f"explanation longer than {WHY_MAX_CHARS} characters")
    elif field == "paragraph":
        if len(text) > PARAGRAPH_MAX_CHARS:
            reasons.append(f"paragraph longer than {PARAGRAPH_MAX_CHARS} characters")
    elif len(text) > TEXT_MAX_CHARS:
        reasons.append(f"text longer than {TEXT_MAX_CHARS} characters")
    return reasons


def banned_names_in(text: str) -> list[str]:
    return [name for name, rx in _BANNED_RE if rx.search(text)]


def check(
    text: str, facts: Mapping[str, FactValue], language: str = "en", field: Field = "text"
) -> FactCheck:
    reasons = length_problems(text, field)
    for name in banned_names_in(text):
        reasons.append(f"real name not allowed: {name}")

    scrubbed = text
    for s in _string_facts(facts):
        scrubbed = scrubbed.replace(s, " ")
    values = _numeric_facts(facts)
    for token in extract_numbers(scrubbed, language):
        if not _matches(token, values):
            reasons.append(f"number {token} is not in the facts")
    return FactCheck(ok=not reasons, reasons=reasons)


def check_all(
    parts: Mapping[Field, str | list[str]], facts: Mapping[str, FactValue], language: str
) -> FactCheck:
    """Check several fields at once; reasons are prefixed with the field."""
    reasons: list[str] = []
    for field, value in parts.items():
        for text in value if isinstance(value, list) else [value]:
            result = check(text, facts, language, field)
            reasons.extend(f"{field}: {r}" for r in result.reasons)
    return FactCheck(ok=not reasons, reasons=reasons)
