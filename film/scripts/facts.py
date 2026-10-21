"""Pull every number and name the film may show out of the Matchmind engine
and its open dataset, into film/facts.json. Each fact keeps the sentence it
backs and a link to its source line, so every on-screen line can be traced.

Run from the repo root with the engine installed (`pip install -e backend`):
    python film/scripts/facts.py [--branch feat/matchmind-engine]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from matchmind.simulator import pitch
from matchmind.simulator.teams import TEAMS
from matchmind.stats import metrics

FILM = Path(__file__).resolve().parents[1]
# The engine checkout to read; defaults to this repo.
ROOT = Path(os.environ.get("MATCHMIND_ROOT", FILM.parent))
DATA = ROOT / "backend/data/matches/MM-DEMO-001.jsonl"
HOME = "NBR"
REPO = "https://github.com/g-shankar/matchmind"


def load():
    rows = [json.loads(l) for l in DATA.read_text().splitlines() if l.strip()]
    return rows


def link(branch: str, path: str, line: int | None = None) -> str:
    return f"{REPO}/blob/{branch}/{path}" + (f"#L{line}" if line else "")


def name_of(pid: str) -> str:
    team, _ = pid.split("-")
    return TEAMS[team].player(pid).name


def surname(pid: str) -> str:
    return name_of(pid).split()[-1]


def better_option(shot: dict) -> dict:
    """Shot taken vs the square ball, from the engine's deterministic metrics."""
    ff = shot["freeze_frame"]
    open_id = next(l.split(":")[1] for l in shot["labels"] if l.startswith("better_option:"))
    def att(p):  # the shooting team's attacking frame (towards x = 105)
        return metrics.to_attacking((p["x"], p["y"]), shot["team"], HOME)

    shooter = att(shot["start"])
    mate_pos = att(next(p for p in ff if p["player_id"] == open_id))
    keeper = next((att(p) for p in ff if p["keeper"] and not p["teammate"]), None)
    opps = [att(p) for p in ff if not p["teammate"] and not p["keeper"]]
    all_opps = opps + ([keeper] if keeper else [])

    def cq(p):
        return metrics.chance_quality(
            p, blockers=metrics.blockers_in_cone(p, opps), keeper_on_line=metrics.keeper_on_line(p, keeper)
        )

    shot_cq = cq(shooter)
    alt_cq = cq(mate_pos)
    ps, lane = metrics.pass_success_probability(shooter, mate_pos, all_opps)
    nearest = min(pitch.dist(mate_pos, o) for o in opps)
    alt_value = round(ps * alt_cq, 3)
    return {
        "shooter_id": shot["player_id"],
        "teammate_id": open_id,
        "shot_chance_quality": shot_cq,
        "alt_chance_quality": alt_cq,
        "pass_success": ps,
        "alt_value": alt_value,
        "times_better": round(alt_value / shot_cq, 1),
        "pass_distance_m": round(pitch.dist(shooter, mate_pos), 1),
        "nearest_marker_m": round(nearest, 1),
        "shooter_distance_to_goal_m": round(pitch.distance_to_goal(shooter), 1),
        "mate_distance_to_goal_m": round(pitch.distance_to_goal(mate_pos), 1),
        "shot_speed_kmh": metrics.kmh(shot.get("ball_speed_mps")),
        "freeze_frame": ff,
        "shot_end": shot["end"],
    }


