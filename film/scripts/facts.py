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
    """Shot taken vs the square ball. Uses the engine's own trigger
    (matchmind.stats.better_option) when present, else the same metrics here."""
    try:
        from matchmind.schema import Event
        from matchmind.stats.better_option import analyse_shot
    except ImportError:
        return _better_option_local(shot)
    bo = analyse_shot(Event.model_validate(shot), HOME)
    if bo is None:
        raise SystemExit(f"engine does not flag {shot['event_id']} as a better-option moment")
    att = lambda xy: metrics.to_attacking((xy.x, xy.y), shot["team"], HOME)
    return {
        "shooter_id": bo.shooter_id,
        "teammate_id": bo.teammate_id,
        "shot_chance_quality": bo.shot_chance_quality,
        "alt_chance_quality": bo.alt_chance_quality,
        "pass_success": bo.pass_success,
        "alt_value": bo.alt_value,
        "times_better": bo.times_better,
        "pass_distance_m": bo.pass_distance_m,
        "nearest_marker_m": bo.nearest_marker_m,
        "shooter_distance_to_goal_m": round(pitch.distance_to_goal(att(bo.shooter_pos)), 1),
        "mate_distance_to_goal_m": round(pitch.distance_to_goal(att(bo.teammate_pos)), 1),
        "shot_speed_kmh": metrics.kmh(shot.get("ball_speed_mps")),
        "freeze_frame": shot["freeze_frame"],
        "shot_end": shot["end"],
        "computed_by": "matchmind.stats.better_option.analyse_shot",
    }


def _better_option_local(shot: dict) -> dict:
    """Fallback for engine checkouts without the better-option module."""
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



API = os.environ.get("MATCHMIND_API", "http://127.0.0.1:8000")


def _get(path: str):
    import urllib.request

    with urllib.request.urlopen(API + path, timeout=10) as r:
        return json.loads(r.read())


