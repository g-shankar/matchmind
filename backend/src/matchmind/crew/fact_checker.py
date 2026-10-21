"""Fact-checker: every number on screen must come from the stats engine.

`check(text, facts, language)` passes only when
- every number in the text (integers, decimals, percentages, "3.1x", any
  script's digits, including Arabic-Indic and full-width) matches a numeric
  fact within printing tolerance,
- the text fits the length rules for its field, and
- no real club, player, manager, stadium or competition name appears
  (accents are stripped first, so a name spelled with "Ø" is still caught), and
- for model text (`strict_words=True`), no spelled-out number or count word
  ("three", "tres", "trois", "ثلاث", "三本", "twice", "hat-trick", "2nd"...)
  unless it matches a numeric fact. Templates are exempt: they use articles
  such as "un"/"une" and words such as "premier" by design.

Machine-translated text (world languages, `translated=True`) gets the same
number and name checks with slightly roomier length rules; the translator's
own protection check makes sure every number and name came back unchanged.

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
# Machine-translated text (world languages) may run this much longer than English.
TRANSLATED_STRETCH = 1.3
TRANSLATED_HEADLINE_MAX_WORDS = 12
TRANSLATED_HEADLINE_MAX_CJK_UNITS = 26

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
    # managers
    "Guardiola",
    "Arteta",
    "Klopp",
    "Mourinho",
    "Ferguson",
    "Wenger",
    "Postecoglou",
    "Pochettino",
    "Ten Hag",
    "Amorim",
    "Maresca",
    "Unai Emery",
    "Eddie Howe",
    "Arne Slot",
    "Moyes",
    "Dyche",
    "Iraola",
    # stadiums
    "Anfield",
    "Old Trafford",
    "Etihad",
    "Emirates Stadium",
    "Stamford Bridge",
    "Villa Park",
    "St James' Park",
    "Goodison Park",
    "Craven Cottage",
    "Selhurst Park",
    "Molineux",
    "Elland Road",
    "Turf Moor",
    "Stadium of Light",
    "White Hart Lane",
    "Highbury",
    # club nicknames
    "Gunners",
    "Red Devils",
    "Spurs",
    "Toffees",
    "Magpies",
    "Cottagers",
    "Villans",
    "Seagulls",
    "Wolves",
    "Black Cats",
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

# Letters NFKD does not split into a base letter and an accent.
_FOLD = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "æ": "ae", "Æ": "AE"})


def fold(text: str) -> str:
    """Strip accents and compatibility forms so look-alike spellings match."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_FOLD))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


_BANNED_RE = [
    (
        name,
        re.compile(
            rf"(?<!\w){re.escape(fold(name))}(?!\w)" if name.isascii() else re.escape(fold(name)),
            re.IGNORECASE,
        ),
    )
    for name in BANNED_NAMES
]

_SENTENCE_END = re.compile(r"[。！？]+|[.!?؟।]+(?=\s|$|[\"'”’)])")
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
    trailing = 0 if last and last in ".!?。！？؟।" else 1
    return ends + trailing


def length_problems(text: str, field: Field, translated: bool = False) -> list[str]:
    """`translated=True` (machine-translated studio text) allows a little more
    room: translations run longer than the English they come from."""
    reasons: list[str] = []
    if not text.strip():
        return ["empty text"]
    stretch = TRANSLATED_STRETCH if translated else 1.0
    max_words = TRANSLATED_HEADLINE_MAX_WORDS if translated else HEADLINE_MAX_WORDS
    max_cjk = TRANSLATED_HEADLINE_MAX_CJK_UNITS if translated else HEADLINE_MAX_CJK_UNITS

    def limit(n: int) -> int:
        return int(n * stretch)

    if field == "headline":
        if len(text) > limit(HEADLINE_MAX_CHARS):
            reasons.append(f"headline longer than {limit(HEADLINE_MAX_CHARS)} characters")
        if _CJK.search(text):
            units = len(_CJK.findall(text)) + _word_count(_CJK.sub(" ", text))
            if units > max_cjk:
                reasons.append(f"headline longer than {max_cjk} characters")
        elif _word_count(text) > max_words:
            reasons.append(f"headline longer than {max_words} words")
    elif field == "body":
        if len(text) > limit(BODY_MAX_CHARS):
            reasons.append(f"body longer than {limit(BODY_MAX_CHARS)} characters")
        if sentence_count(text) > BODY_MAX_SENTENCES:
            reasons.append(f"body longer than {BODY_MAX_SENTENCES} sentences")
    elif field == "why":
        if len(text) > limit(WHY_MAX_CHARS):
            reasons.append(f"explanation longer than {limit(WHY_MAX_CHARS)} characters")
    elif field == "paragraph":
        if len(text) > limit(PARAGRAPH_MAX_CHARS):
            reasons.append(f"paragraph longer than {limit(PARAGRAPH_MAX_CHARS)} characters")
    elif len(text) > limit(TEXT_MAX_CHARS):
        reasons.append(f"text longer than {limit(TEXT_MAX_CHARS)} characters")
    return reasons


