"""Rule-based question -> `Intent`. No model, no network, same answer every time.

The parser reads the guard's normalised copy of the question (accent-free,
case-folded, Arabic letters folded, ASCII digits) with keyword tables for
English, Spanish, French, Arabic and Japanese. Clubs and
players are resolved only against the match's own squads: full name, surname,
unique first name, club name, short code, "home"/"away", or a shirt number
("number 9", "#9", "dorsal 9", "رقم 9"). A capitalised name that is not in
the squads ends the question with a refusal, never a guess.
"""

# Keyword tables are kept one concept per line for review.
# ruff: noqa: E501

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from matchmind.crew.fact_checker import fold
from matchmind.simulator.teams import Team

from .guard import RefusalReason, normalise
from .intents import Intent
from .vocab import AR_PREFIXES, FILLER, JA


def _rx(*patterns: str) -> re.Pattern[str]:
    # Folded like the text they read (`guard.normalise`): Japanese voiced kana lose their
    # marks there (ド -> ト), so the patterns must lose them too.
    return re.compile("|".join(f"(?:{fold(p)})" for p in patterns))


# --- Keyword tables (normalised text) ------------------------------------------------------------

SCORERS = _rx(
    r"\bwho (has |have |had )?(scored|got the goals?|got on the scoresheet)\b",
    r"\b(goal ?scorers?|scorers?)\b",
    r"\b(quien|quienes) (ha |han )?(marcado|marco|marcaron|anotado|anoto|anotaron)\b",
    r"\bgoleador(es)?\b",
    r"\bqui (a|ont) (marque|inscrit)\b",
    r"\bbuteurs?\b",
    r"من سجل|من احرز|الهداف|مسجلو الاهداف|مسجلي الاهداف",
    r"得点者|誰が(得点|点|ゴール)|得点した|ゴールを決めた",
)
SCORE = _rx(
    r"\bscore(line)?\b",
    r"\bresult\b",
    r"\bwho('s| is) (winning|ahead|leading|in front)\b",
    r"\bmarcador\b",
    r"\bresultado\b",
    r"\bcomo (va|van|esta|quedo) (el partido|el marcador)?",
    r"\bquien (gana|va ganando)\b",
    r"\bqui gagne\b",
    r"\bou en est\b",
    r"النتيجه|من يفوز|من المتقدم",
    r"スコア|何対何",
)
VAR = _rx(
    r"\bvar\b",
    r"\bvideo (review|referee|assistant)\b",
    r"\bruled out\b",
    r"\bdisallowed\b",
    r"\banulad[oa]s?\b",
    r"\bannules?\b",
    r"حكم الفيديو|الفار|الغي",
)
BETTER = _rx(
    r"should (he|she|they|i)?\s?(have|'ve)? ?pass",
    r"\bbetter option\b",
    r"\bpass(ed)? instead\b",
    r"\bdebio pasar",
    r"\bmejor opcion\b",
    r"\baurait du passer\b",
    r"\bmeilleure option\b",
    r"كان (عليه|يجب) (ان )?يمرر|التمرير كان افضل|خيار افضل|ان يمرر",
    r"パスすべき",
)
CARDS = _rx(
    r"\b(yellow|red) cards?\b",
    r"\bbookings?\b",
    r"\bbooked\b",
    r"\bsent off\b",
    r"\bcards?\b",
    r"\btarjetas?\b",
    r"\bamonestad",
    r"\bexpulsad",
    r"\bcartons?\b",
    r"\bexpulse",
    r"بطاق|انذار|طرد",
    r"カード|退場",
)
EXPLAIN_CUE = _rx(
    r"\b(explain|meaning|means|mean|define|definition|calculated|computed|measured|worked out)\b",
    r"\bwhat (is|are|'s|s|does) (an? )?(?!the\b)",
    r"\b(que es|que son|que significa|que mide|explica|explicame|definicion)\b",
    r"\b(qu'est-ce que|qu'est ce que|c'est quoi|explique|expliquez|que signifie|que veut dire|definition)\b",
    r"ما هو|ما هي|ما معنى|اشرح|ماذا يعني|كيف يحسب",
    r"とは|って何|説明",
)
TEAM_CUE = _rx(
    r"\b(which|what) (team|side|club)\b",
    r"\b(que|cual) equipo\b",
    r"\bquel(le)? (equipe|club)\b",
    r"اي فريق|اي نادي",
)
TOP_CUE = _rx(
    r"\b(who|whos|which player|most|top|best|highest|leader|leads|leading|furthest|farthest|fastest|quickest)\b",
    r"\b(quien|quienes|que jugador|mas|mejor|lider|lidera)\b",
    r"\b(qui|quel joueur|le plus|meilleur|en tete)\b",
    r"\bمن\b|اي لاعب|الاكثر|الاسرع|افضل|اكثر",
    r"誰|最も|一番|最速",
)
WHAT_HAPPENED = _rx(
    r"\b(what happened|happen|happened|summary|story)\b",
    r"\b(que (paso|ha pasado|sucedio)|resumen)\b",
    r"\b(que s'est-il passe|ce qui s'est passe|resume)\b",
    r"ماذا حدث|ما الذي حدث",
    r"何があった",
)
CONTROL = _rx(
    r"\b(control|chaos|tempo|cci|chaotic)\b",
    r"\b(caos|ritmo|caotico)\b",
    r"\b(controle|rythme|chaotique)\b",
    r"السيطره|الفوضى|الايقاع",
)
MOMENTUM = _rx(
    r"\bmomentum\b",
    r"\bon top\b",
    r"\b(dominat\w*|in control|front foot|pressure|pressing|pushing|playing better|better side)\b",
    r"\b(impulso|inercia|domina\w*|presion|juega mejor|mejor equipo)\b",
    r"\b(dynamique|domine\w*|pression|joue mieux|meilleure equipe|elan)\b",
    r"الزخم|الضغط|يسيطر|المسيطر|الطرف الافضل|يهيمن",
    r"優勢|勢い|プレッシャー",
)
HOME = _rx(
    r"\bhome (side|team)\b",
    r"\bhosts\b",
    r"\b(local|locales)\b",
    r"\bdomicile\b",
    r"اصحاب الارض|المضيف",
    r"ホーム",
)
AWAY = _rx(
    r"\baway (side|team)\b",
    r"\bvisitors?\b",
    r"\bvisitantes?\b",
    r"\bvisiteurs?\b",
    r"الضيوف|الضيف",
    r"アウェイ|アウェー",
)

