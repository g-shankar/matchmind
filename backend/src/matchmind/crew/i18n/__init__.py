"""Localised studio phrases and the small formatter that fills them.

Placeholders: `{key}` takes a value from the variables (a moment's facts plus
derived words); `{key|one|many}` prints the number then the right plural word.
Numbers print exactly as stored in the facts, with a decimal comma in es/fr.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from matchmind.crew.i18n import ar, en, es, fr, ja

PACKS: dict[str, dict[str, Any]] = {"en": en.PACK, "es": es.PACK, "fr": fr.PACK, "ar": ar.PACK, "ja": ja.PACK}

_PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)(?:\|([^|{}]*)\|([^{}]*))?\}")


# The curated football glossary every studio pack defines (`PACK["glossary"]`):
# term key -> (register, what it means). Templates print a term as `{g_<key>}`.
# The terms were written by the PitchPulse team; see docs/LANGUAGES.md.
GLOSSARY_TERMS: dict[str, tuple[str, str]] = {
    "box": ("neutral", "the penalty area, in everyday broadcast words"),
    "keeper": ("neutral", "the goalkeeper"),
    "back_line": ("neutral", "the defensive line"),
    "equaliser": ("neutral", "the goal that levels the match"),
    "comeback": ("emotive", "fighting back from behind"),
    "let_off": ("emotive", "a rival chance the fan's team survived"),
    "rocket": ("emotive", "a thunderous, very fast shot"),
}


def glossary_markdown() -> str:
    """The glossary table for docs/LANGUAGES.md (a test keeps them in step)."""
    langs = list(PACKS)
    lines = [
        "| Term | Register | Meaning | " + " | ".join(langs) + " |",
        "|---|---|---|" + "---|" * len(langs),
    ]
    for key, (register, meaning) in GLOSSARY_TERMS.items():
        terms = " | ".join(PACKS[lang]["glossary"][key] for lang in langs)
        lines.append(f"| `{key}` | {register} | {meaning} | {terms} |")
    return "\n".join(lines)


class MissingFact(KeyError):
    """A template needs a variable the moment does not have."""


def pack(language: str) -> dict[str, Any]:
    return PACKS.get(language, PACKS["en"])


def fmt_value(value: Any, language: str) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = str(int(value)) if value.is_integer() else repr(value)
        return text.replace(".", ",") if language in ("es", "fr") else text
    return str(value)


# Chance values in a replay ("worth 0.20 expected goals against 0.05 xG"): always two
# decimals, as the evidence shows them, so 0.2 never reads as a different figure from 0.24.
XG_DECIMALS_KEYS: frozenset[str] = frozenset({"shot_xg", "alt_xg", "alt_value", "projected_xg"})


def _fmt_key(key: str, value: Any, language: str) -> str:
    if key in XG_DECIMALS_KEYS and isinstance(value, float) and not isinstance(value, bool):
        text = f"{value:.2f}"
        return text.replace(".", ",") if language in ("es", "fr") else text
    return fmt_value(value, language)


def _plural_one(n: float, language: str) -> bool:
    return n < 2 if language == "fr" else n == 1


def fill(template: str, variables: Mapping[str, Any], language: str) -> str:
    def repl(m: re.Match[str]) -> str:
        key, one, many = m.group(1), m.group(2), m.group(3)
        if key not in variables or variables[key] is None or isinstance(variables[key], bool):
            raise MissingFact(key)
        value = variables[key]
        text = _fmt_key(key, value, language)
        if one is not None:
            word = one if isinstance(value, int | float) and _plural_one(value, language) else many
            return f"{text} {word}"
        return text

    return capitalise(_PLACEHOLDER.sub(repl, template))


def fill_first(options: Sequence[Any], variables: Mapping[str, Any], language: str) -> Any:
    """Fill the first option (a string or a tuple of strings) whose
    placeholders are all available. Raises MissingFact when none fits."""
    return fill_first_with_template(options, variables, language)[0]


def fill_first_with_template(
    options: Sequence[Any], variables: Mapping[str, Any], language: str
) -> tuple[Any, Any]:
    """`fill_first`, plus the option it used: the claims know exactly which
    placeholders (facts) each printed sentence came from."""
    last: MissingFact | None = None
    for option in options:
        try:
            if isinstance(option, tuple):
                return tuple(fill(part, variables, language) for part in option), option
            return fill(option, variables, language), option
        except MissingFact as exc:
            last = exc
    raise last or MissingFact("no template")


def placeholder_keys(template: str) -> list[str]:
    """The variable names a template prints, in order, once each."""
    return list(dict.fromkeys(m.group(1) for m in _PLACEHOLDER.finditer(template)))


def capitalise(text: str) -> str:
    """Upper-case the first letter of each sentence (Latin scripts only)."""

    def up(m: re.Match[str]) -> str:
        return m.group(1) + m.group(2).upper()

    text = re.sub(r"^([¡¿\"'“]*)([a-zà-ÿ])(?![A-Z])", up, text)
    return re.sub(r"([.!?]\s+[¡¿\"'“]*)([a-zà-ÿ])(?![A-Z])", up, text)


def ordinal_en(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