def banned_names_in(text: str) -> list[str]:
    folded = fold(text)
    return [name for name, rx in _BANNED_RE if rx.search(folded)]


# --- Number words (model text only) ---------------------------------------------------------
# Indefinite articles that double as "one" (fr un/une, es un/una) are left out on purpose.


def _seq(words: str, start: int, step: int = 1) -> dict[str, int]:
    return {w: start + step * i for i, w in enumerate(words.split())}


def _same(value: int, *words: str) -> dict[str, int]:
    return dict.fromkeys(words, value)


_EN_WORDS: dict[str, int] = {
    **_same(0, "zero", "nil"),
    **_seq("one two three four five six seven eight nine ten", 1),
    **_seq("eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty", 11),
    **_seq("thirty forty fifty sixty seventy eighty ninety hundred", 30, 10),
    **_seq("first second third fourth fifth sixth seventh eighth ninth tenth", 1),
    **_same(2, "twice", "brace"),
    **_same(3, "thrice", "hat-trick", "hattrick"),
}
_ES_WORDS: dict[str, int] = {
    **_same(0, "cero"),
    **_same(1, "uno", "primer", "primero", "primera"),
    **_seq("dos tres cuatro cinco seis siete ocho nueve diez", 2),
    **_seq("once doce trece catorce quince dieciséis diecisiete dieciocho diecinueve veinte", 11),
    **_seq("treinta cuarenta cincuenta sesenta setenta ochenta noventa cien", 30, 10),
    **_same(100, "ciento"),
    **_same(2, "segundo", "segunda", "doblete"),
    **_same(3, "tercer", "tercero", "tercera", "triplete", "hat-trick"),
    **_seq("cuarto quinto sexto séptimo octavo noveno décimo", 4),
    **_seq("cuarta quinta sexta séptima octava novena décima", 4),
}
_FR_WORDS: dict[str, int] = {
    **_same(0, "zéro"),
    **_same(1, "premier", "première"),
    **_seq("deux trois quatre cinq six sept huit neuf dix", 2),
    **_seq("onze douze treize quatorze quinze seize dix-sept dix-huit dix-neuf vingt", 11),
    **_seq("trente quarante cinquante soixante soixante-dix quatre-vingt quatre-vingt-dix cent", 30, 10),
    **_same(80, "quatre-vingts"),
    **_same(2, "deuxième", "second", "seconde", "doublé"),
    **_same(3, "triplé", "hat-trick"),
    **_seq("troisième quatrième cinquième sixième septième huitième neuvième dixième", 3),
}
_AR_WORDS: dict[str, int] = {
    **_same(0, "صفر"),
    **_same(1, "واحد", "واحدة", "أول", "الأول", "الأولى"),
    **_same(2, "اثنان", "اثنين", "اثنتان", "اثنتين", "ثاني", "الثاني", "الثانية", "مرتين", "مرتان", "ثنائية"),
    **_same(3, "ثلاث", "ثلاثة", "ثالث", "الثالث", "الثالثة", "ثلاثية", "هاتريك"),
    **_same(4, "أربع", "أربعة", "الرابع"),
    **_same(5, "خمس", "خمسة", "الخامس"),
    **_same(6, "ست", "ستة", "السادس"),
    **_same(7, "سبع", "سبعة", "السابع"),
    **_same(8, "ثمان", "ثماني", "ثمانية", "الثامن"),
    **_same(9, "تسع", "تسعة", "التاسع"),
    **_same(10, "عشر", "عشرة", "العاشر"),
    **_same(20, "عشرون", "عشرين"),
    **_same(30, "ثلاثون", "ثلاثين"),
    **_same(40, "أربعون", "أربعين"),
    **_same(50, "خمسون", "خمسين"),
    **_same(60, "ستون", "ستين"),
    **_same(70, "سبعون", "سبعين"),
    **_same(80, "ثمانون", "ثمانين"),
    **_same(90, "تسعون", "تسعين"),
    **_same(100, "مئة", "مائة"),
}
_JA_WORDS: dict[str, int] = {"ハットトリック": 3}
_NUMBER_WORDS: dict[str, dict[str, int]] = {
    "en": _EN_WORDS,
    "es": _ES_WORDS,
    "fr": _FR_WORDS,
    "ar": _AR_WORDS,
    "ja": _JA_WORDS,
}
# English count words a model may slip into any language.
_EN_COUNT_WORDS = {"twice", "brace", "thrice", "hat-trick", "hattrick"}