# Metric vocabulary, most specific first. (metric id, pattern)
_METRIC_WORDS: list[tuple[str, re.Pattern[str]]] = [
    (
        "shots_on_target",
        _rx(
            r"\bshots? on target\b",
            r"\btiros? a (puerta|porteria)\b",
            r"\btirs? cadres?\b",
            r"على المرمى",
            r"枠内",
        ),
    ),
    (
        "key_passes",
        _rx(
            r"\bkey pass(es)?\b",
            r"\bpases? clave\b",
            r"\bpasses? cles?\b",
            r"تمريرات مفتاحيه|التمريرات المفتاحيه",
            r"キーパス",
        ),
    ),
    (
        "pass_accuracy",
        _rx(
            r"\bpass(ing)? accuracy\b",
            r"\bprecision (de|del|en el) pase",
            r"\bprecision des passes\b",
            r"دقه التمرير",
            r"パス成功率",
        ),
    ),
    (
        "xg",
        _rx(
            r"\bxg\b",
            r"\bexpected goals?\b",
            r"\bgoles esperados\b",
            r"\bbuts attendus\b",
            r"الاهداف المتوقعه",
            r"期待ゴール",
        ),
    ),
    (
        "xa",
        _rx(
            r"\bxa\b",
            r"\bexpected assists?\b",
            r"\basistencias esperadas\b",
            r"\bpasses decisives attendues\b",
        ),
    ),
    (
        "xt",
        _rx(
            r"\bxt\b",
            r"\bexpected threat\b",
            r"\bamenaza esperada\b",
            r"\bmenace attendue\b",
            r"التهديد المتوقع",
        ),
    ),
    ("ppda", _rx(r"\bppda\b")),
    (
        "field_tilt",
        _rx(r"\bfield tilt\b", r"\binclinacion del campo\b", r"\binclinaison du terrain\b", r"ميل الملعب"),
    ),
    (
        "pressure_index",
        _rx(r"\bpressure index\b", r"\bindice de presion\b", r"\bindice de pression\b", r"مؤشر الضغط"),
    ),
    (
        "pass_difficulty",
        _rx(
            r"\bpass difficulty\b",
            r"\bdificultad del pase\b",
            r"\bdifficulte de (la )?passe\b",
            r"صعوبه التمرير",
        ),
    ),
    (
        "unfound_run",
        _rx(
            r"\bunfound runs?\b",
            r"\bdesmarques? sin premio\b",
            r"\bappels? non servis?\b",
            r"انطلاقه بلا تمريره",
        ),
    ),
    ("control_chaos", _rx(r"\bcontrol.?chaos\b", r"\bcci\b", r"\bcontrol.?caos\b", r"\bcontrole.?chaos\b")),
    ("possession", _rx(r"\bpossession\b", r"\bposesion\b", r"الاستحواذ", r"ポゼッション|支配率")),
    (
        "sprints",
        _rx(r"\bsprints?\b", r"\besprints?\b", r"\bacelerones?\b", r"الانطلاقات السريعه", r"スプリント"),
    ),
    (
        "top_speed",
        _rx(
            r"\b(top speed|fastest|quickest|speed|pace|km/h|kmh|quick)\b",
            r"\b(velocidad|mas rapido|rapidez)\b",
            r"\b(vitesse|plus rapide)\b",
            r"السرعه|الاسرع|اسرع",
            r"最速|スピード|速い",
        ),
    ),
    (
        "distance",
        _rx(
            r"\b(distance|furthest|farthest|covered|ran the most|run the most|running|kilometres|kilometers|km)\b",
            r"\b(distancia|recorrido|kilometros|mas ha corrido|corrido|corrio)\b",
            r"\b(distance|parcouru|kilometres|le plus couru|couru)\b",
            r"المسافه|ركض|جري",
            r"走行距離|走った",
        ),
    ),
    (
        "tackles",
        _rx(r"\btackles?\b", r"\bentradas?\b", r"\btacles?\b", r"الافتكاك|افتكاك|التدخلات", r"タックル"),
    ),
    (
        "interceptions",
        _rx(
            r"\binterceptions?\b", r"\bintercepciones?\b", r"\binterceptions?\b", r"اعتراض", r"インターセプト"
        ),
    ),
    ("touches", _rx(r"\btouches\b", r"\btoques\b", r"\bballons touches\b", r"لمسات", r"タッチ")),
    ("passes", _rx(r"\bpass(es)?\b", r"\bpases?\b", r"\bpasses?\b", r"تمرير", r"パス")),
    ("shots", _rx(r"\bshots?\b", r"\btiros?\b", r"\bdisparos?\b", r"\btirs?\b", r"تسديد", r"シュート")),
]
_TEAM_METRIC = {
    "xg": "xg", "shots": "shots", "shots_on_target": "shots_on_target", "possession": "possession",
    "pass_accuracy": "pass_accuracy", "passes": "passes", "tackles": "tackles", "distance": "distance",
}  # fmt: skip
_PLAYER_METRIC = {
    "distance": "distance", "top_speed": "top_speed", "passes": "passes", "tackles": "tackles", "xg": "xg",
    "shots": "shots", "sprints": "sprints", "key_passes": "key_passes", "interceptions": "interceptions",
    "touches": "touches",
}  # fmt: skip
_EXPLAIN_METRIC = {
    "xg": "chance_quality", "xa": "xa", "xt": "xt_delta", "ppda": "ppda", "field_tilt": "field_tilt_pct",
    "pressure_index": "pressure_index", "pass_difficulty": "pass_difficulty", "unfound_run": "projected_chance_quality",
    "control_chaos": "control_chaos", "possession": "possession_pct", "sprints": "sprints",
    "top_speed": "top_speed_kmh", "distance": "distance_km", "pass_accuracy": "pass_accuracy",
}  # fmt: skip
_EXPLAIN_EXTRA: list[tuple[str, re.Pattern[str]]] = [
    ("times_better", BETTER),
    ("momentum", _rx(r"\bmomentum\b", r"\binercia\b", r"\bdynamique\b", r"الزخم")),
    ("pressure_index", _rx(r"\bpressure\b", r"\bpresion\b", r"\bpression\b", r"الضغط")),
    ("control_chaos", CONTROL),
]

