# Personalisation: one match, many viewers

Every PitchPulse viewer has a profile (`ViewerProfile`, one per connection,
never shared). The **facts never change**: every number on every card comes
from the stats engine, and the fact-checker refuses any text with a number
that is not one of the moment's facts. What changes is **what is shown**
(selection), **how high it ranks** (priority and slot), **how it is told**
(framing, vocabulary, depth) and **in which language**.

## The attribute vector

| Attribute | Values | Selection | Priority | Framing and depth |
|---|---|---|---|---|
| `persona` | `casual` (Fan), `tactical` (Analyst), `fantasy` (Stats scout), `player_spotlight` (Player cam) | Each audience has its own moment kinds (`PERSONA_KINDS` in `crew/producer.py`); moments at priority 80+ reach every audience except Stats scout | - | Fan: plain words, no stat acronyms. Analyst: chalkboard terms and numbers (PDR, xT, field tilt). Stats scout: only stats PitchPulse computes itself (goals, assists, shots, key passes, xG, xA); no game points, bonuses or real-league fantasy branding. Player cam: told around the focus player |
| `language` | 5 studio languages (hand-written packs) + 8 world languages (Azure AI Translator, off by default) | - | - | Studio packs carry their own football glossary and register ([LANGUAGES.md](LANGUAGES.md)); Arabic is right-to-left |
| `favourite_team` | a club in this match, or none | **Club heart**: rival minor moments dropped (table below) | Own club +15; rival momentum and pressure -10 | Club heart frames: let-off, next step after a goal conceded, constructive "should he have passed", comeback, full-time result from the fan's side; the fan's club prints as "your team" |
| `focus_player_id` | a player in this match, or none | That player's moments are always kept, even a rival's minor moments | +20 | Player cam voice for that player's moments |
| `focus_metric` | `pressure`, `xg`, `pass_difficulty`, `top_speed`, `momentum`, or none | Adds `metric_alert` cards when the metric moves meaningfully; with a favourite club, they follow that club | - | A momentum move towards the rival is worded as a warning |

Precedence in the producer (`wanted` in `crew/producer.py`): focus player
first (always kept), then metric alerts (always kept), then club heart (may
drop), then the persona filter. The API only accepts a favourite club and a
focus player that are in the match.

## Club heart

The policy is one table in code, `POLICY` in
`backend/src/matchmind/crew/club_heart.py`; the tables below are generated
from it (`policy_markdown()`) and a test fails if they drift. "Shown" means
the club-heart rule keeps it; the persona filter still applies after it.

| Moment | Own club: shown | priority | framing | Rival: shown | priority | framing | Why |
|---|---|---|---|---|---|---|---|
| `goal` | shown | +15 | `goal_for` | shown | 0 | `goal_against` | Own goals celebrated, with level / pull-back / lead variants; goals conceded get a next step (the score and the clock), or a late-blow line from 85:00 on. |
| `card` | shown | +15 | `card_own` | shown | 0 | `card_rival` | An own booking asks for discipline; a rival booking is a chance to press the advantage. |
| `big_chance` | shown | +15 | kind's own wording | shown | 0 | `let_off` | A rival big chance is shown as danger survived, never celebrated. |
| `rocket_shot` | shown | +15 | kind's own wording | shown | 0 | `let_off_shot` | A rival rocket that did not go in is a let-off (a rocket that scored is voiced as the goal). |
| `better_option` | shown | +15 | `lesson_choice` | shown | 0 | `let_off_choice` | Own 'should he have passed' is framed constructively; the rival's is a let-off. |
| `unfound_run` | shown | +15 | `lesson_run` | shown | 0 | `let_off_run` | Own unfound run: the run deserved the ball. Rival unfound run: a let-off for the back line. |
| `momentum_swing` | shown | +15 | kind's own wording | shown | -10 | `momentum_against` | A swing towards the rival is a warning and ranks a little lower than the fan's own moments. |
| `pressure_spell` | shown | +15 | `pressure_for` | shown | -10 | `hold_firm` | Own pressure: turn the screw. Rival pressure: hold firm. |
| `speed_burst` | shown | +15 | kind's own wording | dropped | - | - | Rival speed tags are dropped. |
| `distance_milestone` | shown | +15 | kind's own wording | dropped | - | - | Rival distance tags are dropped. |
| `hard_pass` | shown | +15 | kind's own wording | dropped | - | - | Rival hard-pass tags are dropped. |
| `milestone` | shown | +15 | kind's own wording | dropped | - | - | Rival player milestones are dropped. |
| `correction` | shown | +15 | kind's own wording | shown | 0 | kind's own wording | A VAR decision is always shown, in its own neutral wording: the score must be right for every fan. |

