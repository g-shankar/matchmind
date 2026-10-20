import sys
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matchmind.simulator.publisher import read_jsonl

ev = read_jsonl("backend/data/matches/MM-DEMO-001.jsonl")
shot = next(e for e in ev if e.type == "shot" and "scripted:missed_option" in e.labels and e.team == "NBR")
run = next(e for e in ev if e.type == "run" and "scripted:run_not_found" in e.labels)
open_id = [l.split(":")[1] for l in shot.labels if l.startswith("better_option")][0]
BG, LINE, A, D, HL = "#0f1a14", "#3d5a48", "#f2c14e", "#7aa6ff", "#ff5c5c"


def pitch(ax, x0, x1, rotate=False):
    ax.set_facecolor(BG)
    ax.set_xlim(x0, x1)
    ax.set_ylim(0, 68)
    ax.set_aspect("equal")
    ax.axis("off")
    kw = dict(fill=False, ec=LINE, lw=1.2)
    ax.add_patch(Rectangle((0, 0), 105, 68, **kw))
    for bx, sx, gx in ((88.5, 99.5, 105), (0, 0, -1.2)):
        ax.add_patch(Rectangle((bx, 13.84), 16.5, 40.32, **kw))
        ax.add_patch(Rectangle((sx, 24.84), 5.5, 18.32, **kw))
        ax.add_patch(Rectangle((gx, 30.34), 1.2, 7.32, **kw))
    ax.plot([52.5, 52.5], [0, 68], color=LINE, lw=1.2)
    ax.add_patch(Circle((52.5, 34), 9.15, **kw))
    if rotate:
        ax.invert_xaxis()
        ax.invert_yaxis()


def label(ax, x, y, pid):
    ax.annotate(
        pid.split("-")[1], (x, y), color=BG, ha="center", va="center", fontsize=7, fontweight="bold", zorder=5
    )


fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), facecolor=BG)
ax = axes[0]
pitch(ax, 55, 107)
for p in shot.freeze_frame:
    ax.scatter(
        p.x,
        p.y,
        s=170,
        c=A if p.teammate else D,
        ec="white" if p.actor else BG,
        lw=2,
        zorder=3,
        marker="s" if p.keeper else "o",
    )
    label(ax, p.x, p.y, p.player_id)
o = next(p for p in shot.freeze_frame if p.player_id == open_id)
ax.annotate(
    "",
    xy=(shot.end.x, shot.end.y),
    xytext=(shot.start.x, shot.start.y),
    arrowprops=dict(arrowstyle="->", color="white", lw=1.5),
    zorder=2,
)
ax.plot([shot.start.x, o.x], [shot.start.y, o.y], ls="--", color=HL, lw=2, zorder=2)
ax.add_patch(Circle((o.x, o.y), 7, fill=False, ec=HL, ls=":", lw=1.2))
ax.set_title(
    f"Trigger 1 · {shot.match_clock} · shot taken (white) vs square ball (red)",
    color="white",
    fontsize=11,
    loc="left",
)
ax = axes[1]
pitch(ax, -2, 50, rotate=True)
tracks = {}
for f in run.tracking:
    for p in f.players:
        tracks.setdefault(p.player_id, []).append(p)
for pid, tr in tracks.items():
    c = A if tr[0].teammate else D
    ax.plot([p.x for p in tr], [p.y for p in tr], color=c, lw=1.5, alpha=0.6, zorder=2)
    for p in tr[:-1]:
        ax.scatter(p.x, p.y, s=12, c=c, zorder=3)
    last = tr[-1]
    ax.scatter(
        last.x,
        last.y,
        s=170,
        c=c,
        ec="white" if last.actor else BG,
        lw=2,
        zorder=4,
        marker="s" if last.keeper else "o",
    )
    label(ax, last.x, last.y, pid)
f1 = next(f for f in run.tracking if f.t_offset_s == 1.0)
r1 = next(p for p in f1.players if p.actor)
c1 = next(p for p in f1.players if p.teammate and not p.actor)
ax.plot([c1.x, r1.x], [c1.y, r1.y], ls="--", color=HL, lw=2, zorder=2)
ax.set_title(
    f"Trigger 2 · {run.match_clock} · 3 s run in behind, never found", color="white", fontsize=11, loc="left"
)
fig.text(
    0.01,
    0.02,
    "Yellow = attacking team · blue = defenders · square = keeper · red dashed = the pass that was on (trigger 2: at t = 1.0 s)",
    color="#9fb3a7",
    fontsize=9,
)
plt.tight_layout(rect=(0, 0.04, 1, 1))
plt.savefig("docs/images/should-he-have-passed.png", dpi=130, facecolor=BG)