_NUMBER = re.compile(
    r"(?:#\s?|\bno\.?\s?|\bnumber\s|\bnumero\s|\bdorsal\s|\bn°\s?|\bnr\.?\s?|رقم\s?|背番号\s?)(\d{1,2})\b"
)
_RANGE = re.compile(
    r"(?:\bbetween|\bfrom|\bentre|\bdesde|\bdel?|\bdu|بين|من)\s*(?:the\s|el\s|la\s|le\s|minute\s|minutes\s|minuto\s"
    r"|minutos\s|min\s|الدقيقه\s)*(\d{1,3})\s*'?\s*(?:min\w*\s)?(?:and|to|-|–|y|a|al|hasta|et|à|و|الى|حتى|ل)\s*"
    r"(?:the\s|el\s|la\s|le\s|l'|minute\s|minuto\s|الدقيقه\s)*(\d{1,3})\b"
)
_LAST = re.compile(
    r"\b(?:last|past|ultimos|dernieres)\s(\d{1,2})\s(?:minutes|minutos|min)\b|(?:اخر|آخر)\s(\d{1,2})\s(?:دقائق|دقيقه)"
)
_FIRST_HALF = _rx(
    r"\bfirst half\b",
    r"\bprimera parte\b",
    r"\bprimer tiempo\b",
    r"\bpremiere mi-?temps\b",
    r"الشوط الاول",
    r"前半",
)
_SECOND_HALF = _rx(
    r"\bsecond half\b", r"\bsegunda parte\b", r"\bsegundo tiempo\b", r"\b(seconde|deuxieme) mi-?temps\b",
    r"الشوط الثاني", r"後半",
)  # fmt: skip

