"""Questions about PitchPulse itself: "is this real data?", "who built you?", "is this AI?".

They get one fixed answer written by the team (the `about` intent: synthetic data,
invented clubs, numbers from the stats engine, the crew's mode, made by the
PitchPulse team as a hackathon entry). Nothing from the question is ever printed.

The same wrapped-request rule as match questions applies: once the provenance
phrase, filler words and the words below are taken out, at most one unknown word
may be left, so "who built you? btw how do I make a bomb" is still refused.

A provenance question that names a real competition or club ("is this real
Premier League data?") is answered with the same fixed text, because the honest
answer to it is "no, it is synthetic"; the real name is never repeated.
"""

# Pattern tables are kept one language per line for review.
# ruff: noqa: E501

from __future__ import annotations

import re

from matchmind.crew.fact_checker import banned_names_in, fold

from .guard import carries_another_request, normalise
from .parser import MAX_UNKNOWN_WORDS, Roster, unknown_words


def _rx(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{fold(p)})" for p in patterns))


# Normalised text (guard.normalise): case-folded, accents stripped, Arabic letters folded.
ABOUT = _rx(
    # English
    r"\b(is|are) (this|it|that|the data|the match|the game|these|they|the players|the clubs|the teams) (real|fake|live|synthetic|made up|invented|actual|genuine|simulated|an? ai|ai)\b",
    r"\b(real|actual|genuine|live) (data|match|game|players?|clubs?|teams?|stats)\b",
    r"\bwho (made|built|created|developed|designed|makes|runs|wrote|programmed) (you|this|the (app|site|demo|studio)|pitchpulse)\b",
    r"\b(are you|is this|is it) (an? )?(ai|bot|robot|human|real person|person|machine)\b",
    r"\bwhere (does|do) (the|your|this) (data|numbers|stats) come from\b",
    r"\bwhat is pitchpulse\b|\babout pitchpulse\b",
    # Spanish
    r"\b(es|son) (real|reales|falso|falsos|inventad[oa]s?|sintetic[oa]s?|en directo|una ia|ia)\b",
    r"\bdatos (reales|de verdad)\b",
    r"\bquien (te |lo )?(hizo|ha hecho|creo|ha creado|construyo|desarrollo|programo|diseno)\b",
    r"\b(eres|es esto) (una )?(ia|inteligencia artificial|bot|robot|humano|persona)\b",
    r"\bde donde (salen|vienen) (los|tus) (datos|numeros)\b",
    # French
    r"\b(est-ce|c'est|est ce) (reel|vrai|faux|invente|synthetique|en direct|une ia|de l'ia)\b",
    r"\b(sont-ils|sont-elles|sont ils) (reels|vrais|inventes)\b",
    r"\bdonnees (reelles|vraies)\b",
    r"\bqui (t'a|vous a|l'a|a) (cree|fait|construit|developpe|concu|programme)\b",
    r"\b(es-tu|etes-vous|es tu|etes vous) (une )?(ia|intelligence artificielle|bot|robot|humain)\b",
    r"\bd'ou viennent (les|tes|vos) (donnees|chiffres)\b",
    # Arabic (letters folded: no hamza on alef, teh marbuta as heh)
    r"بيانات حقيقيه|هل (هذا|هذه|هي|هو) (حقيقي|حقيقيه|مزيف|مزيفه|اصطناعي|اصطناعيه)",
    r"من (صنعك|صممك|بناك|برمجك|طورك|انشاك|صنع هذا|صمم هذا|بنى هذا|طور هذا)",
    r"هل انت (ذكاء اصطناعي|روبوت|انسان|بوت)|ذكاء اصطناعي",
    r"من اين (تاتي|جاءت) (البيانات|الارقام)",
    # Japanese
    r"本物のデータ|実際のデータ|本当のデータ|実在|架空|本物",
    r"誰が作|誰が開発|誰が制作|作ったのは誰|開発したのは誰",
    r"ai ?ですか|ai ?なの|ロボット|人間ですか",
    r"データはどこから|データの出所",
)

# Words a provenance question carries besides its phrase (normalised form), one language a line.
_ABOUT_WORDS: frozenset[str] = frozenset(
    normalise(
        """
    real fake synthetic data stats numbers made built created ai app site demo studio pitchpulse premier league
    football soccer official licensed actual genuine live invented simulated bot robot human person you your this
    datos reales sintetico inventado ia hecho creado estadisticas futbol oficial
    donnees reelles reel synthetique invente cree construit appli statistiques officiel
    بيانات حقيقيه حقيقي مزيف اصطناعي ذكاء التطبيق الموقع كره القدم رسمي
    """
    ).split()
)


def is_about(question: str, roster: Roster) -> bool:
    """A question about PitchPulse itself, carrying nothing else."""
    norm = normalise(question)
    if not ABOUT.search(norm) or carries_another_request(norm):
        return False
    rest = ABOUT.sub(" ", norm)
    for name in banned_names_in(question):  # named only to ask whether we use it: never echoed
        rest = rest.replace(normalise(name), " ")
    unknown = [w for w in unknown_words(rest, roster) if w not in _ABOUT_WORDS]
    return len(unknown) <= MAX_UNKNOWN_WORDS
