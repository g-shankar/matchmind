# PitchPulse graphics in OBS Studio and vMix

PitchPulse's overlay can sit on top of a programme feed in OBS Studio or vMix
as a Browser Source / Web Browser input. Capture mode draws only the graphics
(scorebug, lower thirds, side cards, ticker, full-screen cards, VAR
corrections) on a transparent page.

## The overlay URL

```
<app origin>/?capture=1&persona=casual&lang=en#overlay
```

| Part | Meaning |
|---|---|
| `<app origin>` | Where the app is served: the backend's own address when it serves the built frontend (`MATCHMIND_STATIC_DIR`), or the dev server `http://localhost:3000` |
| `#overlay` | The overlay view (the real route; views are chosen by the hash) |
| `capture=1` | Graphics only: no app header, no producer panel, no pitch backdrop, transparent background, fills the whole source |
| `persona` | `casual`, `tactical` or `fantasy`. Optional |
| `lang` | Any language from `/api/languages`, e.g. `en`, `es`, `ar`. Optional |
| `club` | A club id from the match (e.g. `NBR`) to favour its moments. Optional |
| `demo=1` | Optional: play the recorded offline demo, no backend needed |
| `t=2340&p=1&pause=1` | Optional: start at a match time (seconds, period) and hold there |

The source has its own browser storage, so set `persona` and `lang` in the URL
rather than relying on choices made in another browser. Unknown values are
ignored. Playback (play, pause, speed, seek) is shared: control it from the
studio view in a normal browser.

If the backend's `MATCHMIND_ALLOWED_ORIGINS` does not include the app origin
the live connection is refused; served from the backend itself, set
`MATCHMIND_PUBLIC_ORIGIN` instead (see API-CONTRACT.md, Server settings).

## OBS Studio

1. **Sources > + > Browser**, name it "PitchPulse graphics".
2. **URL**: the overlay URL above. Untick **Local file**.
3. **Width 1920, Height 1080**. The graphics are laid out for 16:9 and scale
   with the source.
4. **Custom CSS**: keep OBS's default
   `body { background-color: rgba(0, 0, 0, 0); margin: 0px auto; overflow: hidden; }`.
   Capture mode is already transparent; this keeps it so.
5. Tick **Shutdown source when not visible** only if you want the overlay to
   reconnect each time the scene is shown (it always comes back with the
   current score and what is on air).
6. Tick **Refresh browser when scene becomes active** if the operator switches
   persona or language by changing the URL between scenes.
7. Put the source above the programme video in the scene, Transform >
   **Fit to screen** (Ctrl+F).
8. After changing the URL, or after updating PitchPulse, press **Refresh cache
   of current page** in the source properties so OBS does not keep an old copy.

Right-click > **Interact** opens the page for clicks, but there is nothing to
click in capture mode; use the studio view to drive playback.

## vMix

1. **Add Input > Web Browser**.
2. **URL**: the overlay URL above.
3. **Width 1920, Height 1080**, frame rate 30 (or the production frame rate).
4. vMix web inputs keep transparency; place the input on an **Overlay** channel
   (e.g. Overlay 1) above the programme, or use it as a layer in a Virtual Set.
5. To reload after a URL change or an update, use the web browser input's
   **Refresh** option, so vMix does not keep showing a cached copy.

## Driving your own graphics from the cue sheet

Graphics systems that render their own templates (vMix GT titles, CasparCG,
a custom HTML package) can read the cue sheet instead of the PitchPulse overlay:

- **Polling (simplest):** `GET /api/match/cue-sheet?persona=casual&lang=en&since_seq=N`
  every second or two. Start with `since_seq=0`, page while `has_more` is true,
  and keep the last `next_since_seq`. Responses are `Cache-Control: no-store`;
  the route is rate-limited to about 3 requests a second per address (bursts
  of 30).
- **Push:** connect to the WebSocket `/ws/match`, read `INITIAL_SNAPSHOT.cue_sheet.active`
  for what is on air now, then apply each `CUES` message.
- Apply cues by the rules in [CUE-SHEET.md](CUE-SHEET.md): by `seq`, each
  `cue_id` once, honour `retract`, `supersede` and `clear`, and never show a
  cue whose moment a VAR retract ruled out. Map `layer` to your template
  (`scorebug` to your score bug, `lower_third` to a lower-third title, and so
  on) and fill it from `text`, `scorebug`, `ribbon` or `telestration`.
- Schedule on `start.t_s` / `end.t_s` (always increasing), show `match_clock`.
- For vMix GT titles, a small script or Data Source can turn the newest
  on-air cue per layer into title fields, e.g. `headline`, `body`,
  `score_home`, `score_away`.

## Checks before going on air

- At 1920x1080 the scorebug sits top left and cards stay inside the safe area.
- Arabic (`lang=ar`) renders right to left with Western digits.
- Jump the match past 40:22 in the studio view: the 39:11 goal never appears,
  the scorebug reads 1-0, and the "Ruled out by VAR" card shows when played
  through live.
- The page is transparent: nothing but graphics over the programme.