# Capitalised words that are not names, so they never trigger "unknown player".
_NOT_NAMES = frozenset(
    {
        "var", "xg", "xa", "xt", "ppda", "cci", "km", "i", "ok", "fc", "who", "what", "how", "which", "when",
        "is", "the", "and", "has", "have", "did", "does", "do", "tell", "show", "give", "any", "can", "could",
        "would", "should", "was", "were", "are", "explain", "between", "from", "in", "on", "at", "for", "of",
        "a", "an", "it", "its", "he", "she", "they", "we", "you", "me", "my", "home", "away", "first", "second",
        "half", "goal", "goals", "yellow", "red", "card", "cards", "momentum", "pressure", "possession", "please",
        "quien", "quienes", "que", "como", "cual", "cuantos", "cuantas", "cuanto", "el", "la", "los", "las", "y",
        "en", "de", "del", "un", "una", "por", "para", "hay", "ha", "han", "es", "son", "esta", "va", "dime",
        "explica", "qui", "quoi", "quel", "quelle", "combien", "le", "les", "et", "est", "du", "des", "une", "il",
        "elle", "ont", "explique", "c'est", "qu'est-ce", "entre", "local", "visitante", "domicile", "next",
        "latest", "last", "who's", "what's", "whos", "whats", "should've", "mr", "man", "match", "game",
        "partido", "juego", "jeu", "minute", "minutes", "minuto", "minutos", "sobre", "sur",
    }
)  # fmt: skip
_CAPITALISED = re.compile(r"(?<![\w'’])([A-ZÀ-ÖØ-Þ][\w'’\-]+)")


@dataclass
class Roster:
    """Every way a question may name a club or a player of this match."""

    teams: Mapping[str, Team]
    team_alias: dict[str, str] = field(default_factory=dict)
    player_alias: dict[str, str] = field(default_factory=dict)
    numbers: dict[int, list[str]] = field(default_factory=dict)
    known_words: set[str] = field(default_factory=set)
    home_id: str = ""
    away_id: str = ""

    @classmethod
    def build(cls, teams: Mapping[str, Team], home_id: str, away_id: str) -> Roster:
        r = cls(teams=teams, home_id=home_id, away_id=away_id)
        firsts: dict[str, list[str]] = {}
        for t in teams.values():
            for alias in {t.name, t.short_name or "", t.team_id, re.sub(r"\s+FC$", "", t.name)}:
                if alias:
                    r.team_alias[normalise(alias)] = t.team_id
                    r.known_words.update(fold(w).casefold() for w in alias.split())
            for p in t.players:
                parts = p.name.split()
                r.player_alias[normalise(p.name)] = p.player_id
                if len(parts) > 1:
                    r.player_alias.setdefault(normalise(parts[-1]), p.player_id)
                    firsts.setdefault(normalise(parts[0]), []).append(p.player_id)
                r.numbers.setdefault(p.number, []).append(p.player_id)
                r.known_words.update(fold(w).casefold() for w in parts)
        for first, ids in firsts.items():
            if len(ids) == 1:
                r.player_alias.setdefault(first, ids[0])
        return r

    def team_of(self, player_id: str) -> str | None:
        for t in self.teams.values():
            if any(p.player_id == player_id for p in t.players):
                return t.team_id
        return None


