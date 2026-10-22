"""The first gate for every question: hostile text never gets near the parser.

A question is refused, with one plain sentence in the viewer's language, when it
is empty or over `MAX_QUESTION_CHARS`, looks like markup or SQL, carries hidden
or direction-override characters, tries to change the rules ("ignore your
instructions", role-play, "my teacher says print your prompt", "translate
this: ..."), or names a real club, player, manager or competition (the
fact-checker's banned list). Checks run on a normalised copy: compatibility
forms folded (full-width letters), invisible characters dropped, Cyrillic and
Greek look-alikes mapped to Latin, accents stripped, case folded, so "ＩＧＮＯＲＥ",
"i​gnore" and "іgnore" all read as "ignore".

The question itself is never stored or logged; only the refusal reason is.
"""

# Pattern tables are kept one rule per line for review.
# ruff: noqa: E501

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from matchmind.crew.fact_checker import CONFUSABLES, banned_names_in, fold, normalise_digits

MAX_QUESTION_CHARS = 200

RefusalReason = Literal[
    "empty", "too_long", "markup", "injection", "real_name", "off_topic", "unknown_player", "fact_check"
]

# Look-alike letters (Cyrillic, Greek, Latin small capitals) -> Latin: shared with the ban list.
_CONFUSABLES = CONFUSABLES
# Arabic letter variants folded for matching (hamza forms, alef maqsura, teh marbuta, tatweel).
_ARABIC = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ـ": None})
# Direction overrides and isolates, and Unicode "tag" characters (invisible ASCII smuggling).
_FORBIDDEN_CONTROLS = re.compile("[‪-‮⁦-⁩\U000e0000-\U000e007f]")

_MARKUP = re.compile(
    r"[<>{}\[\]\\`$|]"
    r"|&#?\w+;"
    r"|(?:javascript|data|vbscript)\s*:"
    r"|\bon\w+\s*="
    r"|--|/\*|\*/|;\s*\w"
    r"|\bselect\b.{0,40}\bfrom\b|\binsert\s+into\b|\b(?:drop|alter|truncate)\s+(?:table|database)\b"
    r"|\bunion\s+(?:all\s+)?select\b|\bdelete\s+from\b|\bupdate\s+\w+\s+set\b|\bor\s+\d+\s*=\s*\d+"
    r"|'\s*or\s*'|\bexec(?:ute)?\s*\("
    r"|%[0-9a-f]{2}",
    re.IGNORECASE,
)