| Framing variant | When |
|---|---|
| `goal_for` | Own club scores and was already ahead |
| `goal_for_level` | Own club scores to level the match |
| `goal_for_pull_back` | Own club scores and is still behind |
| `goal_for_lead` | Own club scores from level to lead |
| `goal_against` | Rival scores and the own club is behind |
| `goal_against_level` | Rival scores to level the match |
| `goal_against_lead_cut` | Rival scores and the own club still leads |
| `goal_against_late` | Rival scores from 85:00 on and the own club is behind |
| `full_time_won` | Full time, own club won |
| `full_time_lost` | Full time, own club lost |
| `full_time_drawn` | Full time, a draw |

| Focus metric | Whose numbers | Own wording | Rival wording | Why |
|---|---|---|---|---|
| `pressure` | own club only | `pressure` | - | Only the fan's club's pressure index. |
| `xg` | own club only | `xg` | - | Only the fan's club's xG (or the focus player's). |
| `pass_difficulty` | own club only | `pass_difficulty` | - | Only the fan's club's hard passes. |
| `top_speed` | own club only | `top_speed` | - | Only the fan's club's top speed. |
| `momentum` | both clubs | `momentum` | `momentum_against` | Momentum is one number: a move towards the rival is shown as a warning. |

Moments with no club (kick-off, half-time, full-time) are never dropped or
re-ranked. Framing only changes words: every framed template is filled from
the same facts and passes the same fact-checker and length rules
(`backend/tests/test_club_heart.py` runs the whole demo match for every
persona, language and club). Player cam keeps its player-centred wording for
its focus player's moments; it still gets club-heart selection and priority.
With paid AI switched on (off by default), the commentator model is told the
frame (`fan_framing`) and its answer is fact-checked like any other; the
template above is the fallback.

What club heart does not do (honestly): it does not invent game-state facts.
"Time to respond" uses the clock and the score already in the goal's facts;
there is no time-left or win-probability number, because the stats engine
does not compute one. Pressure spells are framed by side, not by the score.

## Worked example: the unfound run at 61:15 (demo match MM-DEMO-001)

Harbour City's Ivan Petrov is 6.7 m clear of the Northbridge FC back line and
Elias Varga never plays the pass. The moment's facts (shared by every viewer):
`clear_of_line_m: 6.7`, `projected_xg: 0.48`, `projected_xg_pct: 48`,
`pass_on_clock: "61:15"`, `one_on_one: true`, priority 80.

| Viewer | Shown | Priority | Headline | Body |
|---|---|---|---|---|
| Neutral, Fan, English | yes, side panel | 80 | Petrov's run went unseen | Ivan Petrov broke clear behind the defence, but Varga never played the pass. It could have been a 48% chance. |
| Northbridge FC fan, Fan, English | yes, side panel (`favourite_side: false`) | 80 | Let-off: Petrov's run went unseen | Ivan Petrov got in behind your team's back line, but Varga never played the pass. It could have been a 48% chance. |
| Harbour City fan, Analyst, Español | yes, side panel (`favourite_side: true`) | 95 | Desmarque sin premio: Petrov, 6,7 m | El pase al hueco estaba en el 61:15: una ocasión de 0,48 xG. La próxima vez Varga puede encontrarlo. |

The evidence panel is identical for all three (6.7 m, 0.48 xG, 61:15,
one-on-one), with labels in the card's language.

Across the whole demo match the three viewers get measurably different card
sets: the Northbridge FC fan never sees Harbour City's speed and distance tags
or Varga's 100th-appearance card, reads Harbour City's goals as "Varga cuts
your team's lead", "Pegged back: Petrov levels it" and "Late blow: Clarke
scores", and ends on "Full-time: defeat for your team"; the Harbour City fan
reads the same goals as "Varga pulls a goal back!", "Level! Petrov brings your
team back" and "GOAL! Clarke puts your team in front", and ends on "Full-time: your
team win!". Every number on every one of those cards is a neutral fact
(`test_three_viewers_get_different_cards_with_identical_numbers`).

## Where it lives

| Piece | File |
|---|---|
| Club-heart policy table, frame choice, doc generator | `backend/src/matchmind/crew/club_heart.py` |
| Selection and priority | `crew/producer.py` (`wanted`, `card_priority`) |
| Framed templates | `crew/i18n/<lang>.py`, `PACK["heart"]`; chosen in `crew/commentator.py` |
| Metric alerts that follow the club | `crew/alerts.py`, `club_heart.METRIC_POLICY` |
| Glossary | `crew/i18n/<lang>.py`, `PACK["glossary"]`; registry in `crew/i18n/__init__.py` |
| Tests | `backend/tests/test_club_heart.py` |

Known limit: the offline browser demo (`frontend/src/api/mockServer.ts`) has
its own simple producer and does not apply club heart yet; the live backend
does.
