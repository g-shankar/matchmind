"""The studio crew orchestrator.

    event + stats -> Spotter -> Analyst -> Fact-checker        (process, once per event)
    bundle + viewer -> Commentator -> Fact-checker -> Producer  (render, per audience x language)

Every model step has a timeout (3 s), one repair retry when the answer does
not match the schema, then the template fallback with `fallback_reason`. Each
agent has a circuit breaker: 3 failures in a row open it for 60 s. A model
text the fact-checker rejects is never shown: the template text (which must
itself pass) is used instead. Every step is traced per moment.

World languages (docs/LANGUAGES.md): the card or recap is made in English
first (cached, so no extra model spend), then the Translator agent turns all of
its strings into the viewer's language in one request, and the fact-checker
checks the translation again. Translator off, failing or refused: the English
text is shown, with `fallback_reason` saying why.

Prompt-injection rule: agents only ever receive typed facts produced by our
own engine and answer with fixed-schema JSON.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

from pydantic import BaseModel

from matchmind.crew import analyst, commentator, telemetry
from matchmind.crew import claims as claims_mod
from matchmind.crew import recap as recap_mod
from matchmind.crew.alerts import AlertWatcher
from matchmind.crew.breaker import CircuitBreaker
from matchmind.crew.contracts import (
    AgentStep,
    Claim,
    CrewStatus,
    CrewTrace,
    Evidence,
    Explanation,
    FactCheck,
    Moment,
    MomentBundle,
    Narrative,
    OverlayCard,
    Recap,
    ViewerProfile,
    is_world_language,
)
from matchmind.crew.fact_checker import banned_names_in, check, check_all
from matchmind.crew.i18n import MissingFact, fill_first_with_template, pack
from matchmind.crew.llm import LLM, LLMSchemaError, ModelBudget, default_budget, make_llm
from matchmind.crew.producer import ViewerState, build_card, select
from matchmind.crew.spotter import Spotter, surname
from matchmind.crew.translator import TRANSIENT_REASONS, TranslationService, Translator
from matchmind.crew.wording import localise_teams
from matchmind.schema import Event
from matchmind.simulator.teams import Team
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

STEP_TIMEOUT_S = 3.0
TRACE_LIMIT = 500
TRACE_STEPS_LIMIT = 60
CACHE_LIMIT = 5000
PROCESSED_LIMIT = 50_000
RECAP_AI_LIMIT = 256
# A world-language recap is translated at most once per audience in this many seconds
# before full time (the last translation is reused in between), and once at full time.
AI_AGENTS = ("analyst", "commentator", "recap")


class Crew:
    def __init__(
        self,
        teams: dict[str, Team],
        llm: LLM | None = None,
        *,
        timeout_s: float = STEP_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
        budget: ModelBudget | None = None,
        translator: Translator | TranslationService | None = None,
    ) -> None:
        self.teams = teams
        self.llm: LLM = llm if llm is not None else make_llm()
        # None follows the switches (off by default); pass OffTranslator() where paid calls are not allowed.
        self.translation = (
            translator if isinstance(translator, TranslationService) else TranslationService(translator)
        )
        self.budget = budget if budget is not None else default_budget()
        self.timeout_s = timeout_s
        self.clock = clock
        self.spotter = Spotter(teams)
        self.alerts = AlertWatcher(teams)
        self.names: dict[str, str] = {p.player_id: p.name for t in teams.values() for p in t.players}
        # Kept exactly as written in every language.
        self.protected_names: tuple[str, ...] = tuple(
            sorted(
                {p.name for t in teams.values() for p in t.players}
                | {surname(p.name) for t in teams.values() for p in t.players}
                | {t.name for t in teams.values()}
                | {t.short_name for t in teams.values() if t.short_name}
            )
        )
        # Squad and club names -> player or club id, for the claims.
        self.roster_ids: dict[str, str] = {}
        for t in teams.values():
            for name in (t.name, t.short_name):
                if name:
                    self.roster_ids.setdefault(name, t.team_id)
            for p in t.players:
                self.roster_ids.setdefault(p.name, p.player_id)
                self.roster_ids.setdefault(surname(p.name), p.player_id)
        self.breakers = {agent: CircuitBreaker(clock) for agent in AI_AGENTS}
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="crew-llm")
        self._lock = threading.RLock()
        self._init_state()

    def _init_state(self) -> None:
        self._bundles: OrderedDict[str, MomentBundle] = OrderedDict()
        self._processed: OrderedDict[str, list[str]] = OrderedDict()
        self._cards: OrderedDict[tuple, OverlayCard] = OrderedDict()
        self._traces: OrderedDict[str, CrewTrace] = OrderedDict()
        self._recap_ai: OrderedDict[tuple, tuple[Any | None, str | None]] = OrderedDict()
        # (match, persona, language, club, focus) -> (when, translated recap, made at full time)
        self._recap_translated: OrderedDict[tuple, Recap] = OrderedDict()
        self._generation = getattr(self, "_generation", 0) + 1  # changes on every reset
        self._fallbacks = 0
        self._rejections = 0
        self._match_id: str | None = None
        self._health = telemetry.HealthTracker(self.clock)

    # ------------------------------------------------------------ public

    @property
    def mode(self) -> str:
        return "ai" if self.llm.enabled else "template"

    def reset(self) -> None:
        with self._lock:
            self.spotter.reset()
            self.breakers = {agent: CircuitBreaker(self.clock) for agent in AI_AGENTS}
            self._init_state()

    def restore(self, bundles: list[MomentBundle]) -> None:
        """After a reset for a jump: take back the moments already played, in order."""
        with self._lock:
            for b in bundles:
                self._bundles[b.moment.moment_id] = b

    def moments(self) -> list[Moment]:
        with self._lock:
            return [b.moment for b in self._bundles.values()]

    def bundle(self, moment_id: str) -> MomentBundle | None:
        with self._lock:
            return self._bundles.get(moment_id)

    def status(self) -> CrewStatus:
        with self._lock:
            return CrewStatus(
                mode=self.mode,  # type: ignore[arg-type]
                model=self.llm.model if self.llm.enabled else None,
                breakers_open=[
                    a
                    for a, b in self.breakers.items()
                    if b.open_until is not None and self.clock() < b.open_until
                ],
                moments=len(self._bundles),
                fallbacks=self._fallbacks,
                rejections=self._rejections,
                translator=self.translation.status(),
                health=self._health.snapshot(),
            )

    def traces(self, limit: int = 20) -> list[CrewTrace]:
        with self._lock:
            items = list(self._traces.values())[-max(0, limit) :] if limit > 0 else []
            return [t.model_copy(deep=True) for t in reversed(items)]

    def trace_for(self, moment_id: str) -> CrewTrace | None:
        """The trace of one moment (bounded to TRACE_STEPS_LIMIT steps), or None."""
        with self._lock:
            trace = self._traces.get(moment_id)
            return trace.model_copy(deep=True) if trace is not None else None

    def cached_cards(self, moment_id: str, limit: int = 32) -> list[OverlayCard]:
        """Cards already rendered for one moment (any audience), newest last. Never
        renders, so it never calls a model or the translator."""
        with self._lock:
            found = [c for k, c in self._cards.items() if k[0] == moment_id]
            return [c.model_copy(deep=True) for c in found[-limit:]]

    def _checked(self, verdict: FactCheck) -> FactCheck:
        self._health.verdict(verdict.ok)
        return verdict

    # ----------------------------------------------------------- process

    def process(
        self,
        event: Event,
        metrics: EventMetrics,
        snapshot: MatchStateSnapshot,
        players: dict[str, PlayerStats],
    ) -> list[MomentBundle]:
        """Spot, explain and fact-check the moments in one event. Processing
        the same event again returns the same bundles and adds nothing."""
        with self._lock:
            done = self._processed.get(event.event_id)
            if done is not None:
                return [self._bundles[m] for m in done if m in self._bundles]
            self._match_id = snapshot.match_id
            t0 = time.perf_counter()
            moments = self.spotter.spot(event, metrics, snapshot, players)
            spot_ms = (time.perf_counter() - t0) * 1000
            self._processed[event.event_id] = [m.moment_id for m in moments]
            self._health.moments(len(moments))
            while len(self._processed) > PROCESSED_LIMIT:
                self._processed.popitem(last=False)

        bundles: list[MomentBundle] = []
        for moment in moments:
            self._trace(moment, "spotter", spot_ms, "ok", moment.kind.value)
            explanation = self._explain(moment)
            replay = None
            if metrics.better_option is not None and moment.kind.value == "better_option":
                replay = metrics.better_option.model_dump(mode="json")
            elif metrics.unfound_run is not None and moment.kind.value == "unfound_run":
                replay = metrics.unfound_run.model_dump(mode="json")
            bundle = MomentBundle(moment=moment, explanation=explanation, replay=replay)
            with self._lock:
                self._bundles[moment.moment_id] = bundle
            bundles.append(bundle)
        return bundles

    def _explain(self, moment: Moment) -> Explanation:
        t0 = time.perf_counter()
        result, reason = self._ai(
            "analyst", analyst.ANALYST_SYSTEM, analyst.ai_payload(moment), analyst.AnalystOut
        )
        ms = (time.perf_counter() - t0) * 1000
        if result is not None:
            verdict = self._checked(
                check(result.why, moment.facts, "en", "why", strict_words=True, roster=self.protected_names)
            )
            self._trace(
                moment, "fact_checker", 0.0, "ok" if verdict.ok else "rejected", _short(verdict.reasons)
            )
            if verdict.ok:
                self._trace(moment, "analyst", ms, "ok", "ai")
                return Explanation(
                    moment_id=moment.moment_id,
                    why=result.why,
                    tactical_tag=result.tactical_tag,
                    evidence=analyst.evidence(moment),
                    produced_by="ai",
                )
            reason = "fact_check: " + verdict.reasons[0]
            self._rejected("analyst")
        explanation = analyst.template_explanation(moment, fallback_reason=reason)
        verdict = (
            self._checked(check(explanation.why, moment.facts, "en", "why", roster=self.protected_names))
            if explanation.why
            else None
        )
        if verdict is not None and not verdict.ok:
            explanation = explanation.model_copy(update={"why": ""})
            self._trace(moment, "fact_checker", 0.0, "rejected", _short(verdict.reasons))
        self._trace(moment, "analyst", ms, "fallback" if reason else "ok", reason or "template")
        return explanation

    # ------------------------------------------------------------ render

    def team_name(self, team_id: str | None) -> str | None:
        team = self.teams.get(team_id or "")
        return team.name if team else None

    def render(self, bundle: MomentBundle, profile: ViewerProfile) -> OverlayCard | None:
        """Voice one moment for one viewer profile. Cached per audience."""
        m = bundle.moment
        key = (
            m.moment_id,
            profile.persona,
            profile.language,
            profile.favourite_team,
            profile.focus_player_id,
        )
        with self._lock:
            cached = self._cards.get(key)
            if cached is not None:
                self._cards.move_to_end(key)
                return cached.model_copy(deep=True)

        if is_world_language(profile.language):
            english = self.render(bundle, profile.model_copy(update={"language": "en"}))
            if english is None:
                return None
            card = self._translate_card(english, m, profile.language)
            if card.fallback_reason not in TRANSIENT_REASONS:
                self._remember_card(key, card)
            return card.model_copy(deep=True)

        fav_name = self.team_name(profile.favourite_team)
        lang = profile.language
        why = bundle.explanation.why
        why_template: str | None = None
        if bundle.explanation.produced_by != "ai" or lang != "en":
            why, why_template = analyst.why_text_with_template(m, lang, fav_name)
        if why and not self._checked(check(why, m.facts, lang, "why", roster=self.protected_names)).ok:
            why = ""

        detail = f"{profile.persona}/{lang}"
        t0 = time.perf_counter()
        try:
            template, templates = commentator.template_narrative_with_templates(
                m, profile.persona, lang, fav_name, profile.focus_player_id
            )
        except MissingFact as exc:
            self._trace(m, "commentator", 0.0, "error", f"{detail}: no template fits ({exc.args[0]})")
            return None
        narrative: Narrative = template
        payload = commentator.ai_payload(m, why, profile.persona, lang, fav_name, profile.focus_player_id)
        result, reason = self._ai(
            "commentator", commentator.COMMENTATOR_SYSTEM, payload, commentator.CommentatorOut
        )
        ms = (time.perf_counter() - t0) * 1000
        if result is not None:
            verdict = self._checked(
                check_all(
                    {"headline": result.headline, "body": result.body},
                    m.facts,
                    lang,
                    strict_words=True,
                    roster=self.protected_names,
                )
            )
            if verdict.ok:
                narrative = Narrative(
                    moment_id=m.moment_id,
                    persona=profile.persona,
                    language=lang,
                    headline=result.headline,
                    body=result.body,
                    produced_by="ai",
                )
                self._trace(m, "fact_checker", 0.0, "ok", detail)
            else:
                reason = "fact_check: " + verdict.reasons[0]
                self._rejected("commentator")
                self._trace(m, "fact_checker", 0.0, "rejected", f"{detail}: {_short(verdict.reasons)}")
        if narrative is template:
            verdict = self._checked(
                check_all(
                    {"headline": template.headline, "body": template.body},
                    m.facts,
                    lang,
                    roster=self.protected_names,
                )
            )
            if not verdict.ok:
                self._trace(
                    m, "fact_checker", 0.0, "rejected", f"{detail} template: {_short(verdict.reasons)}"
                )
                with self._lock:
                    self._rejections += 1
                return None
            if reason:
                narrative = template.model_copy(update={"fallback_reason": reason})
        self._trace(
            m,
            "commentator",
            ms,
            "fallback" if reason else "ok",
            f"{detail}: {reason or narrative.produced_by}",
        )

        t1 = time.perf_counter()
        claims = claims_mod.card_claims(
            m,
            narrative.headline,
            narrative.body,
            why,
            lang,
            templates={
                "headline": templates["headline"] if narrative.produced_by == "template" else None,
                "body": templates["body"] if narrative.produced_by == "template" else None,
                "why": why_template,
            },
            roster=self.roster_ids,
        )
        card = build_card(bundle, narrative, why, profile, claims=claims)
        self._trace(m, "producer", (time.perf_counter() - t1) * 1000, "ok", f"{detail}: {card.slot}")
        self._remember_card(key, card)
        return card.model_copy(deep=True)

    def _remember_card(self, key: tuple, card: OverlayCard) -> None:
        with self._lock:
            self._cards[key] = card
            while len(self._cards) > CACHE_LIMIT:
                self._cards.popitem(last=False)

    # ------------------------------------------------------- translation

    def _translate_card(self, english: OverlayCard, moment: Moment, language: str) -> OverlayCard:
        """The English card in a world language: every string in one Translator
        request, then the fact-checker on the result. Any failure keeps the
        English text, marked with the reason."""
        t0 = time.perf_counter()
        labels = [e.label for e in english.evidence]
        texts = [english.headline, english.body, english.why, *labels]
        result = self.translation.translate(texts, language, self.protected_names)
        ms = (time.perf_counter() - t0) * 1000
        detail = f"{english.persona}/{language}"
        base = {
            "card_id": f"{moment.moment_id}:{english.persona}:{language}",
            "language": language,
            "rtl": False,
        }
        reason = result.reason
        if result.texts is not None:
            headline, body, why, *new_labels = result.texts
            parts: dict = {"headline": headline, "body": body}
            if why:
                parts["why"] = why
            reasons = list(
                self._checked(
                    check_all(parts, moment.facts, language, translated=True, roster=self.protected_names)
                ).reasons
            )
            if any(banned_names_in(label) for label in new_labels):
                reasons.append("label: real name not allowed")
            if not reasons:
                self._trace(moment, "fact_checker", 0.0, "ok", f"{detail}: translation")
                source = "cache" if result.cached else "azure"
                self._trace(moment, "translator", ms, "ok", f"{detail}: {source}")
                evidence = [
                    e.model_copy(update={"label": label})
                    for e, label in zip(english.evidence, new_labels, strict=True)
                ]
                return english.model_copy(
                    update={
                        **base,
                        "headline": headline,
                        "body": body,
                        "why": why,
                        "evidence": evidence,
                        "text_language": language,
                        "translated_by": "azure_ai_translator",
                        "claims": claims_mod.card_claims(
                            moment, headline, body, why, language, roster=self.roster_ids
                        ),
                    }
                )
            self.translation.note_rejected()
            self._trace(moment, "fact_checker", 0.0, "rejected", f"{detail} translation: {_short(reasons)}")
            reason = "translation_rejected"
        if reason != "translator_off":
            status = "rejected" if reason == "translation_rejected" else "fallback"
            self._trace(moment, "translator", ms, status, f"{detail}: {reason}")
        return english.model_copy(
            update={**base, "text_language": "en", "translated_by": None, "fallback_reason": reason}
        )

    def cards_for(
        self, bundles: list[MomentBundle], profile: ViewerProfile, state: ViewerState
    ) -> list[OverlayCard]:
        """Cards for one viewer from this tick's bundles: rendered, filtered,
        de-duplicated and timed by the producer."""
        cards = [c for c in (self.render(b, profile) for b in bundles) if c is not None]
        return select(cards, profile, state)

    def metric_alerts(
        self,
        event: Event,
        metrics: EventMetrics,
        snapshot: MatchStateSnapshot,
        players: dict[str, PlayerStats],
        profile: ViewerProfile,
        state: ViewerState,
    ) -> list[OverlayCard]:
        """`metric_alert` cards for the viewer's focus metric (template text,
        fact-checked)."""
        out: list[OverlayCard] = []
        fav_name = self.team_name(profile.favourite_team)
        world = is_world_language(profile.language)
        # World languages: the English alert, translated once it has passed the checks.
        text_profile = profile.model_copy(update={"language": "en"}) if world else profile
        lang = text_profile.language
        for alert in self.alerts.watch(event, metrics, snapshot, players, profile, state):
            m = alert.moment
            if m.moment_id in state.seen:
                continue
            v = localise_teams(dict(m.facts), lang, fav_name)
            try:
                (headline, body), (headline_t, body_t) = fill_first_with_template(
                    pack(lang)["metric"][alert.metric], v, lang
                )
            except MissingFact:
                continue
            verdict = self._checked(
                check_all({"headline": headline, "body": body}, m.facts, lang, roster=self.protected_names)
            )
            if not verdict.ok:
                with self._lock:
                    self._rejections += 1
                continue
            narrative = Narrative(
                moment_id=m.moment_id,
                persona=profile.persona,
                language=lang,
                headline=headline,
                body=body,
                produced_by="template",
            )
            bundle = MomentBundle(moment=m, explanation=analyst.template_explanation(m))
            evidence = [
                Evidence(
                    label=analyst.LABELS.get(k, k.replace("_", " ").capitalize()),
                    label_key=k,
                    value=val,
                    unit=analyst.unit_for(k),
                    source_event_id=m.source_event_ids[0],
                )
                for k, val in m.facts.items()
                if isinstance(val, int | float) and not isinstance(val, bool)
            ]
            claims = claims_mod.card_claims(
                m,
                headline,
                body,
                "",
                lang,
                templates={"headline": headline_t, "body": body_t},
                roster=self.roster_ids,
            )
            card = build_card(
                bundle, narrative, body, text_profile, slot="metric_alert", evidence=evidence, claims=claims
            )
            if world:
                card = self._translate_card(card, m, profile.language)
            state.remember(m.moment_id)
            out.append(card)
        return out

    # ------------------------------------------------------------- recap

    def recap(
        self,
        snapshot: MatchStateSnapshot,
        players: dict[str, PlayerStats],
        profile: ViewerProfile,
        moments: list[Moment] | None = None,
    ) -> Recap:
        """The recap so far. `moments` (in match order) overrides the crew's own,
        so a caller that jumped around the match can pass the true list.

        Model text is only asked for at full time, once per (persona, language,
        favourite club); before that, and once the budget is spent, templates.
        World languages get the English recap, translated and fact-checked again."""
        t0 = time.perf_counter()
        moments = self.moments() if moments is None else list(moments)
        if is_world_language(profile.language):
            english = self.recap(snapshot, players, profile.model_copy(update={"language": "en"}), moments)
            return self.translate_recap(english, moments, profile, snapshot)
        fav_name = self.team_name(profile.favourite_team)
        facts = recap_mod.recap_facts(moments, snapshot, players, profile, self.teams, self.names)
        full_time = recap_mod.is_full_time(moments)
        title, headline, paragraphs, recap_templates = recap_mod.template_texts_with_templates(
            facts, profile, full_time, fav_name
        )
        verdict = self._checked(
            recap_mod.check_texts(
                title, headline, paragraphs, facts, profile.language, roster=self.protected_names
            )
        )
        produced_by = "template"
        trace_id = f"recap-{snapshot.match_id}-{snapshot.clock_s:.0f}-{profile.persona}-{profile.language}"

        result, reason = None, None
        if full_time and self.llm.enabled:
            result, reason = self._ai_recap(snapshot.match_id, profile, facts, fav_name)
        if result is not None:
            ai_verdict = self._checked(
                recap_mod.check_texts(
                    result.title,
                    result.headline,
                    list(result.summary_paragraphs),
                    facts,
                    profile.language,
                    strict_words=True,
                    roster=self.protected_names,
                )
            )
            if ai_verdict.ok:
                title, headline, paragraphs = result.title, result.headline, list(result.summary_paragraphs)
                verdict, produced_by = ai_verdict, "ai"
                recap_templates = None
            else:
                self._rejected("recap")
                reason = "fact_check: " + ai_verdict.reasons[0]

        headline_templates: dict[str, str] = {}

        def headline_for(m: Moment) -> str | None:
            try:
                n, tpl = commentator.template_narrative_with_templates(
                    m, profile.persona, profile.language, fav_name, profile.focus_player_id
                )
            except MissingFact:
                return None
            if not check(n.headline, m.facts, profile.language, "headline", roster=self.protected_names).ok:
                return None
            headline_templates[m.moment_id] = tpl["headline"]
            return n.headline

        potm = recap_mod.player_of_the_match(players)
        out = recap_mod.build(
            snapshot.match_id,
            profile,
            facts,
            title,
            headline,
            paragraphs,
            recap_mod.key_moments(moments, headline_for),
            produced_by,
            verdict,
            potm.player_id if potm and "potm" in facts else None,
        )
        out.claims = self._recap_claims(out, moments, recap_templates, headline_templates)
        status = "fallback" if reason else ("ok" if verdict.ok else "rejected")
        with self._lock:
            trace = CrewTrace(moment_id=trace_id, match_clock=snapshot.match_clock, steps=[])
            trace.steps.append(
                AgentStep(
                    agent="recap",
                    ms=(time.perf_counter() - t0) * 1000,
                    status=status,
                    detail=reason or produced_by,
                )
            )
            self._store_trace(trace)
        # The span id leaves out persona and language: telemetry never carries viewer choices.
        span_id = f"recap-{snapshot.match_id}-{snapshot.clock_s:.0f}"
        self._span("recap", trace.steps[0].ms, status, reason or produced_by, span_id, "recap")
        return out

    def _recap_claims(
        self,
        recap: Recap,
        moments: list[Moment],
        templates: tuple[str, str, list[str]] | None,
        headline_templates: dict[str, str] | None = None,
    ) -> list[Claim]:
        """Claims for a recap: title, headline and paragraphs against the recap's
        facts (the goals line points at the goal events), key-moment lines
        against each moment's own facts and events."""
        lang = recap.text_language or recap.language
        goal_sources = [sid for m in moments if m.kind.value == "goal" for sid in m.source_event_ids]
        key_sources = {"goals_line": goal_sources}
        title_t, headline_t, paragraph_ts = templates if templates else (None, None, [])
        out: list[Claim] = []
        out += claims_mod.text_claims(
            recap.title,
            "title",
            recap.stats,
            lang,
            template=title_t,
            key_sources=key_sources,
            roster=self.roster_ids,
        )
        out += claims_mod.text_claims(
            recap.headline,
            "headline",
            recap.stats,
            lang,
            template=headline_t,
            key_sources=key_sources,
            roster=self.roster_ids,
        )
        for i, paragraph in enumerate(recap.summary_paragraphs):
            tpl = paragraph_ts[i] if i < len(paragraph_ts) else None
            out += claims_mod.text_claims(
                paragraph,
                "paragraph",
                recap.stats,
                lang,
                template=tpl,
                key_sources=key_sources,
                roster=self.roster_ids,
            )
        by_id = {m.moment_id: m for m in moments}
        for k in recap.key_moments:
            m = by_id.get(k.moment_id)
            if m is None:
                continue
            out += claims_mod.text_claims(
                k.headline,
                "key_moment",
                m.facts,
                lang,
                template=(headline_templates or {}).get(k.moment_id),
                source_event_ids=m.source_event_ids,
                roster=self.roster_ids,
            )
        return out[: claims_mod.MAX_CLAIMS]

    def translate_recap(
        self, english: Recap, moments: list[Moment], profile: ViewerProfile, snapshot: MatchStateSnapshot
    ) -> Recap:
        """The English recap in the viewer's world language. Before full time it stays
        in English (`fallback_reason` "recap_at_full_time"), so recap requests can never
        spend the translation budget live cards need; at full time it is translated once
        per audience and kept. Safe to call without the caller's crew lock: a reset
        while the request is out means the answer is returned but not kept."""
        t0 = time.perf_counter()
        key = (
            snapshot.match_id,
            profile.persona,
            profile.language,
            profile.favourite_team,
            profile.focus_player_id,
        )
        if not recap_mod.is_full_time(moments):
            return english.model_copy(
                update={
                    "language": profile.language,
                    "rtl": False,
                    "text_language": "en",
                    "translated_by": None,
                    "fallback_reason": "recap_at_full_time",
                }
            )
        with self._lock:
            generation = self._generation
            previous = self._recap_translated.get(key)
            if previous is not None:
                self._recap_translated.move_to_end(key)
                return previous.model_copy(deep=True)
        out = self._translate_recap(english, moments, profile.language, snapshot, t0)
        if out.translated_by is not None:
            with self._lock:
                if generation == self._generation:
                    self._recap_translated[key] = out
                    self._recap_translated.move_to_end(key)
                    while len(self._recap_translated) > RECAP_AI_LIMIT:
                        self._recap_translated.popitem(last=False)
        return out.model_copy(deep=True)

    def _translate_recap(
        self, english: Recap, moments: list[Moment], language: str, snapshot: MatchStateSnapshot, t0: float
    ) -> Recap:
        """The English recap in a world language: one Translator request for the
        title, headline, paragraphs and key-moment headlines, then the
        fact-checker (recap facts, and each key moment's own facts)."""
        n = len(english.summary_paragraphs)
        texts = [english.title, english.headline, *english.summary_paragraphs]
        texts += [k.headline for k in english.key_moments]
        result = self.translation.translate(texts, language, self.protected_names)
        reason = result.reason
        reasons: list[str] = []
        base = {"language": language, "rtl": False}
        out: Recap | None = None
        if result.texts is not None:
            title, headline = result.texts[0], result.texts[1]
            paragraphs = result.texts[2 : 2 + n]
            key_headlines = result.texts[2 + n :]
            verdict = self._checked(
                recap_mod.check_texts(
                    title,
                    headline,
                    paragraphs,
                    english.stats,
                    language,
                    translated=True,
                    roster=self.protected_names,
                )
            )
            reasons = list(verdict.reasons)
            facts_by_id = {m.moment_id: m.facts for m in moments}
            for k, text in zip(english.key_moments, key_headlines, strict=True):
                found = check(
                    text,
                    facts_by_id.get(k.moment_id, {}),
                    language,
                    "headline",
                    translated=True,
                    roster=self.protected_names,
                )
                reasons += [f"key moment {k.match_clock}: {r}" for r in found.reasons]
            if not reasons:
                key_moments = [
                    k.model_copy(update={"headline": h})
                    for k, h in zip(english.key_moments, key_headlines, strict=True)
                ]
                out = english.model_copy(
                    update={
                        **base,
                        "title": title,
                        "headline": headline,
                        "summary_paragraphs": paragraphs,
                        "key_moments": key_moments,
                        "fact_check": verdict,
                        "text_language": language,
                        "translated_by": "azure_ai_translator",
                    }
                )
                out.claims = self._recap_claims(out, moments, None)
            else:
                self.translation.note_rejected()
                reason = "translation_rejected"
        if out is None:
            out = english.model_copy(
                update={**base, "text_language": "en", "translated_by": None, "fallback_reason": reason}
            )
        if reason != "translator_off":
            status = (
                "ok" if reason is None else ("rejected" if reason == "translation_rejected" else "fallback")
            )
            detail = ("cache" if result.cached else "azure") if reason is None else reason
            if reasons:
                detail = f"{detail}: {_short(reasons)}"
            trace_id = f"recap-{snapshot.match_id}-{snapshot.clock_s:.0f}-{english.persona}-{language}"
            step = AgentStep(
                agent="translator", ms=(time.perf_counter() - t0) * 1000, status=status, detail=detail
            )
            self._health.step("translator", step.ms, status)
            with self._lock:
                trace = CrewTrace(moment_id=trace_id, match_clock=snapshot.match_clock, steps=[step])
                self._store_trace(trace)
        return out

    def _ai_recap(
        self, match_id: str, profile: ViewerProfile, facts: dict, fav_name: str | None
    ) -> tuple[Any | None, str | None]:
        """One model recap per (match, persona, language, favourite club), cached,
        failures included, so many viewers never mean many paid calls. The
        viewer's focus player is left out of the request; the cached text is
        still fact-checked against each viewer's own facts."""
        key = (match_id, profile.persona, profile.language, profile.favourite_team)
        with self._lock:
            if key in self._recap_ai:
                return self._recap_ai[key]
        shared = {k: v for k, v in facts.items() if not k.startswith("focus")}
        payload = {
            "audience": commentator.PERSONA_BRIEFS[profile.persona],
            "language": commentator.LANGUAGE_NAMES[profile.language],
            "full_time": True,
            "facts": shared,
            "favourite_team": fav_name,
        }
        outcome = self._ai("recap", recap_mod.RECAP_SYSTEM, payload, recap_mod.RecapOut)
        with self._lock:
            self._recap_ai[key] = outcome
            while len(self._recap_ai) > RECAP_AI_LIMIT:
                self._recap_ai.popitem(last=False)
        return outcome

    # ------------------------------------------------------------ AI calls

    def _ai(
        self, agent: str, system: str, payload: dict[str, Any], schema: type[BaseModel]
    ) -> tuple[Any | None, str | None]:
        """One model step: (validated answer, None) or (None, fallback reason).
        Template mode returns (None, None): templates are the normal path."""
        if not self.llm.enabled:
            return None, None
        breaker = self.breakers[agent]
        with self._lock:
            if breaker.is_open():
                self._fallbacks += 1
                return None, "circuit_open"
        reason = "error"
        user = dict(payload)
        for attempt in range(2):
            if not self.budget.take():
                breaker.cancel_probe()  # no call was made: let the next caller probe
                with self._lock:
                    self._fallbacks += 1
                return None, "budget"
            future = self._pool.submit(self.llm.complete_json, system, user, schema, self.timeout_s)
            try:
                result = future.result(timeout=self.timeout_s)
            except FuturesTimeout:
                future.cancel()
                reason = "timeout"
                break
            except LLMSchemaError:
                reason = "schema"
                if attempt == 0:
                    user = {
                        **payload,
                        "repair": f"Your last answer did not match the JSON schema {schema.__name__}. "
                        "Answer again with JSON only, exactly in the requested shape.",
                    }
                    continue
                break
            except Exception:  # noqa: BLE001 - any provider failure falls back
                reason = "error"
                break
            if not isinstance(result, schema):
                reason = "schema"
                break
            with self._lock:
                breaker.success()
            return result, None
        with self._lock:
            breaker.failure()
            self._fallbacks += 1
        return None, reason

    def _rejected(self, agent: str) -> None:
        with self._lock:
            self.breakers[agent].failure()
            self._rejections += 1
            self._fallbacks += 1

    # ------------------------------------------------------------- traces

    def _trace(self, moment: Moment, agent: str, ms: float, status: str, detail: str | None) -> None:
        with self._lock:
            trace = self._traces.get(moment.moment_id)
            if trace is None:
                trace = CrewTrace(moment_id=moment.moment_id, match_clock=moment.match_clock, steps=[])
                self._store_trace(trace)
            if len(trace.steps) < TRACE_STEPS_LIMIT:
                trace.steps.append(AgentStep(agent=agent, ms=round(ms, 2), status=status, detail=detail))
        self._span(agent, ms, status, detail, moment.moment_id, moment.kind.value)

    def _span(
        self, agent: str, ms: float, status: str, detail: str | None, moment_id: str, kind: str | None
    ) -> None:
        """OpenTelemetry span for one step (a no-op unless tracing is configured),
        and the step's latency and status for the rolling service levels."""
        self._health.step(agent, ms, status)
        telemetry.record_step(
            agent=agent,
            status=status,
            ms=ms,
            moment_id=moment_id,
            moment_kind=kind,
            detail=detail,
            model=self.llm.model if self.llm.enabled else None,
        )

    def _store_trace(self, trace: CrewTrace) -> None:
        self._traces[trace.moment_id] = trace
        self._traces.move_to_end(trace.moment_id)
        while len(self._traces) > TRACE_LIMIT:
            self._traces.popitem(last=False)


def _short(reasons: list[str]) -> str:
    return "; ".join(reasons[:3]) if reasons else "ok"
