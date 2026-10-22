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
                    "Card points lost. {player_short} today: {p_goals|goal|goals}, {p_assists|assist|assists}, {p_xg} xG.",
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
                    "Final xG: {home} {xg_home}, {away} {xg_away}. Check your points.",
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
