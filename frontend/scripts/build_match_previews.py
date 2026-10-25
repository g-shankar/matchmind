"""Build the small per-match preview files for the "Choose a match" picker.

Reads every synthetic match listed in `backend/data/matches/manifest.json` and
writes `frontend/public/previews/<match_id>.json` plus an `index.json`. Each
preview holds the clubs, the final score, the score story (goals with their
minutes), storyline tags derived from those goals and VAR reviews, and the key
moment: the ball path of the possession that ended in the decisive goal, the
shot's freeze frame and its chance quality from `matchmind.stats`.

Nothing is invented: positions are copied from the events, the score is
counted from goal events (minus goals overturned by VAR) and checked against
the manifest, and chance quality comes from the stats engine.

Run from the repository root:

    PYTHONPATH=backend/src python frontend/scripts/build_match_previews.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from matchmind.schema import Event
from matchmind.simulator.teams import get_team
from matchmind.stats.better_option import shot_chance_quality

ROOT = Path(__file__).resolve().parents[2]
MATCHES = ROOT / "backend" / "data" / "matches"
OUT = ROOT / "frontend" / "public" / "previews"
# The only match the offline demo and the default server session play.
PLAYABLE = {"MM-DEMO-001"}
LATE_MINUTE = 80
PATH_STEPS = 5


def _r(v: float) -> float:
    return round(float(v), 1)


def _minute(ev: dict) -> int:
    return int(ev["clock_s"] // 60) + 1


def _team(team_id: str) -> dict:
    t = get_team(team_id)
    return {
        "team_id": t.team_id,
        "name": t.name,
        "short_name": t.short_name,
        "primary_color": t.primary_color,
        "secondary_color": t.secondary_color,
    }


def build(entry: dict) -> dict:
    raw = [json.loads(line) for line in (MATCHES / entry["file"]).read_text().splitlines() if line.strip()]
    home, away = entry["home"], entry["away"]
    overturned = {e["reviewed_event_id"] for e in raw if e["type"] == "var_review" and e.get("outcome") == "overturned"}
    var_reviews = sum(1 for e in raw if e["type"] == "var_review")

    goals: list[dict] = []
    score = {home: 0, away: 0}
    for e in raw:
        if e["type"] == "shot" and e.get("outcome") == "goal" and e["event_id"] not in overturned:
            score[e["team"]] += 1
            goals.append({"event": e, "team": e["team"], "minute": _minute(e), "period": e["period"], "home": score[home], "away": score[away]})
    final = f"{score[home]}-{score[away]}"
    if final != entry["score"]:
        sys.exit(f"{entry['match_id']}: counted {final}, manifest says {entry['score']}")

    winner = home if score[home] > score[away] else away if score[away] > score[home] else None
    # The decisive goal: the one that put the winner ahead for good (else the last goal).
    decisive = goals[-1] if goals else None
    trailed = False
    if winner:
        def split(g: dict) -> tuple[int, int]:
            return (g["home"], g["away"]) if winner == home else (g["away"], g["home"])

        trailed = any(split(g)[1] > split(g)[0] for g in goals)
        lead_from = None
        for i, g in enumerate(goals):
            w, lo = split(g)
            if w > lo and lead_from is None:
                lead_from = i
            if w <= lo:
                lead_from = None
        decisive = goals[lead_from] if lead_from is not None else decisive

    tags: list[str] = []
    if trailed:
        tags.append("comeback")
    if decisive and winner and decisive["minute"] >= LATE_MINUTE:
        tags.append("late_winner")
    if overturned:
        tags.append("var_drama")
    if len(goals) >= 4:
        tags.append("goal_fest")
    if winner and abs(score[home] - score[away]) == 1 and not tags:
        tags.append("tight_win")
    if not goals:
        tags.append("goalless")

    key = None
    if decisive:
        shot = decisive["event"]
        idx = raw.index(shot)
        steps = []
        for e in reversed(raw[:idx]):
            if e.get("possession_id") != shot["possession_id"] or len(steps) >= PATH_STEPS:
                break
            if e.get("start") and e.get("end") and e["type"] in ("pass", "carry", "dribble"):
                steps.append({"kind": e["type"], "x1": _r(e["start"]["x"]), "y1": _r(e["start"]["y"]), "x2": _r(e["end"]["x"]), "y2": _r(e["end"]["y"])})
        steps.reverse()
        steps.append({"kind": "shot", "x1": _r(shot["start"]["x"]), "y1": _r(shot["start"]["y"]), "x2": _r(shot["end"]["x"]), "y2": _r(shot["end"]["y"])})
        cq = shot_chance_quality(Event.model_validate(shot), home)
        key = {
            "event_id": shot["event_id"],
            "team": shot["team"],
            "minute": decisive["minute"],
            "period": decisive["period"],
            "chance_quality": cq,
            "path": steps,
            "players": [
                {"x": _r(p["x"]), "y": _r(p["y"]), "mate": bool(p["teammate"]), "actor": bool(p["actor"])}
                for p in shot.get("freeze_frame") or []
            ],
        }

    return {
        "match_id": entry["match_id"],
        "playable": entry["match_id"] in PLAYABLE,
        "home": _team(home),
        "away": _team(away),
        "score": {"home": score[home], "away": score[away]},
        "goals": [{"team": g["team"], "minute": g["minute"], "period": g["period"], "home": g["home"], "away": g["away"]} for g in goals],
        "var_reviews": var_reviews,
        "var_overturned": len(overturned),
        "events": entry["events"],
        "tags": tags,
        "key_moment": key,
    }


def main() -> None:
    manifest = json.loads((MATCHES / "manifest.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for entry in manifest:
        preview = build(entry)
        (OUT / f"{entry['match_id']}.json").write_text(json.dumps(preview, separators=(",", ":")) + "\n")
        index.append(entry["match_id"])
    (OUT / "index.json").write_text(json.dumps({"matches": index}) + "\n")
    print(f"wrote {len(index)} previews to {OUT}")


if __name__ == "__main__":
    main()