def crew_lines(add, bo: dict) -> bool:
    """Real crew output for the moment, from the running API (python -m matchmind.api).
    Returns False when the API is not reachable, so the drafts are used instead."""
    try:
        marks = _get("/api/match/bookmarks")
    except OSError:
        return False
    mid = next(m["moment_id"] for m in marks if m["moment_id"].endswith(bo["event_id"]))
    src = f"crew API: GET /api/match/moment/{mid}"
    tac = _get(f"/api/match/moment/{mid}?persona=tactical&lang=en")
    add("crew.analyst", f"{tac['headline']}. {tac['body']}", {"headline": tac["headline"], "body": tac["body"],
        "produced_by": tac["produced_by"]}, path=None, src=src + "?persona=tactical&lang=en")
    for lang in ("en", "es", "ar"):
        c = _get(f"/api/match/moment/{mid}?persona=casual&lang={lang}")
        add(f"crew.fan.{lang}", f"{c['headline']} {c['body']}", {"headline": c["headline"], "body": c["body"],
            "rtl": c["rtl"], "produced_by": c["produced_by"]}, path=None, src=src + f"?persona=casual&lang={lang}")
    from matchmind.crew.fact_checker import check

    facts = {e["label"]: e["value"] for e in tac["evidence"]}
    wrong = f"{bo['shooter'].split()[-1]} had a 40% chance"
    res = check(wrong, facts, "en")
    add("crew.factcheck", f"Fact-checker on \"{wrong}\": {'; '.join(res.reasons)}.",
        {"blocked": "40%", "replacement": f"{bo['shot_chance_quality']:.0%}", "ok": res.ok, "reasons": res.reasons},
        path=None, src="matchmind.crew.fact_checker.check")
    goal = next((m for m in marks if m["kind"] == "goal" and any(
        x["kind"] == "correction" and x["moment_id"].endswith(str(int(m["moment_id"][-5:]) + 1).zfill(5))
        for x in marks)), None)
    if goal:
        cor = next(m for m in marks if m["kind"] == "correction")
        for key, m in (("crew.var.goal", goal), ("crew.var.correction", cor)):
            c = _get(f"/api/match/moment/{m['moment_id']}?persona=casual&lang=en")
            add(key, f"{c['headline']} {c['body']}", {"headline": c["headline"], "body": c["body"],
                "clock": m["match_clock"], "retracts": c.get("retracts", [])},
                path=None, src=f"crew API: GET /api/match/moment/{m['moment_id']}?persona=casual&lang=en")
    st = _get("/api/crew/status")
    add("crew.fallback", f"No model connected: the crew runs in {st['mode']} mode, and every card says produced_by: "
        f"{tac['produced_by']}.", st, path=None, src="crew API: GET /api/crew/status")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="feat/matchmind-engine")
    args = ap.parse_args()
    b = args.branch
    rows = load()
    dpath = str(DATA.relative_to(ROOT))
    facts: list[dict] = []

    def add(fid, text, value, path=dpath, line=None, src=None):
        facts.append({"id": fid, "text": text, "value": value, "source": src or link(b, path, line)})

    start = rows[0]
    home, away = TEAMS["NBR"], TEAMS["HCY"]
    add("match.id", f"Demo match {start['match_id']}, fully synthetic.", start["match_id"], line=1)
    add("match.events", f"The demo match streams {len(rows):,} events.", len(rows))
    for t in (home, away):
        add(f"team.{t.team_id}", f"{t.name}: {t.style}.", {"name": t.name, "short": t.short_name,
            "formation": t.formation, "primary": t.primary_color, "secondary": t.secondary_color},
            path="backend/src/matchmind/simulator/teams.py")

    # a goal VAR overturns never counts; the film tells that story on its own card
    overturned = {r["reviewed_event_id"]: (i, r) for i, r in enumerate(rows, 1)
                  if r["type"] == "var_review" and r.get("outcome") == "overturned"}
    goals = [(i, r) for i, r in enumerate(rows, 1) if r["type"] == "shot" and r.get("outcome") == "goal"
             and r["event_id"] not in overturned]
    for gid, (vline, v) in overturned.items():
        g = next(r for r in rows if r["event_id"] == gid)
        add("var.ruled_out", f"{g['match_clock']} goal by {name_of(g['player_id'])} ruled out by VAR "
            f"({v['review_reason']}) at {v['match_clock']}.",
            {"goal_clock": g["match_clock"], "var_clock": v["match_clock"], "scorer": name_of(g["player_id"]),
             "surname": surname(g["player_id"]), "reason": v["review_reason"],
             "score_after": f"{v['details']['score_home']}-{v['details']['score_away']}",
             "score_with_goal": f"{v['details']['score_home'] + (g['team'] == HOME)}-"
                                f"{v['details']['score_away'] + (g['team'] != HOME)}"}, line=vline)
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

    live = crew_lines(add, next(f["value"] for f in facts if f["id"] == "spha.NBR"))
    drafts(add_draft := lambda fid, text, value=None: None if live and fid.startswith("crew.") else facts.append(
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
    # Infrastructure as code (PR #2); wording stays true before the first deploy.
    add("azure.stack", "Container Apps deploys the engine and crew API; the match streams into Event Hubs; "
        "the crew is built for Azure OpenAI with managed identity, no keys.",
        ["Deploys the engine and crew API", "The match streams into Event Hubs", "Built for managed identity, no keys"],
        path=None, src=f"{REPO}/pull/2 (deployment/azure_bicep/main.bicep)")
    add("repo.quality", "Tests, CI and secret scanning on every push.", None, path=".github/workflows/ci.yml")
    facts.append({"id": "crew.roles", "source": link(b, "backend/src/matchmind/crew/__init__.py"),
                  "text": "Spotter finds the moment; Analyst pulls the evidence; Commentator writes it; "
                          "Producer decides what airs; Fact-checker blocks unproven numbers.",
                  "value": [["Spotter", "Finds the moment", "Moment"], ["Analyst", "Pulls the evidence", "Evidence"],
                            ["Commentator", "Writes it", "Script"], ["Producer", "Decides what airs", "Rundown"],
                            ["Fact-checker", "Blocks unproven numbers", "Verified"]]})

    add("engine.deterministic", "Deterministic football metrics. No randomness, no models: same event in, "
        "same number out.", None, path="backend/src/matchmind/stats/metrics.py", line=1)
    # Headings and voice lines that carry no data; listed so every on-screen line traces here.
    for cid, text in [("copy.tagline", "Every broadcast has a crew. So we built one, with AI."),
                      ("copy.byline", "powered by the Matchmind engine"),
                      ("copy.pipeline", "One synthetic match. Five stages."),
                      ("copy.crew", "Five agents. One job each."),
                      ("copy.spha", "Should he have passed?"),
                      ("copy.split", "Same moment, two audiences. The analyst gets the evidence trail. The fan gets the story."),
                      ("copy.overlay", "Broadcast overlay · corrections go on air too"),
                      ("copy.azure", "Built for Azure")]:
        facts.append({"id": cid, "text": text, "value": None, "source": "film copy (storyboard.md)"})
    # On-screen labels built from engine values, and every voiceover caption.
    mt, x = bo["teammate"].split()[-1], f"{bo['times_better']:.1f}"
    home_, away_ = TEAMS["NBR"], TEAMS["HCY"]
    fin = next(f["value"] for f in facts if f["id"] == "match.final")
    for cid, text in [
        ("copy.kicker.match", f"{start['match_id']} · {home_.name} v {away_.name} · no real clubs or players"),
        ("copy.kicker.crew", "The AI studio crew"),
        ("copy.stages", "Ingest | Stats engine | AI studio crew | Broadcast overlays | A view for every viewer"),
        ("copy.square", f"Square ball to {mt}, {bo['pass_distance_m']} m: arrives"),
        ("copy.verdict", f"{x}× the value. He should have passed."),
        ("copy.lowerthird", f"Square ball to {mt} was worth {x}× the shot."),
        ("copy.ui", "Replay | Ruled out | VAR | Fallback | events streamed | Nearest marker | Value: pass vs shot | "
                    f"Verdict | {mt}'s chance after the pass | {mt} · free | English | Español | العربية | Analyst | Fan"),
        ("copy.endline", f"Demo match: {home_.name} {fin['NBR']}–{fin['HCY']} {away_.name}. Fully synthetic."),
    ]:
        facts.append({"id": cid, "text": text, "value": None, "source": "film copy built from engine facts (facts.py)"})
    for line in json.loads((FILM / "vo.json").read_text())["lines"]:
        cap = line.get("caption", True)
        if cap is not False:
            facts.append({"id": f"copy.vo.{line['id']}", "text": line["text"] if cap is True else cap,
                          "value": None, "source": "voiceover script (vo.json)"})

    out = FILM / "facts.json"
    out.write_text(json.dumps({"branch": b, "facts": facts}, indent=1, ensure_ascii=False) + "\n")
    for f in facts:
        print(f["id"], "|", f["text"])


if __name__ == "__main__":
    main()