def drafts(add, bo: dict) -> None:
    """Crew lines the film shows until the crew API exists. Numbers are filled
    from the engine's facts so they still trace; the words are drafts."""
    sh, mt = bo["shooter"].split()[-1], bo["teammate"].split()[-1]
    p = lambda v: f"{v:.0%}"
    add("crew.analyst", f"{bo['clock']} {sh} shot from {bo['shooter_distance_to_goal_m']} m: chance {p(bo['shot_chance_quality'])}. "
        f"Square ball to {mt}, {bo['pass_distance_m']} m: {p(bo['pass_success'])} to arrive, then {p(bo['alt_chance_quality'])}. "
        f"Value {bo['alt_value']:.2f} vs {bo['shot_chance_quality']:.2f}: {bo['times_better']}x.")
    add("crew.fan.en", f"{sh} went for glory and the keeper said no. {mt} was free in the middle. "
        f"That pass was worth {bo['times_better']} times more.")
    add("crew.fan.es", f"{sh} buscó la gloria y el portero dijo que no. {mt} estaba solo en el centro. "
        f"Ese pase valía {str(bo['times_better']).replace('.', ',')} veces más.")
    add("crew.fan.ar", f"سدّد {'أسانتي' if sh == 'Asante' else sh} فتصدّى الحارس. كان {'كيريغان' if mt == 'Kerrigan' else mt} حرًّا في الوسط. "
        f"تلك التمريرة كانت تساوي {bo['times_better']} أضعاف.")
    add("crew.factcheck", f"Blocked: \"a 40% chance\" is not in the moment's facts. Replaced with {p(bo['alt_chance_quality'])}.",
        {"blocked": "40%", "replacement": p(bo["alt_chance_quality"])})
    add("crew.fallback", "Model unavailable: Commentator switched to template mode.")
    add("azure.stack", "Azure Container Apps, Azure Event Hubs, Azure OpenAI with managed identity.")
    add("repo.quality", "Tests, CI and secret scanning on every push.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="feat/matchmind-engine")
    args = ap.parse_args()
    b = args.branch
    rows = load()
    dpath = str(DATA.relative_to(ROOT))
    facts: list[dict] = []

    def add(fid, text, value, path=dpath, line=None):
        facts.append({"id": fid, "text": text, "value": value, "source": link(b, path, line)})

    start = rows[0]
    home, away = TEAMS["NBR"], TEAMS["HCY"]
    add("match.id", f"Demo match {start['match_id']}, fully synthetic.", start["match_id"], line=1)
    add("match.events", f"The demo match streams {len(rows):,} events.", len(rows))
    for t in (home, away):
        add(f"team.{t.team_id}", f"{t.name}: {t.style}.", {"name": t.name, "short": t.short_name,
            "formation": t.formation, "primary": t.primary_color, "secondary": t.secondary_color},
            path="backend/src/matchmind/simulator/teams.py")

    goals = [(i, r) for i, r in enumerate(rows, 1) if r["type"] == "shot" and r.get("outcome") == "goal"]
    score = {"NBR": 0, "HCY": 0}
    timeline = []
    for line, g in goals:
        score[g["team"]] += 1
        timeline.append({"clock": g["match_clock"], "team": g["team"], "scorer": name_of(g["player_id"]),
                         "score": f"{score['NBR']}-{score['HCY']}", "line": line})
        add(f"goal.{g['match_clock']}", f"{g['match_clock']} goal, {name_of(g['player_id'])} "
            f"({g['team']}), {score['NBR']}-{score['HCY']}.", timeline[-1], line=line)
    add("match.final", f"Full time: {home.name} {score['NBR']}-{score['HCY']} {away.name}.",
        dict(score), line=len(rows))
    reds = [(i, r) for i, r in enumerate(rows, 1) if r["type"] == "card" and "scripted:red_card" in r["labels"]]
    if reds:
        line, r = reds[0]
        add("card.red", f"{r['match_clock']} red card, {name_of(r['player_id'])} ({r['team']}).",
            {"clock": r["match_clock"], "player": name_of(r["player_id"])}, line=line)

    for line, s in [(i, r) for i, r in enumerate(rows, 1) if r["type"] == "shot"
                    and any(l.startswith("better_option:") for l in r["labels"])]:
        bo = better_option(s)
        k = f"spha.{s['team']}"
        bo.update({"clock": s["match_clock"], "outcome": s["outcome"], "event_id": s["event_id"],
                   "shooter": name_of(bo["shooter_id"]), "teammate": name_of(bo["teammate_id"])})
        add(k, f"{s['match_clock']}: {bo['shooter']} shot from {bo['shooter_distance_to_goal_m']} m "
            f"(chance {bo['shot_chance_quality']:.0%}); a {bo['pass_distance_m']} m pass to "
            f"{bo['teammate']} ({bo['pass_success']:.0%} to arrive, chance {bo['alt_chance_quality']:.0%}) "
            f"was worth {bo['times_better']}x more. Outcome: {s['outcome']}.", bo, line=line)

    drafts(add_draft := lambda fid, text, value=None: facts.append(
        {"id": fid, "text": text, "value": value, "source": "crew draft (replace with crew API output)",
         "draft": True}), next(f["value"] for f in facts if f["id"] == "spha.NBR"))

    bo = next(f["value"] for f in facts if f["id"] == "spha.NBR")
    mate = TEAMS["NBR"].player(bo["teammate_id"])
    first = next(g for g in timeline if g["scorer"] == mate.name)
    add("player.focus", f"{mate.name}, #{mate.number}, {mate.position}, {TEAMS['NBR'].name}: scored at "
        f"{first['clock']}, free in the middle at {bo['clock']}.",
        {"name": mate.name, "number": mate.number, "position": mate.position, "goal": first["clock"]},
        path="backend/src/matchmind/simulator/teams.py")
    before = [g for g in timeline if g["clock"] < bo["clock"] and "+" not in g["clock"]]
    add("score.at.spha", f"Score at {bo['clock']}: {before[-1]['score'] if before else '0-0'}.",
        before[-1]["score"] if before else "0-0", line=before[-1]["line"] if before else None)
    facts.append({"id": "crew.roles", "draft": True, "source": "project goal (PitchPulse brief)",
                  "text": "Spotter finds the moment; Analyst pulls the evidence; Commentator writes it; "
                          "Producer decides what airs; Fact-checker blocks unproven numbers.",
                  "value": [["Spotter", "Finds the moment", "Moment"], ["Analyst", "Pulls the evidence", "Evidence"],
                            ["Commentator", "Writes it", "Script"], ["Producer", "Decides what airs", "Rundown"],
                            ["Fact-checker", "Blocks unproven numbers", "Verified"]]})

    out = FILM / "facts.json"
    out.write_text(json.dumps({"branch": b, "facts": facts}, indent=1, ensure_ascii=False) + "\n")
    for f in facts:
        print(f["id"], "|", f["text"])


if __name__ == "__main__":
    main()
