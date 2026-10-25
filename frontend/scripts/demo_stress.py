"""Recorded "Stress test the crew" results for the offline demo (?demo=1).

Writes `frontend/public/demo/demo-stress.json`: for one demo moment of each
headline kind, every fault (`matchmind.crew.stress.FAULTS`) in every studio
language, run by the server's own sandbox (`matchmind.crew.stress.run`) on the
bundled demo match. Nothing here writes text: the steps and the safe cards come
from the engine's templates and fact-checker. Deterministic output.

Run from the repository root:

    PYTHONPATH=backend/src python3 frontend/scripts/demo_stress.py
"""

from __future__ import annotations

import json
from pathlib import Path

from matchmind.api.session import Engines, MatchSession, load_events
from matchmind.crew import stress
from matchmind.crew.contracts import STUDIO_LANGUAGES, ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.llm import TemplateLLM
from matchmind.crew.translator import OffTranslator
from matchmind.simulator.teams import get_team
from matchmind.stats.state import StatsEngine

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "frontend" / "public" / "demo"
KINDS = ("goal", "big_chance", "card", "better_option", "rocket_shot", "unfound_run", "momentum_swing")
STRESS_VERSION = 1


def build() -> dict:
    events = load_events()
    home, away = str(events[0].details["home"]), str(events[0].details["away"])
    teams = {home: get_team(home), away: get_team(away)}
    engines = Engines(
        stats=StatsEngine,
        crew=lambda t: Crew(t, llm=TemplateLLM(), translator=OffTranslator()),
        bookmark_crew=lambda t: Crew(t, llm=TemplateLLM(), translator=OffTranslator()),
    )
    session = MatchSession(events, teams=teams, engines=engines, base_rate=10)
    session.play_to_end()
    by_event = {
        (b.moment.kind.value, eid): b
        for b in session._bundles.values()
        for eid in b.moment.source_event_ids[-1:]
    }
    demo = json.loads((DEMO / "demo-match.json").read_text())
    results: dict[str, dict[str, dict[str, dict]]] = {}
    for kind in KINDS:
        for m in demo["moments"]:
            bundle = by_event.get((m["kind"], m["event_id"]))
            if m["kind"] != kind or bundle is None:
                continue
            per_lang: dict[str, dict[str, dict]] = {}
            for lang in STUDIO_LANGUAGES:
                per_lang[lang] = {}
                for fault in stress.FAULTS:
                    out = stress.run(teams, bundle, fault, ViewerProfile(language=lang))
                    assert out["safe"], (m["moment_id"], fault, lang)
                    out["moment_id"] = m["moment_id"]
                    if out["card"]:
                        out["card"]["moment_id"] = m["moment_id"]
                    per_lang[lang][fault] = out
            results[m["moment_id"]] = per_lang
            break
    return {
        "stress_version": STRESS_VERSION,
        "match_id": demo["match_id"],
        "note": "Recorded from the server's sandbox crew on the bundled demo match; template mode, no model.",
        "results": results,
    }


if __name__ == "__main__":
    out = DEMO / "demo-stress.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
