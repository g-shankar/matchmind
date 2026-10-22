# ADR 0008: A first visit on the shared match clock

Status: Accepted (Oct 2026). Amends [ADR 0006](0006-one-shared-match-clock.md).

## Context

ADR 0006 keeps one match clock per server, shared by every viewer. In the first
round of first-time-user testing that clock was the most reported problem: one
tester loaded the page at full time (2-3, nothing moving), others watched the
score and cards race past at 10x while they were reading, Restart kept the last
viewer's 60x, and a jump on a finished match stayed paused on an empty pitch.

## Decision

We keep one shared clock (the overlay and the studio must agree, and answers "as
of the clock" can never read ahead). Around it:

1. **1x by default.** A fresh or restarted match plays at 1x (about 9 real
   minutes for the 90), slow enough to read each crew card as it lands.
   `MATCHMIND_DEFAULT_SPEED` (1, 10 or 60) changes it for a demo booth.
2. **Restart is a fresh start.** Reset goes back to kick-off, playing, at the
   default speed.
3. **A match nobody is watching rewinds for the next visitor.** When the last
   viewer leaves, the server notes the time. The first viewer to arrive after
   `MATCHMIND_IDLE_REWIND_S` (default 300 s; 0 turns it off) starts at kick-off at
   the default speed. A reload inside that spell keeps the match where it was,
   and nothing moves while anyone else is connected. A live Event Hubs stream is
   never rewound.
4. **A jump always lands somewhere visible.** A jump into a finished match plays
   from the jump point (a jump on a paused, unfinished match keeps the pause).
   `INITIAL_SNAPSHOT.recent_events` carries the last 30 events so the pitch shows
   players and ball at once, playing or paused. The app scrolls back to the
   pitch and shows the moment's own card; a "Should he have passed?" moment opens
   its replay directly.
5. **Full time says so.** A viewer who arrives at full time sees a banner with
   "Watch from kick-off" and "Read the recap", instead of a still pitch.
6. **Modals do not pause the match.** Pausing for one viewer would pause it for
   everyone. Instead each modal (replay, recap, "Show your working") is a fixed
   snapshot of its moment: the match moving behind it never changes what the
   viewer is reading. A per-viewer pause needs a clock per viewer (rejected in
   ADR 0006); we revisit it if the app runs per-viewer sessions.

The rate limits from earlier security reviews stay as they were: `set_view` in
bursts of 3 then 1 a second per connection, one seek or reset every 0.5 s for
everyone, and one pause or speed change every 0.3 s for everyone. The app now
spaces its own requests to fit them (it merges quick audience or language
changes into one `set_view`, sends only the last of several quick jumps, and
keeps pause and speed 350 ms apart, two waiting pause taps undoing each other),
and every refusal it shows is translated from a stable error `code`.

## Alternatives considered

- **A clock per viewer.** Still rejected for this build (cost and overlay
  agreement, ADR 0006).
- **Always start each new connection at kick-off.** Rejected: it would rewind
  the match under everyone already watching.
- **Pause while a modal is open.** Rejected: it pauses every other viewer.

## Consequences

- A judge or fan arriving at an idle server sees kick-off at a readable speed.
- Two visitors at once still share one match: what one does, the other sees.