@dataclass(frozen=True)
class ParseResult:
    intent: Intent | None = None
    refusal: RefusalReason | None = None
    clarify: tuple[str, ...] = ()  # player ids sharing the shirt number asked for
    clarify_number: int | None = None


def _find_alias(norm: str, aliases: Mapping[str, str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for alias in sorted(aliases, key=len, reverse=True):
        for m in re.finditer(rf"(?<!\w){re.escape(alias)}(?:'s)?(?!\w)", norm):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), aliases[alias]))
    return sorted(found)


def _unknown_names(question: str, roster: Roster) -> bool:
    """A capitalised Latin word (not the first word of a sentence) that is not a
    squad, club or football word: someone outside this match."""
    for m in _CAPITALISED.finditer(question):
        word = fold(m.group(1)).casefold().strip("'’-")
        word = re.sub(r"'s$", "", word)
        before = question[: m.start()].rstrip()
        sentence_start = not before or before[-1] in ".?!¿¡:;,\"'(«"
        if word in _NOT_NAMES or word in roster.known_words or len(word) < 3:
            continue
        if sentence_start and not any(w in roster.known_words for w in (word,)):
            # First word of a sentence: only a problem when it is followed by "'s" or another capital.
            follow = question[m.end() : m.end() + 3]
            if not follow.startswith(("'s", "’s")) and not re.match(r"\s[A-Z]", follow):
                continue
        return True
    return False


MAX_UNKNOWN_WORDS = 1
_NON_LATIN = re.compile(r"[\u0600-\u06ff\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]")
_CJK_RUN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]+")
_WORD = re.compile(r"[^\W\d_]+")


def _keyword_tables() -> list[re.Pattern[str]]:
    tables = [
        SCORERS, SCORE, VAR, BETTER, CARDS, EXPLAIN_CUE, TEAM_CUE, TOP_CUE, WHAT_HAPPENED, CONTROL,
        MOMENTUM, HOME, AWAY, _NUMBER, _RANGE, _LAST, _FIRST_HALF, _SECOND_HALF,
    ]  # fmt: skip
    tables += [rx for _, rx in _METRIC_WORDS] + [rx for _, rx in _EXPLAIN_EXTRA]
    # Arabic keywords are stems ("تسديد" in "التسديدات"): take out the whole word.
    return [re.compile(rf"{_AR_LETTERS}(?:{rx.pattern}){_AR_LETTERS}") for rx in tables]


_AR_LETTERS = r"[\u0600-\u06ff]*"


def _known_word(word: str, roster: Roster) -> bool:
    if len(word) < 2 or word in FILLER or word in roster.known_words:
        return True
    return any(word.startswith(p) and word[len(p) :] in FILLER for p in AR_PREFIXES if len(word) > len(p) + 1)


def unknown_words(norm: str, roster: Roster) -> list[str]:
    """The words of a normalised question that are neither football keywords, nor
    names from this match, nor filler (ask/vocab.py). Never logged or shown."""
    rest = norm
    for rx in _KEYWORD_TABLES:
        rest = rx.sub(" ", rest)
    for alias in sorted({**roster.team_alias, **roster.player_alias}, key=len, reverse=True):
        rest = re.sub(rf"(?<!\w){re.escape(alias)}(?:'s)?(?!\w)", " ", rest)
    unknown: list[str] = []
    for run in _CJK_RUN.findall(rest):
        for word in JA:
            run = run.replace(word, " ")
        left = run.replace(" ", "")
        unknown += [left[i : i + 2] for i in range(0, len(left), 2)]  # about one word per two characters
    rest = _CJK_RUN.sub(" ", rest)
    unknown += [w for w in _WORD.findall(rest) if not _known_word(w, roster)]
    return unknown


_KEYWORD_TABLES = _keyword_tables()


def _metric(norm: str) -> str | None:
    for key, rx in _METRIC_WORDS:
        if rx.search(norm):
            return key
    return None


def _window(norm: str, now_minute: int) -> tuple[int, int] | None:
    m = _RANGE.search(norm)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a < b <= 130:
            return a, b
    m = _LAST.search(norm)
    if m:
        n = int(m.group(1) or m.group(2))
        if 0 < n <= 130:
            return max(0, now_minute - n), max(now_minute, 1)
    if WHAT_HAPPENED.search(norm):
        if _FIRST_HALF.search(norm):
            return 0, 45
        if _SECOND_HALF.search(norm):
            return 45, 90
    return None


