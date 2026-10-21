"""Draw a short passage of play: true events against detected ones.

A plain SVG with no dependencies, used for the docs and the demo video. It is
labelled as synthetic tracking on the image itself.
"""

from __future__ import annotations

from html import escape

from matchmind.schema import Event, EventType

from .detect import DetectedEvent
from .score import LABEL
from .tracking import TrackingFeed

SCALE = 8.0  # pixels per metre
PAD = 24.0
HEADER = 64.0
COLOURS = {
    "complete": "#2dd4bf",
    "incomplete": "#fb923c",
    "out": "#fb923c",
    "shot": "#f43f5e",
    "clearance": "#a78bfa",
}
TEAM_COLOURS = ("#60a5fa", "#fbbf24")


def _p(x: float, y: float) -> tuple[float, float]:
    return (PAD + x * SCALE, HEADER + PAD + (68 - y) * SCALE)


def _line(a, b, colour: str, width: float, dash: str = "", marker: str = "") -> str:
    (x1, y1), (x2, y2) = _p(*a), _p(*b)
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    extra += f' marker-end="url(#{marker})"' if marker else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{colour}"'
        f' stroke-width="{width}" stroke-linecap="round"{extra}/>'
    )


def _pitch() -> list[str]:
    w, h = 105 * SCALE, 68 * SCALE
    x0, y0 = _p(0, 68)
    cx, cy = _p(52.5, 34)
    out = [
        f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#14532d"'
        ' stroke="#e5e7eb" stroke-width="2"/>',
        _line((52.5, 0), (52.5, 68), "#e5e7eb", 2),
        f'<circle cx="{cx}" cy="{cy}" r="{9.15 * SCALE}" fill="none" stroke="#e5e7eb" stroke-width="2"/>',
    ]
    for gx, sign in ((0, 1), (105, -1)):
        bx, by = _p(gx if sign > 0 else gx - 16.5, 34 + 20.16)
        out.append(
            f'<rect x="{bx}" y="{by}" width="{16.5 * SCALE}" height="{40.32 * SCALE}" fill="none"'
            ' stroke="#e5e7eb" stroke-width="2"/>'
        )
        out.append(_line((gx, 34 - 3.66), (gx, 34 + 3.66), "#ffffff", 6))
    return out


def render_svg(
    feed: TrackingFeed,
    truth: list[Event],
    found: list[DetectedEvent],
    *,
    period: int,
    start_s: float,
    end_s: float,
    title: str,
    subtitle: str,
) -> str:
    width, height = 105 * SCALE + 2 * PAD, 68 * SCALE + 2 * PAD + HEADER + 40
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}"'
        f' viewBox="0 0 {width:.0f} {height:.0f}" font-family="Inter, Segoe UI, sans-serif">',
        "<defs>",
    ]
    for name, colour in COLOURS.items():
        parts.append(
            f'<marker id="{name}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5"'
            f' orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{colour}"/></marker>'
        )
    parts.append("</defs>")
    parts.append('<rect width="100%" height="100%" fill="#0b1120"/>')
    parts.append(
        f'<text x="{PAD}" y="30" fill="#f8fafc" font-size="20" font-weight="700">{escape(title)}</text>'
    )
    parts.append(f'<text x="{PAD}" y="54" fill="#94a3b8" font-size="14">{escape(subtitle)}</text>')
    badge_w = 7.0 * len(LABEL) + 20
    parts.append(
        f'<rect x="{width - PAD - badge_w:.0f}" y="14" width="{badge_w:.0f}" height="24" rx="12"'
        ' fill="none" stroke="#fbbf24"/>'
    )
    parts.append(
        f'<text x="{width - PAD - badge_w / 2:.0f}" y="31" fill="#fbbf24" font-size="13"'
        ' text-anchor="middle">'
        f"{escape(LABEL)}</text>"
    )
    parts.extend(_pitch())

    frames = [f for f in feed.frames if f.period == period and start_s <= f.clock_s <= end_s]
    trail = [f.ball for f in frames if f.ball is not None and f.alive]
    if len(trail) > 1:
        pts = " ".join(f"{_p(*b)[0]:.1f},{_p(*b)[1]:.1f}" for b in trail[::2])
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="#f8fafc" stroke-opacity="0.35" stroke-width="2"/>'
        )

    for e in truth:
        if (
            e.period == period
            and start_s <= e.clock_s <= end_s
            and e.type in (EventType.PASS, EventType.SHOT)
            and e.start
            and e.end
        ):
            parts.append(_line((e.start.x, e.start.y), (e.end.x, e.end.y), "#f8fafc", 1.5, dash="5 5"))
    for d in found:
        if d.period == period and start_s <= d.clock_s <= end_s:
            key = d.outcome if d.kind == "pass" else d.kind
            parts.append(_line(d.start, d.end, COLOURS.get(key, "#2dd4bf"), 3.5, marker=key))
            mx, my = _p((d.start[0] + d.end[0]) / 2, (d.start[1] + d.end[1]) / 2)
            parts.append(
                f'<text x="{mx:.1f}" y="{my - 8:.1f}" fill="#f8fafc" font-size="12" text-anchor="middle">'
                f"{d.ball_speed_mps * 3.6:.0f} km/h</text>"
            )

    if frames:
        last = frames[-1]
        teams = sorted(set(feed.player_teams))
        for n, team in enumerate(feed.player_teams):
            p = last.player(n)
            if p is None:
                continue
            x, y = _p(*p)
            colour = TEAM_COLOURS[teams.index(team) % 2]
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{colour}" stroke="#0b1120" stroke-width="2"/>'
            )
        if last.ball is not None:
            x, y = _p(*last.ball)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#ffffff"/>')

    ly = height - 18
    legend = [
        ("#f8fafc", "true event (simulator), dashed"),
        (COLOURS["complete"], "detected pass"),
        (COLOURS["incomplete"], "detected pass, lost"),
        (COLOURS["shot"], "detected shot"),
    ]
    x = PAD
    for colour, text in legend:
        parts.append(f'<rect x="{x}" y="{ly - 10}" width="14" height="4" fill="{colour}"/>')
        parts.append(f'<text x="{x + 20}" y="{ly - 4}" fill="#cbd5e1" font-size="13">{escape(text)}</text>')
        x += 36 + 6.6 * len(text)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