def _word_re(words: dict[str, int], arabic: bool) -> re.Pattern[str]:
    alts = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    if arabic:  # one-letter prefixes: and, so, with, for, like
        return re.compile(rf"(?<!\w)(?:و|ف|ب|ل|ك)?({alts})(?!\w)")
    return re.compile(rf"(?<![\w-])({alts})(?![\w-])", re.IGNORECASE)


_WORD_RE = {lang: _word_re(words, lang == "ar") for lang, words in _NUMBER_WORDS.items()}
_KANJI_DIGITS = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_RE = re.compile("[〇一二三四五六七八九十百]+")
# Stock phrases where a number word is not a count.
_PHRASES = {
    "en": re.compile(r"\b(?:first|second) half\b|\bone-on-one\b|\bone-two\b|\bno one\b", re.IGNORECASE),
    "es": re.compile(r"\b(?:primera|segunda) parte\b|\buno contra uno\b", re.IGNORECASE),
    "fr": re.compile(r"\b(?:première|seconde|deuxième) mi-temps\b", re.IGNORECASE),
}


def kanji_value(run: str) -> int:
    """Value of a run of kanji numerals: 三 = 3, 十二 = 12, 二十五 = 25, 百 = 100."""
    total, current = 0, 0
    for ch in run:
        if ch in _KANJI_DIGITS:
            current = current * 10 + _KANJI_DIGITS[ch]
        else:
            total += (current or 1) * (10 if ch == "十" else 100)
            current = 0
    return total + current


def number_words_in(text: str, language: str) -> list[tuple[str, int]]:
    """(word, value) for every spelled-out number or count word in the text.
    Digit forms such as "2nd" are already read by `extract_numbers`."""
    if language in _PHRASES:
        text = _PHRASES[language].sub(" ", text)
    words = _NUMBER_WORDS.get(language, _EN_WORDS)
    lower = {w.lower(): v for w, v in words.items()}
    out = [
        (m.group(1), lower[m.group(1).lower()]) for m in _WORD_RE.get(language, _WORD_RE["en"]).finditer(text)
    ]
    if language != "en":
        out += [
            (m.group(1), _EN_WORDS[m.group(1).lower()])
            for m in _WORD_RE["en"].finditer(text)
            if m.group(1).lower() in _EN_COUNT_WORDS
        ]
    out += [(run, kanji_value(run)) for run in _KANJI_RE.findall(text)]
    return out


def check(
    text: str,
    facts: Mapping[str, FactValue],
    language: str = "en",
    field: Field = "text",
    strict_words: bool = False,
    translated: bool = False,
) -> FactCheck:
    """`strict_words=True` (model text) also rejects number words not in the facts.
    `translated=True` (world languages) relaxes the length rules a little."""
    reasons = length_problems(text, field, translated)
    if banned_names_in(text):
        reasons.append("real name not allowed")

    scrubbed = text
    for s in _string_facts(facts):
        scrubbed = scrubbed.replace(s, " ")
    values = _numeric_facts(facts)
    for token in extract_numbers(scrubbed, language):
        if not _matches(token, values):
            reasons.append(f"number {token} is not in the facts")
    if strict_words:
        for word, value in number_words_in(scrubbed, language):
            if not _matches(str(value), values):
                reasons.append(f"number word {word} is not in the facts")
    return FactCheck(ok=not reasons, reasons=reasons)


def check_all(
    parts: Mapping[Field, str | list[str]],
    facts: Mapping[str, FactValue],
    language: str,
    strict_words: bool = False,
    translated: bool = False,
) -> FactCheck:
    """Check several fields at once; reasons are prefixed with the field."""
    reasons: list[str] = []
    for field, value in parts.items():
        for text in value if isinstance(value, list) else [value]:
            result = check(text, facts, language, field, strict_words, translated)
            reasons.extend(f"{field}: {r}" for r in result.reasons)
    return FactCheck(ok=not reasons, reasons=reasons)