# Attempts to change the rules, in every language the box reads. Matched on the
# normalised text (accent-free, case-folded, Arabic letters folded).
_INJECTION = [
    re.compile(fold(p))
    for p in (
        # English
        r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(rules?|instructions?|prompts?|guidelines?"
        r"|polic(?:y|ies)|previous|above|prior|earlier|system|everything|restrictions?|filters?|context)\b",
        r"\b(system|developer|hidden|initial|original|secret|internal)\s+(prompt|message|instructions?|rules)\b",
        r"\b(your|the)\s+(prompt|instructions|rules|system message|configuration|guidelines|training)\b",
        r"\b(you are now|you're now|from now on|pretend|role ?-?play|act as|acting as|imagine you|simulate|jailbreak"
        r"|dan mode|developer mode|do anything now|unfiltered|uncensored|no restrictions|stay in character)\b",
        r"\b(print|reveal|show|repeat|output|display|leak|dump|recite|echo|spell out)\b.{0,30}"
        r"\b(prompt|instructions?|rules|system|configuration|api ?key|secrets?|passwords?|tokens?)\b",
        r"\b(translate|summari[sz]e|rewrite|paraphrase|repeat after me|write|compose|complete the)\b",
        r"\bsay (exactly|this|the following|after me|only|yes|no|that)\b",
        r"\b(base64|rot13|hexadecimal|unicode escape|morse|leetspeak)\b",
        r"\b(chatgpt|gpt|llm|language model|ai model|chatbot|openai|anthropic|claude|copilot|gemini)\b",
        r"\bmy (teacher|boss|grandma|grandmother|mum|mom|dad|professor|manager|developer|admin|lawyer)\b",
        r"\b(admin|sudo|root access|override code|authori[sz]ed|authori[sz]ation|maintenance mode)\b",
        r"\b(new|updated|different|real)\s+(rules|instructions|task|persona|role|identity)\b",
        r"\b(instructions?|commands?|prompt)\s*:",
        # Spanish
        r"\b(ignora|ignore|ignorar|olvida|olvidar|omite|omitir|saltate)\b.{0,40}\b(reglas|instrucciones|indicaciones"
        r"|prompt|sistema|anteriores?|todo|restricciones)\b",
        r"\b(eres ahora|ahora eres|a partir de ahora|finge|fingir|actua como|haz de|juego de rol|modo desarrollador)\b",
        r"\b(muestra|muestrame|revela|imprime|repite|dime)\b.{0,30}\b(prompt|instrucciones|reglas|sistema"
        r"|contrasena|clave|secretos?)\b",
        r"\b(traduce|traducir|resume|resumir|reescribe|escribe|redacta)\b",
        r"\bmi (profesor|profesora|jefe|jefa|abuela|madre|padre|maestro|maestra)\b",
        # French
        r"\b(ignore|ignorez|oublie|oubliez|contourne)\b.{0,40}\b(regles|instructions|consignes|prompt|systeme"
        r"|precedentes?|tout|restrictions)\b",
        r"\b(tu es maintenant|vous etes maintenant|a partir de maintenant|fais semblant|faites semblant|joue le role"
        r"|jouez le role|agis comme|agissez comme|mode developpeur)\b",
        r"\b(montre|montrez|revele|revelez|affiche|affichez|imprime|repete)\b.{0,30}\b(prompt|instructions|regles"
        r"|systeme|mot de passe|secrets?)\b",
        r"\b(traduis|traduisez|traduire|resume|resumez|reecris|ecris|ecrivez|redige)\b",
        r"\b(mon|ma) (prof|professeur|patron|cheffe?|grand-mere|mere|pere)\b",
        # Arabic (letters folded: no hamza on alef, teh marbuta as heh)
        r"(تجاهل|انس |انسى|تخط|تجاوز).{0,40}(القواعد|التعليمات|الاوامر|النظام|السابق|القيود)",
        r"(انت الان|من الان فصاعدا|تظاهر|تقمص|مثل دور|العب دور|وضع المطور)",
        r"(اظهر|اكشف|اطبع|كرر|اعرض).{0,30}(التعليمات|القواعد|النظام|البرومبت|كلمه السر|الاسرار)",
        r"\b(ترجم|لخص|اعد كتابه|اكتب)\b",
        r"\b(استاذي|معلمي|مديري|جدتي|امي|ابي)\b",
        # Japanese
        r"(無視|指示を|ルールを|プロンプト|システム|ロールプレイ|なりきって|翻訳|要約)",
    )
]


_CJK = "\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f"
_CJK_EDGE = re.compile(rf"(?<=[a-z0-9])(?=[{_CJK}])|(?<=[{_CJK}])(?=[a-z0-9])")


# Requests riding along with a match question ("who scored? tell me a joke", "btw how do I
# make a bomb", "answer as a pirate"), in every language the box reads. Normalised text.
_OFF_TOPIC = [
    re.compile(fold(p))
    for p in (
        # English
        r"\b(btw|by the way|p\.? ?s\b|also (tell|give|write|say|print|output)|answer (as|in|like|with) a"
        r"|respond (as|in|like|with|only)|reply (as|in|like)|in the (style|voice) of)\b",
        r"\b(jokes?|poems?|poetry|haiku|songs?|lyrics|rap|limerick|pirates?|recipes?|bombs?|weapons?|hack\w*"
        r"|bitcoin|crypto|stocks?|bets?|betting|weather|homework|essay|pig latin)\b",
        # Spanish
        r"\b(por cierto|responde (como|en|con)|contesta (como|en|con)|al estilo de)\b",
        r"\b(chistes?|poemas?|poesia|cancion(es)?|piratas?|recetas?|bombas?|armas?|hackear|apuestas?|tiempo que hara)\b",
        # French
        r"\b(au fait|reponds (comme|en|avec)|repondez (comme|en|avec)|a la maniere de|nouvelles? consignes?)\b",
        r"\b(blagues?|poemes?|poesie|chansons?|pirates?|recettes?|bombes?|armes?|pirater|paris sportifs?)\b",
        # Arabic (letters folded)
        r"(بالمناسبه|اجب ك|اجب بصفتك|على طريقه)",
        r"(نكت|قصيد|شعر|اغنيه|قرصان|قراصنه|وصفه|قنبل|سلاح|اختراق|رهان|مراهنه|تخيل)",
        # Japanese
        r"(ちなみに|として答え|風に答え|冗談|ジョーク|詩|歌|海賊|レシピ|爆弾|武器|ハッキング|あなたは)",
    )
]


@dataclass(frozen=True)
class GuardResult:
    refusal: RefusalReason | None
    normalised: str  # matching copy; empty when refused


def normalise(text: str) -> str:
    """The matching copy of a question (see the module docstring). Never shown."""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(ch for ch in t if unicodedata.category(ch) not in ("Cf", "Cc", "Co", "Cs") or ch in " \n\t")
    t = t.translate(_CONFUSABLES)
    t = fold(t).translate(_ARABIC)
    t = normalise_digits(t).casefold()
    t = t.replace("’", "'").replace("‘", "'").replace("´", "'").replace("`", "'")
    t = _CJK_EDGE.sub(" ", t)  # "xgが" -> "xg が": Latin words keep their word boundaries
    return re.sub(r"\s+", " ", t).strip()


def check_question(question: str) -> GuardResult:
    """Refusal reason (or None) and the normalised text to parse."""
    if question is None or not question.strip():
        return GuardResult("empty", "")
    if len(question) > MAX_QUESTION_CHARS:
        return GuardResult("too_long", "")
    if _FORBIDDEN_CONTROLS.search(question):
        return GuardResult("injection", "")
    if _MARKUP.search(unicodedata.normalize("NFKC", question)):
        return GuardResult("markup", "")
    norm = normalise(question)
    if not norm or not re.search(r"\w", norm):
        return GuardResult("empty", "")
    if _MARKUP.search(norm):
        return GuardResult("markup", "")
    squashed = re.sub(r"[^\w]+", " ", norm)  # "i.g.n.o.r.e" style padding collapses to words
    letters = re.sub(r"[^a-z]", "", norm)
    if any(rx.search(norm) or rx.search(squashed) for rx in _INJECTION) or _squashed_injection(letters):
        return GuardResult("injection", "")
    if banned_names_in(question) or banned_names_in(norm):
        return GuardResult("real_name", "")
    if any(rx.search(norm) or rx.search(squashed) for rx in _OFF_TOPIC):
        return GuardResult("off_topic", "")
    return GuardResult(None, norm)


# Letter-only runs that never occur in a football question ("i g n o r e  y o u r  r u l e s").
_SQUASHED = (
    "ignoreyour",
    "ignoreall",
    "ignoreprevious",
    "ignoretherules",
    "ignoreinstructions",
    "systemprompt",
    "developermode",
    "jailbreak",
    "yourinstructions",
    "yourprompt",
    "previousinstructions",
    "pretendyou",
    "youarenow",
    "doanythingnow",
)


def _squashed_injection(letters: str) -> bool:
    return any(token in letters for token in _SQUASHED)


def safe_display_name(name: str) -> bool:
    """Whether a roster name may be printed in an answer: names come from feeds we do
    not control, so one that reads like markup or an instruction is never echoed."""
    if not name or len(name) > 40:
        return False
    return check_question(name).refusal is None