def parse(question: str, norm: str, roster: Roster, now_minute: int = 0) -> ParseResult:
    """`question` is the raw text (for capitalised names), `norm` the guard's copy.

    A question we can read but that carries other requests ("what's the xG? btw how do
    I make a bomb", "who scored? answer as a poem") is refused as off-topic: once every
    football word, name and filler word is taken out, at most one unknown word may be
    left (`MAX_UNKNOWN_WORDS`)."""
    result = _parse(question, norm, roster, now_minute)
    if result.intent is None:
        return result
    unknown = unknown_words(norm, roster)
    if len(unknown) > MAX_UNKNOWN_WORDS:
        return ParseResult(refusal="off_topic")
    if any(_NON_LATIN.search(w) for w in unknown):
        # A word in Arabic or Japanese script we cannot place is most likely a name
        # (capitals do not tell us there): never answer as if it were not there.
        return ParseResult(refusal="unknown_player")
    return result


def _parse(question: str, norm: str, roster: Roster, now_minute: int = 0) -> ParseResult:
    if _unknown_names(question, roster):
        return ParseResult(refusal="unknown_player")

    teams = _find_alias(norm, roster.team_alias)
    team: str | None = teams[0][1] if teams else None
    if team is None and HOME.search(norm):
        team = roster.home_id
    elif team is None and AWAY.search(norm):
        team = roster.away_id

    # Player: by name (club and player names never overlap: club aliases are matched first).
    masked = norm
    for alias in sorted(roster.team_alias, key=len, reverse=True):
        masked = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", " ", masked)
    players = _find_alias(masked, roster.player_alias)
    player = players[0][1] if players else None
    if player is None:
        n = _NUMBER.search(norm)
        if n:
            ids = roster.numbers.get(int(n.group(1)), [])
            if team is not None:
                ids = [pid for pid in ids if roster.team_of(pid) == team]
            if len(ids) == 1:
                player = ids[0]
            elif len(ids) > 1:
                return ParseResult(clarify=tuple(ids), clarify_number=int(n.group(1)))
            else:
                return ParseResult(refusal="unknown_player")
    if player is not None and team is None:
        team = None  # a player's club comes from the roster, not the question

    metric = _metric(norm)

    def make(**kw) -> ParseResult:
        return ParseResult(intent=Intent(**kw))

    if SCORERS.search(norm):
        return make(kind="scorers", team=team)
    if BETTER.search(norm) and not EXPLAIN_CUE.search(norm):
        return make(kind="better_option")
    if VAR.search(norm) and not EXPLAIN_CUE.search(norm):
        return make(kind="var")
    if CARDS.search(norm):
        return make(kind="cards", team=team)
    if EXPLAIN_CUE.search(norm) and player is None and team is None:
        explain = _EXPLAIN_METRIC.get(metric or "")
        if explain is None:
            explain = next((key for key, rx in _EXPLAIN_EXTRA if rx.search(norm)), None)
        if explain is not None:
            return make(kind="explain_metric", metric=explain)
    window = _window(norm, now_minute)
    if window is not None:
        return make(kind="window", from_minute=window[0], to_minute=window[1])
    if SCORE.search(norm):
        return make(kind="score")
    if player is not None:
        pm = _PLAYER_METRIC.get(metric or "")
        return make(kind="player_stats", player_id=player, metric=pm)
    if (
        metric in _PLAYER_METRIC
        and not TEAM_CUE.search(norm)
        and (TOP_CUE.search(norm) or metric not in _TEAM_METRIC)
    ):
        return make(kind="top_player", metric=_PLAYER_METRIC[metric], team=team)
    if metric in ("control_chaos",) or (CONTROL.search(norm) and metric is None):
        return make(kind="control")
    if MOMENTUM.search(norm) and metric not in _TEAM_METRIC:
        return make(kind="momentum")
    if metric in _TEAM_METRIC:
        return make(kind="team_stat", metric=_TEAM_METRIC[metric], team=team)
    if metric == "pressure_index" or metric == "field_tilt":
        return make(kind="momentum")
    return ParseResult()  # nothing we answer: off-topic (unless the optional model path maps it)
