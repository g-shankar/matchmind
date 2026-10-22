"""English studio phrases. Placeholders name keys of `Moment.facts` (or the
derived words added by the commentator); `{n|one|many}` picks a plural form.
A list holds alternatives: the first one whose placeholders are all
available is used."""

PACK = {
    "your_team": "your team",
    "labels": {
        "xg": "Chance quality (xG)",
        "distance_m": "Distance to goal",
        "shot_speed_kmh": "Shot speed",
        "score_home": "Home score",
        "score_away": "Away score",
        "card": "Card",
        "shot_xg": "Shot xG",
        "alt_xg": "Teammate chance xG",
        "pass_success_pct": "Pass success chance",
        "alt_value": "Pass expected value",
        "times_better": "Pass vs shot",
        "pass_distance_m": "Pass distance",
        "nearest_marker_m": "Nearest marker",
        "clear_of_line_m": "Clear of the back line",
        "projected_xg": "Projected chance xG",
        "pass_on_clock": "Pass was on at",
        "one_on_one": "One-on-one",
        "momentum_change": "Momentum change",
        "window_min": "Window",
        "team_field_tilt_pct": "Field tilt",
        "team_shots_5": "Shots (last 5 min)",
        "team_xg_total": "Team xG",
        "pressure_index": "Pressure index",
        "spell_min": "Spell length",
        "team_box_entries_5": "Box entries (last 5 min)",
        "speed_kmh": "Speed",
        "top_speed_kmh": "Top speed",
        "sprints": "Sprints",
        "milestone_km": "Distance (estimated)",
        "pass_difficulty": "Pass difficulty",
        "xt_delta": "Threat added (xT)",
        "xg_home": "Home xG",
        "xg_away": "Away xG",
        "shots_home": "Home shots",
        "shots_away": "Away shots",
        "appearance_n": "Club appearances",
        "ruled_out_clock": "Goal ruled out (scored at)",
        "xt_stopped": "Threat stopped (xT)",
        "own_goal_distance_m": "Distance from own goal",
        "p_tackles_won": "Tackles won",
        "last_ditch": "Last-ditch (own box)",
        "distance_km": "Distance so far (tracking est.)",
        "sprint_m": "Sprint length",
    },
    "zones": {
        "Penalty Box": "penalty box",
        "Attacking Third": "attacking third",
        "Middle Third": "middle third",
        "Defensive Third": "defensive third",
        "": "open play",
    },
    "outcomes": {
        "saved": "the keeper saved it",
        "blocked": "a defender blocked it",
        "off_target": "it went off target",
        "goal": "it flew in",
        "": "nothing came of it",
    },
    "card_name": {"yellow": "yellow card", "red": "red card"},
    "card_name_cap": {"yellow": "Yellow card", "red": "Red card"},
    "card_action": {"yellow": "is booked", "red": "is sent off"},
    "var_reason": {"offside": "offside", "handball": "handball", "foul": "a foul"},
    "fav_goal": {
        "for": "GOAL for your team! {player_short} scores",
        "against": "{player_short} scores against your team",
    },
    "narr": {
        "goal": {
            "casual": [
                (
                    "GOAL! {player_short} scores for {team}",
                    "{player} finishes it, set up by {assist}. It's {home} {score_home}-{score_away} {away}.",
                ),
                (
                    "GOAL! {player_short} scores for {team}",
                    "{player} finishes it off. It's {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "tactical": [
                (
                    "{player_short} converts a {xg} xG chance",
                    "{assist_short} finds {player_short} {distance_m} m out in the {zone}. "
                    "{home} {score_home}-{score_away} {away}.",
                ),
                (
                    "{player_short} converts a {xg} xG chance",
                    "{player_short} finishes from {distance_m} m in the {zone}. {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "fantasy": [
                (
                    "Goal {player_short}, assist {assist_short}",
                    "{player_short} today: {p_goals|goal|goals} and {p_xg} xG from {p_shots|shot|shots}. "
                    "This chance was worth {xg} xG.",
                ),
                (
                    "Goal for {player_short}",
                    "{player_short} today: {p_goals|goal|goals} and {p_xg} xG from {p_shots|shot|shots}. "
                    "This chance was worth {xg} xG.",
                ),
            ],
            "player_spotlight": [
                (
                    "{player_short} scores!",
                    "{player} beats the keeper from {distance_m} m. It's {home} {score_home}-{score_away} {away}.",
                ),
            ],
        },
        "card": {
            "casual": [
                (
                    "{card_name_cap} for {player_short}",
                    "{player} {card_action}. {team} have to be careful now.",
                )
            ],
            "tactical": [
                (
                    "{card_name_cap}: {player_short}",
                    "{player} {card_action}. Expect {team} to defend that channel more cautiously.",
                )
            ],
            "fantasy": [
                (
                    "{card_name_cap} for {player_short}",
                    "{player_short} {card_action}. Today: {p_goals|goal|goals}, {p_assists|assist|assists}, {p_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{card_name_cap} for {player_short}",
                    "{player} {card_action}. Every duel from here is a risk.",
                )
            ],
        },
        "big_chance": {
            "casual": [
                (
                    "Big chance for {player_short}!",
                    "{player} got a clear sight of goal {distance_m} m out, but {outcome_phrase}. "
                    "Chances like that go in about {xg_pct}% of the time.",
                )
            ],
            "tactical": [
                (
                    "{xg} xG chance for {team}",
                    "{player_short} shoots from {distance_m} m in the {zone}, but {outcome_phrase}. Shot value: {xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{player_short}: {xg} xG chance",
                    "{player_short} now has {p_xg} xG from {p_shots|shot|shots}. This one did not go in.",
                )
            ],
            "player_spotlight": [
                (
                    "Big chance for {player_short}",
                    "{player_short} finds space {distance_m} m out, but {outcome_phrase}. "
                    "Today: {p_shots|shot|shots}, {p_xg} xG.",
                )
            ],
        },
        "better_option": {
            "casual": [
                (
                    "Should {player_short} have passed?",
                    "{player_short} went for goal, but {teammate_short} was free. "
                    "The pass was worth {times_better}x more than the shot.",
                )
            ],
            "tactical": [
                (
                    "Shot selection: {player_short} ignored {teammate_short}",
                    "Shot at {shot_xg} xG; the {pass_distance_m} m pass had {pass_success_pct}% success odds "
                    "and a {alt_xg} xG chance behind it. Expected value {alt_value}, {times_better}x the shot.",
                )
            ],
            "fantasy": [
                (
                    "Missed assist chance for {player_short}",
                    "Passing to {teammate_short} was worth {alt_value} expected goals against {shot_xg} xG "
                    "for the shot. {player_short} today: {p_xg} xG from {p_shots|shot|shots}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} chose the shot",
                    "{teammate_short} was open {pass_distance_m} m away with no one within {nearest_marker_m} m. "
                    "The pass rated {times_better}x better than the shot.",
                )
            ],
        },
        "unfound_run": {
            "casual": [
                (
                    "{runner_short}'s run went unseen",
                    "{runner} broke clear behind the defence, but {player_short} never played the pass. "
                    "It could have been a {projected_xg_pct}% chance.",
                )
            ],
            "tactical": [
                (
                    "Unfound run: {runner_short} beyond the line",
                    "{runner_short} got {clear_of_line_m} m beyond the back line and the through ball was on "
                    "at {pass_on_clock}. Projected chance: {projected_xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{runner_short} denied a {projected_xg} xG chance",
                    "The through ball from {player_short} never came. That run was worth {projected_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{runner_short} runs in behind",
                    "{runner_short} got {clear_of_line_m} m clear of the defence, but {player_short} kept the ball.",
                )
            ],
        },
        "momentum_swing": {
            "casual": [
                (
                    "{team} take control",
                    "The game has swung towards {team}: momentum moved {momentum_change} points "
                    "in {window_min} minutes.",
                )
            ],
            "tactical": [
                (
                    "Momentum shift to {team}",
                    "Momentum moved {momentum_change} points in {window_min} minutes. "
                    "{team} now have {team_field_tilt_pct}% field tilt.",
                )
            ],
            "fantasy": [
                (
                    "{team} on top: watch their attackers",
                    "{team} have {team_shots_5|shot|shots} in the last {window_min} minutes. "
                    "Their match xG is now {team_xg_total}.",
                )
            ],
        },
        "pressure_spell": {
            "casual": [
                (
                    "{team} piling on the pressure",
                    "{team} have kept {opp} pinned back for {spell_min} minutes. Something may have to give.",
                )
            ],
            "tactical": [
                (
                    "Sustained press: {team} at {pressure_index}",
                    "Pressure index {pressure_index} for {spell_min} minutes with {team_field_tilt_pct}% field tilt. "
                    "{opp} cannot build calmly.",
                )
            ],
            "fantasy": [
                (
                    "{team} pressing high",
                    "{team} have {team_shots_5|shot|shots} in the last {window_min} minutes "
                    "and {team_xg_total} xG in the match. Their attackers are getting looks.",
                )
            ],
        },
        "speed_burst": {
            "casual": [
                (
                    "{player_short} hits {speed_kmh} km/h",
                    "{player} finds top gear at {speed_kmh} km/h. That is {sprints|sprint|sprints} so far.",
                )
            ],
            "tactical": [
                (
                    "Sprint: {player_short} at {speed_kmh} km/h",
                    "{player_short} goes past the {speed_threshold_kmh} km/h sprint line. Sprints today: {sprints}.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} on the move",
                    "{player_short} so far: {p_shots|shot|shots}, {p_xg} xG and {p_key_passes|key pass|key passes}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} at full speed",
                    "{speed_kmh} km/h, and the top speed today is {top_speed_kmh} km/h. Sprints so far: {sprints}.",
                )
            ],
        },
        "rocket_shot": {
            "casual": [
                (
                    "Rocket from {player_short}!",
                    "{player} hits it at {shot_speed_kmh} km/h, and {outcome_phrase}.",
                )
            ],
            "tactical": [
                (
                    "{shot_speed_kmh} km/h strike by {player_short}",
                    "Ball speed {shot_speed_kmh} km/h from {distance_m} m on a {xg} xG chance. "
                    "Pace like that cuts the keeper's reaction time.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} shot: {xg} xG",
                    "{player_short} now has {p_xg} xG from {p_shots|shot|shots}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} lets fly",
                    "{shot_speed_kmh} km/h from {distance_m} m, and {outcome_phrase}.",
                )
            ],
        },
        "distance_milestone": {
            "casual": [
                (
                    "{player_short} passes {milestone_km} km (est.)",
                    "{player} has covered an estimated {milestone_km} km. The engine keeps running.",
                )
            ],
            "tactical": [
                (
                    "Work rate: {player_short}, {milestone_km} km (est.)",
                    "{player_short} passes an estimated {milestone_km} km with {sprints|sprint|sprints}. "
                    "Top speed {top_speed_kmh} km/h.",
                )
            ],
            "fantasy": [
                (
                    "{player_short}: about {milestone_km} km covered",
                    "Plenty of running (distance estimated); the attacking line reads {p_shots|shot|shots}, {p_xg} xG "
                    "and {p_key_passes|key pass|key passes}.",
                )
            ],
            "player_spotlight": [
                (
                    "{milestone_km} km (est.) for {player_short}",
                    "{player_short} reaches an estimated {milestone_km} km, with {sprints|sprint|sprints} "
                    "and a top speed of {top_speed_kmh} km/h.",
                )
            ],
        },
        "hard_pass": {
            "casual": [
                (
                    "What a pass from {player_short}!",
                    "{player} picks out {receiver_short} with a {pass_distance_m} m pass. "
                    "It rated {pass_difficulty} out of {difficulty_scale} for difficulty.",
                )
            ],
            "tactical": [
                (
                    "PDR {pass_difficulty}: {player_short} finds {receiver_short}",
                    "A {pass_distance_m} m pass rated {pass_difficulty} for difficulty, adding {xt_delta} xT.",
                ),
                (
                    "PDR {pass_difficulty}: {player_short} finds {receiver_short}",
                    "A {pass_distance_m} m pass rated {pass_difficulty} for difficulty, played through the lines.",
                ),
            ],
            "fantasy": [
                (
                    "{player_short} creating chances",
                    "{player_short} today: {p_key_passes|key pass|key passes} and {p_xa} xA.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} threads it through",
                    "A {pass_distance_m} m pass to {receiver_short}, difficulty {pass_difficulty} "
                    "out of {difficulty_scale}.",
                )
            ],
        },
        "key_tackle": {
            "casual": [
                (
                    "Big tackle by {player_short}",
                    "{player} takes the ball off {victim_short} {own_goal_distance_m} m from his own goal. "
                    "Danger over for {team}.",
                ),
                (
                    "Big tackle by {player_short}",
                    "{player} wins the ball {own_goal_distance_m} m from his own goal. Danger over for {team}.",
                ),
            ],
            "tactical": [
                (
                    "Key tackle: {player_short}",
                    "Won in the defensive third, {own_goal_distance_m} m out, where {opp} carried {xt_stopped} xT. "
                    "{player_short} has {p_tackles_won|tackle won|tackles won} today.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} stops the attack",
                    "Defensive work from {player_short}: {p_tackles_won|tackle won|tackles won} so far. "
                    "This one came {own_goal_distance_m} m from his own goal.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} wins it back",
                    "A tackle {own_goal_distance_m} m from his own goal takes away a {xt_stopped} xT threat. "
                    "Tackles won today: {p_tackles_won}.",
                )
            ],
        },
        "correction": {
            "casual": [
                (
                    "No goal! VAR rules out {player_short}",
                    "{player}'s goal at {ruled_out_clock} is ruled out for {reason_phrase} after a VAR review. It stays {home} {score_home}-{score_away} {away}.",
                )
            ],
            "tactical": [
                (
                    "VAR: {player_short} goal ruled out",
                    "Overturned for {reason_phrase} on review. The score goes back to {home} {score_home}-{score_away} {away}.",
                )
            ],
            "fantasy": [
                (
                    "Goal ruled out: {player_short}",
                    "VAR takes the goal off for {reason_phrase}; the shot still counts. {player_short} today: {p_goals|goal|goals} and {p_xg} xG from {p_shots|shot|shots}.",
                )
            ],
            "player_spotlight": [
                (
                    "No goal! VAR rules out {player_short}",
                    "{player}'s goal at {ruled_out_clock} is ruled out for {reason_phrase} after a VAR review. It stays {home} {score_home}-{score_away} {away}.",
                )
            ],
        },
        "milestone.kick_off": {
            "casual": [
                (
                    "Kick-off: {home} v {away}",
                    "{home} against {away} is under way. We will flag the moments that matter.",
                )
            ],
            "tactical": [
                (
                    "Kick-off: {home} v {away}",
                    "{home} against {away} is under way. Watch the pressure and momentum lines from the first whistle.",
                )
            ],
            "fantasy": [
                (
                    "Kick-off: {home} v {away}",
                    "{home} against {away} is under way. Goals, assists, xG, xA, shots and key passes tracked live.",
                )
            ],
        },
        "milestone.half_time": {
            "casual": [
                (
                    "Half-time: {home} {score_home}-{score_away} {away}",
                    "That is the break. Shots so far: {shots_home} for {home}, {shots_away} for {away}.",
                )
            ],
            "tactical": [
                (
                    "Half-time: {home} {score_home}-{score_away} {away}",
                    "Expected goals {xg_home} to {xg_away}, shots {shots_home} to {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "Half-time: {home} {score_home}-{score_away} {away}",
                    "xG at the break: {home} {xg_home}, {away} {xg_away}.",
                )
            ],
        },
        "milestone.full_time": {
            "casual": [
                (
                    "Full-time: {home} {score_home}-{score_away} {away}",
                    "It is all over. {home} had {shots_home|shot|shots} and {away} had {shots_away|shot|shots}.",
                )
            ],
            "tactical": [
                (
                    "Full-time: {home} {score_home}-{score_away} {away}",
                    "Final expected goals {xg_home} to {xg_away}, shots {shots_home} to {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "Full-time: {home} {score_home}-{score_away} {away}",
                    "Final xG: {home} {xg_home}, {away} {xg_away}. Shots: {shots_home} to {shots_away}.",
                )
            ],
        },
        "milestone.player": {
            "casual": [
                (
                    "{appearance_nth} club appearance for {player_short}",
                    "{player} reaches {appearance_n} appearances for {team} today.",
                ),
                ("A milestone for {player_short}", "{player} marks a milestone with {team} today."),
            ],
            "tactical": [
                (
                    "{player_short}: {appearance_nth} club appearance",
                    "{player} reaches {appearance_n} appearances for {team}.",
                ),
                ("A milestone for {player_short}", "{player} marks a milestone with {team} today."),
            ],
            "fantasy": [
                (
                    "{player_short}: {appearance_nth} club appearance",
                    "{player_short} today: {p_goals|goal|goals}, {p_assists|assist|assists}, {p_xg} xG.",
                ),
                (
                    "A milestone for {player_short}",
                    "{player_short} today: {p_goals|goal|goals}, {p_assists|assist|assists}, {p_xg} xG.",
                ),
            ],
        },
    },
    "why": {
        "goal": ["The score is now {home} {score_home}-{score_away} {away}, from a {xg} xG chance."],
        "card": ["{player_short} {card_action}, so {team} have to adjust how they defend."],
        "big_chance": ["A {xg} xG chance is a clear opening: {team} are getting into dangerous areas."],
        "better_option": [
            "The pass to {teammate_short} was worth {alt_value} expected goals against {shot_xg} for the shot, "
            "{times_better}x more."
        ],
        "unfound_run": [
            "{runner_short} was {clear_of_line_m} m beyond the back line at {pass_on_clock}; "
            "the pass would have made a {projected_xg} xG chance."
        ],
        "momentum_swing": [
            "Momentum moved {momentum_change} points in {window_min} minutes: control has changed hands."
        ],
        "pressure_spell": [
            "A pressure index of {pressure_index} for {spell_min} minutes stops {opp} building calmly."
        ],
        "speed_burst": [
            "{speed_kmh} km/h is over the {speed_threshold_kmh} km/h sprint line; pace stretches a defence."
        ],
        "rocket_shot": ["At {shot_speed_kmh} km/h the keeper has very little time to react."],
        "distance_milestone": [
            "An estimated {milestone_km} km covered shows the work behind {team}'s shape."
        ],
        "hard_pass": [
            "A difficulty rating of {pass_difficulty} out of {difficulty_scale} is a pass few players complete."
        ],
        "key_tackle": [
            "Won {own_goal_distance_m} m from goal, the tackle took away a {xt_stopped} xT threat from {opp}."
        ],
        "correction": [
            "VAR ruled out the goal from {ruled_out_clock} for {reason_phrase}: the score goes back to {home} {score_home}-{score_away} {away}."
        ],
        "milestone.kick_off": ["The match is under way."],
        "milestone.half_time": ["At the break expected goals read {xg_home} to {xg_away}."],
        "milestone.full_time": ["Final expected goals: {xg_home} to {xg_away}."],
        "milestone.player": [
            "{player_short} reaches {appearance_n} club appearances.",
            "A milestone day for {player_short}.",
        ],
    },
    "metric": {
        "pressure": [
            (
                "Pressure index: {team} {pressure_index}",
                "{team}'s pressure index moved {change} points to {pressure_index}.",
            )
        ],
        "xg": [("xG update: {subject} {xg}", "{subject} is now on {xg} xG, up {change}.")],
        "pass_difficulty": [
            (
                "Pass difficulty {pass_difficulty}",
                "{player_short} completes a pass rated {pass_difficulty} out of {difficulty_scale}.",
            )
        ],
        "top_speed": [
            ("New top speed: {top_speed_kmh} km/h", "{subject} sets a new top speed of {top_speed_kmh} km/h.")
        ],
        "momentum": [("Momentum: {team} on top", "Momentum moved {change} points towards {team}.")],
    },
    "recap": {
        "title_full": "Full-time: {home} {score_home}-{score_away} {away}",
        "title_live": "Match so far: {home} {score_home}-{score_away} {away}",
        "headline_win": "{winner} beat {loser} {score_w}-{score_l}",
        "headline_draw": "{home} and {away} draw {score_home}-{score_away}",
        "headline_lead": "{winner} lead {loser} {score_w}-{score_l}",
        "headline_level": "All square at {score_home}-{score_away}",
        "p1_full": "{home} and {away} finished {score_home}-{score_away}. Expected goals were {xg_home} to {xg_away}, "
        "from {shots_home} and {shots_away} shots.",
        "p1_live": "It is {home} {score_home}-{score_away} {away} at {generated_at}. Expected goals so far: "
        "{xg_home} to {xg_away}, from {shots_home} and {shots_away} shots.",
        "goals": "The goals: {goals_line}.",
        "no_goals": "No goals yet, but {n_big_chances|big chance|big chances} so far.",
        "turning": "We flagged {n_better_options|shot where the pass was better|shots where the pass was better} "
        "and {n_unfound_runs|unfound run|unfound runs}.",
        "potm": {
            "casual": "Player of the match: {potm} of {potm_team}, with {potm_goals|goal|goals} "
            "and {potm_assists|assist|assists}.",
            "tactical": "{n_pressure_spells|pressure spell|pressure spells} and "
            "{n_momentum_swings|momentum swing|momentum swings} shaped it. Player of the match {potm}: "
            "{potm_key_passes|key pass|key passes}, {potm_tackles|tackle won|tackles won}.",
            "fantasy": "Player of the match {potm}: {potm_goals|goal|goals}, {potm_assists|assist|assists}, "
            "{potm_xg} xG, {potm_xa} xA, {potm_key_passes|key pass|key passes}.",
        },
        "focus": "{focus}: {focus_passes_completed} of {focus_passes} passes completed, {focus_distance_km} km "
        "covered, top speed {focus_top_speed_kmh} km/h.",
    },
}

# Football words the templates use as `{g_<term>}` (docs/LANGUAGES.md).
PACK["glossary"] = {
    "box": "box",
    "keeper": "keeper",
    "back_line": "back line",
    "equaliser": "equaliser",
    "comeback": "comeback",
    "let_off": "let-off",
    "rocket": "thunderbolt",
}

_SCORE = "{home} {score_home}-{score_away} {away}"

# Club heart (crew/club_heart.py): the same facts, told from the fan's side.
# `{team}` is the side the moment is about; the fan's own club prints as "your team".
PACK["heart"] = {
    "goal_for": {
        "casual": [
            (
                "GOAL for your team! {player_short} scores",
                "{player} beats the {g_keeper} from {distance_m} m. It's " + _SCORE + ".",
            ),
        ],
        "tactical": [
            (
                "{player_short} converts {xg} xG for your team",
                "From {distance_m} m in the {zone}. " + _SCORE + " at {match_clock}.",
            ),
        ],
        "fantasy": [
            (
                "Goal {player_short}: your team score",
                "{player_short} today: {p_goals|goal|goals} and {p_xg} xG from {p_shots|shot|shots}. "
                "This chance was worth {xg} xG.",
            ),
        ],
    },
    "goal_for_level": {
        "casual": [
            (
                "Level! {player_short} brings your team back",
                "{player} scores the {g_equaliser} at {match_clock}. It's "
                + _SCORE
                + ", and the {g_comeback} is on.",
            ),
        ],
        "tactical": [
            (
                "{player_short} levels it from {xg} xG",
                "A {distance_m} m finish in the {zone}. " + _SCORE + " at {match_clock}.",
            ),
        ],
    },
    "goal_for_pull_back": {
        "casual": [
            (
                "{player_short} pulls a goal back!",
                _SCORE + " at {match_clock}. Your team are back in it, and the {g_comeback} starts here.",
            ),
        ],
        "tactical": [
            (
                "Back in it: {player_short}, {xg} xG",
                "A {distance_m} m finish in the {zone}. " + _SCORE + " at {match_clock}.",
            ),
        ],
    },
    "goal_for_lead": {
        "casual": [
            (
                "GOAL! {player_short} puts your team in front",
                "{player} scores at {match_clock}. It's " + _SCORE + ".",
            ),
        ],
        "tactical": [
            (
                "Your team lead: {player_short}, {xg} xG",
                "A {distance_m} m finish in the {zone} at {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "goal_against": {
        "casual": [
            (
                "{player_short} scores against your team",
                _SCORE + " at {match_clock}. There is time for your team to respond.",
            ),
        ],
        "tactical": [
            (
                "Conceded: {player_short}, {xg} xG",
                "A {distance_m} m finish in the {zone}. "
                + _SCORE
                + " at {match_clock}, with time to respond.",
            ),
        ],
        "fantasy": [
            (
                "{player_short} scores against your team",
                "{player_short} today: {p_goals|goal|goals} and {p_xg} xG from {p_shots|shot|shots}. "
                "This chance was worth {xg} xG.",
            ),
        ],
    },
    "goal_against_level": {
        "casual": [
            (
                "Pegged back: {player_short} levels it",
                _SCORE + " at {match_clock}. Your team need to reset and go again.",
            ),
        ],
        "tactical": [
            (
                "{g_equaliser} against: {player_short}, {xg} xG",
                "A {distance_m} m finish in the {zone}. " + _SCORE + " at {match_clock}.",
            ),
        ],
    },
    "goal_against_lead_cut": {
        "casual": [
            (
                "{player_short} cuts your team's lead",
                _SCORE + " at {match_clock}. Your team are still ahead: stay calm.",
            ),
        ],
        "tactical": [
            (
                "Lead cut: {player_short}, {xg} xG",
                "A {distance_m} m finish in the {zone}. Still ahead at {match_clock}: " + _SCORE + ".",
            ),
        ],
    },
    "goal_against_late": {
        "casual": [
            (
                "Late blow: {player_short} scores",
                _SCORE + " at {match_clock}. Hard to take for your team this late on.",
            ),
        ],
        "tactical": [
            (
                "Late blow: {player_short}, {xg} xG",
                "A {distance_m} m finish in the {zone} at {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "card_own": {
        "casual": [
            (
                "{card_name_cap} for {player_short}",
                "{player} {card_action} at {match_clock}. Your team need cool heads now.",
            ),
        ],
    },
    "card_rival": {
        "casual": [
            (
                "{card_name_cap} for {player_short}",
                "{player} {card_action} at {match_clock}. A chance for your team to press the advantage.",
            ),
        ],
    },
    "let_off": {
        "casual": [
            (
                "{g_let_off} for your team!",
                "{player} had a clear sight of goal for {team} {distance_m} m out, but {outcome_phrase}. "
                "Chances like that go in about {xg_pct}% of the time.",
            ),
        ],
        "tactical": [
            (
                "Danger: {xg} xG chance for {team}",
                "{player_short} shoots from {distance_m} m in the {zone}, but {outcome_phrase}. "
                "Your team's {g_back_line} was opened up.",
            ),
        ],
    },
    "let_off_shot": {
        "casual": [
            (
                "{g_let_off}: {player_short}'s {g_rocket}",
                "{player} hits it at {shot_speed_kmh} km/h from {distance_m} m, and {outcome_phrase}. Your team survive.",
            ),
        ],
    },
    "let_off_choice": {
        "casual": [
            (
                "{g_let_off}: {player_short} chose the shot",
                "{teammate_short} was free, and the pass was worth {times_better}x more than the shot. "
                "Your team got away with it.",
            ),
        ],
        "tactical": [
            (
                "{g_let_off}: {player_short} ignored {teammate_short}",
                "Shot at {shot_xg} xG; the {pass_distance_m} m pass had {pass_success_pct}% success odds. "
                "Your team got away with it.",
            ),
        ],
    },
    "let_off_run": {
        "casual": [
            (
                "{g_let_off}: {runner_short}'s run went unseen",
                "{runner} got in behind your team's {g_back_line}, but {player_short} never played the pass. "
                "It could have been a {projected_xg_pct}% chance.",
            ),
        ],
        "tactical": [
            (
                "{g_let_off}: {runner_short} {clear_of_line_m} m clear",
                "{runner_short} was beyond your team's {g_back_line} at {pass_on_clock}; the pass would have made "
                "a {projected_xg} xG chance. {player_short} missed it.",
            ),
        ],
    },
    "lesson_choice": {
        "casual": [
            (
                "Next time, find {teammate_short}",
                "{player_short} went for goal, but the pass to {teammate_short} was worth {times_better}x more. "
                "Something for your team to work on.",
            ),
        ],
        "tactical": [
            (
                "Learning point: the pass to {teammate_short}",
                "Shot at {shot_xg} xG; the {pass_distance_m} m pass had {pass_success_pct}% success odds and "
                "{alt_xg} xG behind it. The better ball was on.",
            ),
        ],
    },
    "lesson_run": {
        "casual": [
            (
                "{runner_short}'s run deserved the ball",
                "{runner} was {clear_of_line_m} m clear of the {g_back_line}; next time {player_short} can find him. "
                "It could have been a {projected_xg_pct}% chance.",
            ),
        ],
        "tactical": [
            (
                "Unfound run: {runner_short} {clear_of_line_m} m clear",
                "The through ball was on at {pass_on_clock}: a {projected_xg} xG chance. "
                "Next time {player_short} can find him.",
            ),
        ],
    },
    "pressure_for": {
        "casual": [
            (
                "Your team turn the screw",
                "Your team have kept {opp} pinned back for {spell_min|minute|minutes}. Keep it coming.",
            ),
        ],
    },
    "hold_firm": {
        "casual": [
            (
                "Hold firm: {team} are pressing",
                "{team} have pinned your team back for {spell_min|minute|minutes}. "
                "Time to hold firm and keep the ball out of the {g_box}.",
            ),
        ],
        "tactical": [
            (
                "Under pressure: {team} at {pressure_index}",
                "Pressure index {pressure_index} for {spell_min|minute|minutes} with {team_field_tilt_pct}% "
                "field tilt against your team.",
            ),
        ],
    },
    "momentum_against": {
        "casual": [
            (
                "Warning: {team} take control",
                "Momentum moved {momentum_change} points towards {team} in {window_min} minutes. "
                "Your team need a response.",
            ),
        ],
        "tactical": [
            (
                "Momentum shift against your team",
                "Momentum moved {momentum_change} points in {window_min} minutes; {team} have "
                "{team_field_tilt_pct}% field tilt.",
            ),
        ],
    },
    "full_time_won": {"casual": [("Full-time: your team win!", _SCORE + ". A result to enjoy.")]},
    "full_time_lost": {
        "casual": [("Full-time: defeat for your team", _SCORE + ". Time to regroup and go again.")]
    },
    "full_time_drawn": {"casual": [("Full-time: honours even", _SCORE + ". A point apiece.")]},
}
PACK["metric"]["momentum_against"] = [
    ("Warning: momentum to {team}", "Momentum moved {change} points towards {team}, away from your team."),
]
PACK["heart"]["attack_stopped"] = {
    "casual": [
        (
            "{player_short} stops your team's attack",
            "{player} won the ball {own_goal_distance_m} m from his own goal. Your team go again.",
        ),
    ],
    "tactical": [
        (
            "Attack stopped: {xt_stopped} xT taken away",
            "{player_short} won it in his own third, {own_goal_distance_m} m out. Your team must rebuild the move.",
        ),
    ],
}

# Spoiler-safe catch-up (crew/spoilers.py): the story so far without the score,
# the goals or VAR outcomes. Only facts from `recap.story_facts` are filled in.
PACK["story"] = {
    "title": "The story so far: {home} v {away}",
    "headline": "Catch up without the score",
    "p1": "At {generated_at}: xG {xg_home} to {xg_away}, from {shots_home} and {shots_away} shots.",
    "p2": "We flagged {n_big_chances|big chance|big chances}, {n_pressure_spells|pressure spell|pressure spells} "
    "and {n_momentum_swings|momentum swing|momentum swings}.",
    "on_top": "{on_top} are on top right now.",
    "level": "Neither side is on top right now.",
    "watch": "Watch for {n_better_options|shot where the pass was better|shots where the pass was better} "
    "and {n_unfound_runs|unfound run|unfound runs}.",
}
