"""Phrases de plateau en français. Même format que en.py."""

PACK = {
    "your_team": "votre équipe",
    "labels": {
        "xg": "Qualité de l'occasion (xG)",
        "distance_m": "Distance au but",
        "shot_speed_kmh": "Vitesse de la frappe",
        "score_home": "Score domicile",
        "score_away": "Score extérieur",
        "card": "Carton",
        "shot_xg": "xG de la frappe",
        "alt_xg": "xG du coéquipier",
        "pass_success_pct": "Chances de réussite de la passe",
        "alt_value": "Valeur attendue de la passe",
        "times_better": "Passe contre tir",
        "pass_distance_m": "Longueur de la passe",
        "nearest_marker_m": "Adversaire le plus proche",
        "clear_of_line_m": "Avance sur la ligne défensive",
        "projected_xg": "xG projeté de l'occasion",
        "pass_on_clock": "Passe possible à la",
        "one_on_one": "Face-à-face",
        "momentum_change": "Changement d'élan",
        "window_min": "Période",
        "team_field_tilt_pct": "Domination territoriale",
        "team_shots_5": "Tirs (5 dernières min)",
        "team_xg_total": "xG de l'équipe",
        "pressure_index": "Indice de pression",
        "spell_min": "Durée de la phase",
        "team_box_entries_5": "Entrées dans la surface (5 dernières min)",
        "speed_kmh": "Vitesse",
        "top_speed_kmh": "Vitesse maximale",
        "sprints": "Sprints",
        "milestone_km": "Distance (estimée)",
        "pass_difficulty": "Difficulté de la passe",
        "xt_delta": "Menace ajoutée (xT)",
        "xg_home": "xG domicile",
        "xg_away": "xG extérieur",
        "shots_home": "Tirs domicile",
        "shots_away": "Tirs extérieur",
        "appearance_n": "Matchs avec le club",
    },
    "zones": {
        "Penalty Box": "la surface",
        "Attacking Third": "le dernier tiers",
        "Middle Third": "l'entrejeu",
        "Defensive Third": "son propre camp",
        "": "le jeu",
    },
    "outcomes": {
        "saved": "le gardien a sorti le ballon",
        "blocked": "un défenseur a contré",
        "off_target": "c'est passé à côté",
        "goal": "c'est au fond",
        "": "rien n'en est sorti",
    },
    "card_name": {"yellow": "carton jaune", "red": "carton rouge"},
    "card_name_cap": {"yellow": "Carton jaune", "red": "Carton rouge"},
    "card_action": {"yellow": "est averti", "red": "est exclu"},
    "fav_goal": {
        "for": "BUT pour votre équipe ! {player_short} marque",
        "against": "{player_short} marque contre votre équipe",
    },
    "narr": {
        "goal": {
            "casual": [
                (
                    "BUT ! {player_short} marque pour {team}",
                    "{player} conclut sur un service de {assist}. {home} {score_home}-{score_away} {away}.",
                ),
                (
                    "BUT ! {player_short} marque pour {team}",
                    "{player} trouve le chemin des filets. {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "tactical": [
                (
                    "{player_short} convertit une occasion à {xg} xG",
                    "{assist_short} trouve {player_short} à {distance_m} m, dans {zone}. "
                    "{home} {score_home}-{score_away} {away}.",
                ),
                (
                    "{player_short} convertit une occasion à {xg} xG",
                    "{player_short} conclut à {distance_m} m, dans {zone}. {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "fantasy": [
                (
                    "But {player_short}, passe décisive {assist_short}",
                    "{player_short} aujourd'hui : {p_goals|but|buts} et {p_xg} xG en {p_shots|tir|tirs}. "
                    "Cette occasion valait {xg} xG.",
                ),
                (
                    "But de {player_short}",
                    "{player_short} aujourd'hui : {p_goals|but|buts} et {p_xg} xG en {p_shots|tir|tirs}. "
                    "Cette occasion valait {xg} xG.",
                ),
            ],
            "player_spotlight": [
                (
                    "{player_short} marque !",
                    "{player} bat le gardien à {distance_m} m. {home} {score_home}-{score_away} {away}.",
                )
            ],
        },
        "card": {
            "casual": [
                (
                    "{card_name_cap} pour {player_short}",
                    "{player} {card_action}. {team} doit faire attention.",
                )
            ],
            "tactical": [
                (
                    "{card_name_cap} : {player_short}",
                    "{player} {card_action}. {team} va devoir défendre ce couloir avec plus de prudence.",
                )
            ],
            "fantasy": [
                (
                    "{card_name_cap} pour {player_short}",
                    "{player_short} {card_action}. Aujourd'hui : {p_goals|but|buts}, "
                    "{p_assists|passe décisive|passes décisives}, {p_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{card_name_cap} pour {player_short}",
                    "{player} {card_action}. Chaque duel devient un risque.",
                )
            ],
        },
        "big_chance": {
            "casual": [
                (
                    "Grosse occasion pour {player_short} !",
                    "{player} se présente face au but à {distance_m} m, mais {outcome_phrase}. "
                    "Ce genre d'occasion finit au fond environ {xg_pct} % du temps.",
                )
            ],
            "tactical": [
                (
                    "Occasion à {xg} xG pour {team}",
                    "{player_short} frappe à {distance_m} m, dans {zone}, mais {outcome_phrase}. "
                    "Valeur du tir : {xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} : occasion à {xg} xG",
                    "{player_short} cumule {p_xg} xG en {p_shots|tir|tirs}. Celle-ci n'est pas rentrée.",
                )
            ],
            "player_spotlight": [
                (
                    "Grosse occasion pour {player_short}",
                    "{player_short} trouve de l'espace à {distance_m} m, mais {outcome_phrase}. "
                    "Aujourd'hui : {p_shots|tir|tirs}, {p_xg} xG.",
                )
            ],
        },
        "better_option": {
            "casual": [
                (
                    "{player_short} aurait-il dû passer ?",
                    "{player_short} a tenté sa chance, mais {teammate_short} était seul. "
                    "La passe valait {times_better} fois plus que le tir.",
                )
            ],
            "tactical": [
                (
                    "Mauvais choix : {player_short} ignore {teammate_short}",
                    "Tir à {shot_xg} xG ; la passe de {pass_distance_m} m avait {pass_success_pct} % de réussite "
                    "et une occasion à {alt_xg} xG derrière. Valeur attendue {alt_value}, {times_better} fois le tir.",
                )
            ],
            "fantasy": [
                (
                    "Passe décisive manquée par {player_short}",
                    "Servir {teammate_short} valait {alt_value} but attendu contre {shot_xg} xG pour le tir. "
                    "{player_short} aujourd'hui : {p_xg} xG en {p_shots|tir|tirs}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} a choisi de frapper",
                    "{teammate_short} était libre à {pass_distance_m} m, sans adversaire à moins de "
                    "{nearest_marker_m} m. La passe valait {times_better} fois mieux que le tir.",
                )
            ],
        },
        "unfound_run": {
            "casual": [
                (
                    "L'appel de {runner_short} est resté sans réponse",
                    "{runner} s'est échappé dans le dos de la défense, mais {player_short} n'a jamais fait la passe. "
                    "C'était une occasion à {projected_xg_pct} %.",
                )
            ],
            "tactical": [
                (
                    "Appel non servi : {runner_short} dans le dos",
                    "{runner_short} a pris {clear_of_line_m} m à la dernière ligne et la passe en profondeur "
                    "était possible à {pass_on_clock}. Occasion projetée : {projected_xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{runner_short} privé de {projected_xg} xG",
                    "La passe en profondeur de {player_short} n'est jamais venue. Cet appel valait {projected_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{runner_short} attaque la profondeur",
                    "{runner_short} a pris {clear_of_line_m} m à la défense, mais {player_short} a gardé le ballon.",
                )
            ],
        },
        "momentum_swing": {
            "casual": [
                (
                    "{team} prend le contrôle",
                    "Le match bascule vers {team} : la dynamique a bougé de {momentum_change} points "
                    "en {window_min} minutes.",
                )
            ],
            "tactical": [
                (
                    "Bascule de dynamique vers {team}",
                    "La dynamique a bougé de {momentum_change} points en {window_min} minutes. "
                    "{team} occupe désormais {team_field_tilt_pct} % du territoire offensif.",
                )
            ],
            "fantasy": [
                (
                    "{team} domine : surveillez ses attaquants",
                    "{team} compte {team_shots_5|tir|tirs} sur les {window_min} dernières minutes. "
                    "Son xG du match atteint {team_xg_total}.",
                )
            ],
        },
        "pressure_spell": {
            "casual": [
                (
                    "{team} met la pression",
                    "{team} enferme {opp} depuis {spell_min} minutes. Quelque chose va finir par céder.",
                )
            ],
            "tactical": [
                (
                    "Pressing continu : {team} à {pressure_index}",
                    "Indice de pression {pressure_index} pendant {spell_min} minutes, avec {team_field_tilt_pct} % "
                    "du territoire offensif. {opp} ne peut pas relancer proprement.",
                )
            ],
            "fantasy": [
                (
                    "{team} presse haut",
                    "{team} compte {team_shots_5|tir|tirs} sur les {window_min} dernières minutes "
                    "et {team_xg_total} xG dans le match. Ses attaquants se procurent des occasions.",
                )
            ],
        },
        "speed_burst": {
            "casual": [
                (
                    "{player_short} à {speed_kmh} km/h",
                    "{player} passe la cinquième à {speed_kmh} km/h. Cela fait {sprints|sprint|sprints}.",
                )
            ],
            "tactical": [
                (
                    "Sprint : {player_short} à {speed_kmh} km/h",
                    "{player_short} dépasse le seuil de sprint de {speed_threshold_kmh} km/h. "
                    "Sprints aujourd'hui : {sprints}.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} en mouvement",
                    "{player_short} jusqu'ici : {p_shots|tir|tirs}, {p_xg} xG et "
                    "{p_key_passes|passe clé|passes clés}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} à pleine vitesse",
                    "{speed_kmh} km/h ; sa pointe du jour est de {top_speed_kmh} km/h. Sprints : {sprints}.",
                )
            ],
        },
        "rocket_shot": {
            "casual": [
                (
                    "Missile de {player_short} !",
                    "{player} frappe à {shot_speed_kmh} km/h et {outcome_phrase}.",
                )
            ],
            "tactical": [
                (
                    "Frappe à {shot_speed_kmh} km/h de {player_short}",
                    "Ballon à {shot_speed_kmh} km/h à {distance_m} m sur une occasion à {xg} xG. "
                    "À cette vitesse, le gardien n'a presque pas le temps de réagir.",
                )
            ],
            "fantasy": [
                ("Tir de {player_short} : {xg} xG", "{player_short} cumule {p_xg} xG en {p_shots|tir|tirs}.")
            ],
            "player_spotlight": [
                (
                    "{player_short} déclenche",
                    "{shot_speed_kmh} km/h à {distance_m} m, et {outcome_phrase}.",
                )
            ],
        },
        "distance_milestone": {
            "casual": [
                (
                    "{player_short} : cap des {milestone_km} km (est.)",
                    "{player} a déjà parcouru environ {milestone_km} km, selon notre estimation. Il ne s'arrête jamais.",
                )
            ],
            "tactical": [
                (
                    "Volume : {player_short}, {milestone_km} km (est.)",
                    "{player_short} passe le cap des {milestone_km} km (estimation) avec {sprints|sprint|sprints}. "
                    "Pointe de vitesse : {top_speed_kmh} km/h.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} : environ {milestone_km} km de course",
                    "Beaucoup de courses (distance estimée) ; en attaque : {p_shots|tir|tirs}, {p_xg} xG et "
                    "{p_key_passes|passe clé|passes clés}.",
                )
            ],
            "player_spotlight": [
                (
                    "{milestone_km} km (est.) pour {player_short}",
                    "{player_short} atteint environ {milestone_km} km, avec {sprints|sprint|sprints} "
                    "et une pointe à {top_speed_kmh} km/h.",
                )
            ],
        },
        "hard_pass": {
            "casual": [
                (
                    "Quelle passe de {player_short} !",
                    "{player} trouve {receiver_short} d'une passe de {pass_distance_m} m. "
                    "Difficulté : {pass_difficulty} sur {difficulty_scale}.",
                )
            ],
            "tactical": [
                (
                    "PDR {pass_difficulty} : {player_short} trouve {receiver_short}",
                    "Passe de {pass_distance_m} m de difficulté {pass_difficulty}, qui ajoute {xt_delta} xT.",
                ),
                (
                    "PDR {pass_difficulty} : {player_short} trouve {receiver_short}",
                    "Passe de {pass_distance_m} m de difficulté {pass_difficulty}, entre les lignes.",
                ),
            ],
            "fantasy": [
                (
                    "{player_short} se crée des occasions",
                    "{player_short} aujourd'hui : {p_key_passes|passe clé|passes clés} et {p_xa} xA.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} glisse le ballon",
                    "Passe de {pass_distance_m} m pour {receiver_short}, difficulté {pass_difficulty} "
                    "sur {difficulty_scale}.",
                )
            ],
        },
        "milestone.kick_off": {
            "casual": [
                (
                    "Coup d'envoi : {home} contre {away}",
                    "{home} contre {away}, c'est parti. Nous signalerons les moments qui comptent.",
                )
            ],
            "tactical": [
                (
                    "Coup d'envoi : {home} contre {away}",
                    "{home} contre {away}, c'est parti. Suivez la pression et la dynamique dès le premier coup de sifflet.",
                )
            ],
            "fantasy": [
                (
                    "Coup d'envoi : {home} contre {away}",
                    "{home} contre {away}, c'est parti. Buts, passes décisives, xG, xA, tirs et passes clés en direct.",
                )
            ],
        },
        "milestone.half_time": {
            "casual": [
                (
                    "Mi-temps : {home} {score_home}-{score_away} {away}",
                    "C'est la pause. Tirs : {shots_home} pour {home}, {shots_away} pour {away}.",
                )
            ],
            "tactical": [
                (
                    "Mi-temps : {home} {score_home}-{score_away} {away}",
                    "Buts attendus {xg_home} à {xg_away}, tirs {shots_home} à {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "Mi-temps : {home} {score_home}-{score_away} {away}",
                    "xG à la pause : {home} {xg_home}, {away} {xg_away}.",
                )
            ],
        },
        "milestone.full_time": {
            "casual": [
                (
                    "Fin du match : {home} {score_home}-{score_away} {away}",
                    "C'est terminé. {home} a tenté {shots_home|tir|tirs} et {away} {shots_away|tir|tirs}.",
                )
            ],
            "tactical": [
                (
                    "Fin du match : {home} {score_home}-{score_away} {away}",
                    "Buts attendus finaux {xg_home} à {xg_away}, tirs {shots_home} à {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "Fin du match : {home} {score_home}-{score_away} {away}",
                    "xG final : {home} {xg_home}, {away} {xg_away}. Tirs : {shots_home} contre {shots_away}.",
                )
            ],
        },
        "milestone.player": {
            "casual": [
                (
                    "{appearance_n}e match pour {player_short}",
                    "{player} dispute aujourd'hui son {appearance_n}e match avec {team}.",
                ),
                ("Un cap pour {player_short}", "{player} franchit un cap avec {team} aujourd'hui."),
            ],
            "tactical": [
                (
                    "{player_short} : {appearance_n}e match au club",
                    "{player} dispute son {appearance_n}e match avec {team}.",
                ),
                ("Un cap pour {player_short}", "{player} franchit un cap avec {team} aujourd'hui."),
            ],
            "fantasy": [
                (
                    "{player_short} : {appearance_n}e match au club",
                    "{player_short} aujourd'hui : {p_goals|but|buts}, {p_assists|passe décisive|passes décisives}, "
                    "{p_xg} xG.",
                ),
                (
                    "Un cap pour {player_short}",
                    "{player_short} aujourd'hui : {p_goals|but|buts}, {p_assists|passe décisive|passes décisives}, "
                    "{p_xg} xG.",
                ),
            ],
        },
    },
    "why": {
        "goal": ["Le score passe à {home} {score_home}-{score_away} {away}, sur une occasion à {xg} xG."],
        "card": ["{player_short} {card_action} : {team} doit adapter sa façon de défendre."],
        "big_chance": [
            "Une occasion à {xg} xG est une vraie opportunité : {team} arrive dans les zones dangereuses."
        ],
        "better_option": [
            "La passe vers {teammate_short} valait {alt_value} but attendu contre {shot_xg} pour le tir, "
            "soit {times_better} fois plus."
        ],
        "unfound_run": [
            "{runner_short} avait {clear_of_line_m} m d'avance sur la dernière ligne à {pass_on_clock} ; "
            "la passe aurait créé une occasion à {projected_xg} xG."
        ],
        "momentum_swing": [
            "La dynamique a bougé de {momentum_change} points en {window_min} minutes : le contrôle a changé de camp."
        ],
        "pressure_spell": [
            "Un indice de pression de {pressure_index} pendant {spell_min} minutes empêche {opp} de relancer "
            "sereinement."
        ],
        "speed_burst": [
            "{speed_kmh} km/h dépasse le seuil de sprint de {speed_threshold_kmh} km/h ; la vitesse étire une défense."
        ],
        "rocket_shot": ["À {shot_speed_kmh} km/h, le gardien n'a presque pas le temps de réagir."],
        "distance_milestone": [
            "Environ {milestone_km} km de course (estimation) : c'est le travail derrière le bloc de {team}."
        ],
        "hard_pass": [
            "Une difficulté de {pass_difficulty} sur {difficulty_scale}, c'est une passe que peu de joueurs réussissent."
        ],
        "milestone.kick_off": ["Le match est lancé."],
        "milestone.half_time": ["À la pause, les buts attendus sont de {xg_home} à {xg_away}."],
        "milestone.full_time": ["Buts attendus finaux : {xg_home} à {xg_away}."],
        "milestone.player": [
            "{player_short} atteint {appearance_n} matchs avec le club.",
            "Un jour à marquer pour {player_short}.",
        ],
    },
    "metric": {
        "pressure": [
            (
                "Indice de pression : {team} {pressure_index}",
                "L'indice de pression de {team} a bougé de {change} points, à {pressure_index}.",
            )
        ],
        "xg": [("xG : {subject} {xg}", "{subject} atteint {xg} xG, en hausse de {change}.")],
        "pass_difficulty": [
            (
                "Difficulté de passe {pass_difficulty}",
                "{player_short} réussit une passe de difficulté {pass_difficulty} sur {difficulty_scale}.",
            )
        ],
        "top_speed": [
            (
                "Nouvelle pointe : {top_speed_kmh} km/h",
                "{subject} établit une nouvelle pointe de vitesse à {top_speed_kmh} km/h.",
            )
        ],
        "momentum": [
            (
                "Dynamique : {team} prend le dessus",
                "La dynamique a bougé de {change} points en faveur de {team}.",
            )
        ],
    },
    "recap": {
        "title_full": "Fin du match : {home} {score_home}-{score_away} {away}",
        "title_live": "Le match jusqu'ici : {home} {score_home}-{score_away} {away}",
        "headline_win": "{winner} bat {loser} {score_w}-{score_l}",
        "headline_draw": "{home} et {away} se quittent sur un {score_home}-{score_away}",
        "headline_lead": "{winner} mène {score_w}-{score_l} contre {loser}",
        "headline_level": "Égalité parfaite, {score_home}-{score_away}",
        "p1_full": "{home} et {away} se sont quittés sur le score de {score_home}-{score_away}. Les buts attendus : "
        "{xg_home} à {xg_away}, pour {shots_home} et {shots_away} tirs.",
        "p1_live": "{home} {score_home}-{score_away} {away} à {generated_at}. Buts attendus jusqu'ici : "
        "{xg_home} à {xg_away}, pour {shots_home} et {shots_away} tirs.",
        "goals": "Les buts : {goals_line}.",
        "no_goals": "Pas encore de but, mais déjà {n_big_chances|grosse occasion|grosses occasions}.",
        "turning": "Nous avons relevé {n_better_options|tir où la passe était meilleure|tirs où la passe était meilleure} "
        "et {n_unfound_runs|appel non servi|appels non servis}.",
        "potm": {
            "casual": "Homme du match : {potm} ({potm_team}), avec {potm_goals|but|buts} "
            "et {potm_assists|passe décisive|passes décisives}.",
            "tactical": "{n_pressure_spells|phase de pressing|phases de pressing} et "
            "{n_momentum_swings|bascule de dynamique|bascules de dynamique} ont rythmé le match. Homme du match, "
            "{potm} : {potm_key_passes|passe clé|passes clés}, {potm_tackles|tacle réussi|tacles réussis}.",
            "fantasy": "Homme du match, {potm} : {potm_goals|but|buts}, "
            "{potm_assists|passe décisive|passes décisives}, {potm_xg} xG, {potm_xa} xA, "
            "{potm_key_passes|passe clé|passes clés}.",
        },
        "focus": "{focus} : {focus_passes_completed} passes réussies sur {focus_passes}, {focus_distance_km} km "
        "parcourus, pointe à {focus_top_speed_kmh} km/h.",
    },
}

# Vocabulaire du football utilisé par les modèles sous la forme `{g_<terme>}` (docs/LANGUAGES.md).
PACK["glossary"] = {
    "box": "surface",
    "keeper": "gardien",
    "back_line": "défense",
    "equaliser": "égalisation",
    "comeback": "remontada",
    "let_off": "frayeur",
    "rocket": "mine",
}

_SCORE = "{home} {score_home}-{score_away} {away}"

# Cœur de club (crew/club_heart.py) : les mêmes faits, racontés du côté du supporter.
PACK["heart"] = {
    "goal_for": {
        "casual": [
            (
                "BUT pour votre équipe ! {player_short} marque",
                "{player} bat le {g_keeper} à {distance_m} m. " + _SCORE + ".",
            ),
        ],
        "tactical": [
            (
                "{player_short} convertit {xg} xG pour votre équipe",
                "Frappe à {distance_m} m, dans {zone}. " + _SCORE + " à {match_clock}.",
            ),
        ],
        "fantasy": [
            (
                "But de {player_short} pour votre équipe",
                "{player_short} aujourd'hui : {p_goals|but|buts} et {p_xg} xG en {p_shots|tir|tirs}. "
                "Cette occasion valait {xg} xG.",
            ),
        ],
    },
    "goal_for_level": {
        "casual": [
            (
                "{g_equaliser} ! {player_short} relance votre équipe",
                "{player} égalise à {match_clock}. " + _SCORE + " : la {g_comeback} est lancée.",
            ),
        ],
        "tactical": [
            (
                "{player_short} égalise sur {xg} xG",
                "Frappe à {distance_m} m, dans {zone}. " + _SCORE + " à {match_clock}.",
            ),
        ],
    },
    "goal_for_pull_back": {
        "casual": [
            (
                "{player_short} réduit l'écart !",
                _SCORE + " à {match_clock}. Votre équipe est relancée : la {g_comeback} commence ici.",
            ),
        ],
        "tactical": [
            (
                "Votre équipe réduit l'écart : {player_short}, {xg} xG",
                "Frappe à {distance_m} m, dans {zone}. " + _SCORE + " à {match_clock}.",
            ),
        ],
    },
    "goal_for_lead": {
        "casual": [
            (
                "BUT ! {player_short} donne l'avantage à votre équipe",
                "{player} marque à {match_clock}. " + _SCORE + ".",
            ),
        ],
        "tactical": [
            (
                "Avantage votre équipe : {player_short}, {xg} xG",
                "Frappe à {distance_m} m, dans {zone}, à {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "goal_against": {
        "casual": [
            (
                "{player_short} marque contre votre équipe",
                _SCORE + " à {match_clock}. Votre équipe a encore le temps de réagir.",
            ),
        ],
        "tactical": [
            (
                "But encaissé : {player_short}, {xg} xG",
                "Frappe à {distance_m} m, dans {zone}. "
                + _SCORE
                + " à {match_clock} : il reste du temps pour réagir.",
            ),
        ],
        "fantasy": [
            (
                "{player_short} marque contre votre équipe",
                "{player_short} aujourd'hui : {p_goals|but|buts} et {p_xg} xG en {p_shots|tir|tirs}. "
                "Cette occasion valait {xg} xG.",
            ),
        ],
    },
    "goal_against_level": {
        "casual": [
            (
                "Rejoint au score : {player_short} égalise",
                _SCORE + " à {match_clock}. Votre équipe doit se remobiliser.",
            ),
        ],
        "tactical": [
            (
                "{g_equaliser} adverse : {player_short}, {xg} xG",
                "Frappe à {distance_m} m, dans {zone}. " + _SCORE + " à {match_clock}.",
            ),
        ],
    },
    "goal_against_lead_cut": {
        "casual": [
            (
                "{player_short} réduit l'écart contre votre équipe",
                _SCORE + " à {match_clock}. Votre équipe mène toujours : du calme.",
            ),
        ],
        "tactical": [
            (
                "Écart réduit : {player_short}, {xg} xG",
                "Frappe à {distance_m} m, dans {zone}. Toujours devant à {match_clock} : " + _SCORE + ".",
            ),
        ],
    },
    "goal_against_late": {
        "casual": [
            (
                "Coup dur : {player_short} marque",
                _SCORE + " à {match_clock}. Difficile à encaisser pour votre équipe si tard.",
            ),
        ],
        "tactical": [
            (
                "Coup dur tardif : {player_short}, {xg} xG",
                "Frappe à {distance_m} m, dans {zone}, à {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "card_own": {
        "casual": [
            (
                "{card_name_cap} pour {player_short}",
                "{player} {card_action} à {match_clock}. Votre équipe doit garder la tête froide.",
            ),
        ],
    },
    "card_rival": {
        "casual": [
            (
                "{card_name_cap} pour {player_short}",
                "{player} {card_action} à {match_clock}. À votre équipe d'en profiter.",
            ),
        ],
    },
    "let_off": {
        "casual": [
            (
                "Grosse {g_let_off} pour votre équipe !",
                "{player} avait une belle occasion pour {team} à {distance_m} m, mais {outcome_phrase}. "
                "Ce genre d'occasion finit au fond environ {xg_pct} % du temps.",
            ),
        ],
        "tactical": [
            (
                "Danger : occasion à {xg} xG pour {team}",
                "{player_short} frappe à {distance_m} m, dans {zone}, mais {outcome_phrase}. "
                "La {g_back_line} de votre équipe a été prise de vitesse.",
            ),
        ],
    },
    "let_off_shot": {
        "casual": [
            (
                "{g_let_off} : la {g_rocket} de {player_short}",
                "{player} frappe à {shot_speed_kmh} km/h à {distance_m} m, et {outcome_phrase}. Votre équipe s'en sort.",
            ),
        ],
    },
    "let_off_choice": {
        "casual": [
            (
                "{g_let_off} : {player_short} a préféré frapper",
                "{teammate_short} était libre, et la passe valait {times_better} fois plus que le tir. "
                "Votre équipe s'en sort bien.",
            ),
        ],
        "tactical": [
            (
                "Votre équipe s'en sort : {player_short} a ignoré {teammate_short}",
                "Tir à {shot_xg} xG ; la passe de {pass_distance_m} m avait {pass_success_pct} % de chances de réussir. "
                "Votre équipe s'en sort bien.",
            ),
        ],
    },
    "let_off_run": {
        "casual": [
            (
                "{g_let_off} : l'appel de {runner_short} ignoré",
                "{runner} a pris la {g_back_line} de votre équipe dans le dos, mais {player_short} n'a jamais donné "
                "la passe. Ça pouvait être une occasion à {projected_xg_pct} %.",
            ),
        ],
        "tactical": [
            (
                "{g_let_off} : {runner_short}, {clear_of_line_m} m d'avance",
                "{runner_short} avait passé la {g_back_line} de votre équipe à {pass_on_clock} ; la passe aurait "
                "offert {projected_xg} xG. {player_short} ne l'a pas vu.",
            ),
        ],
    },
    "lesson_choice": {
        "casual": [
            (
                "La prochaine fois, trouver {teammate_short}",
                "{player_short} a frappé, mais la passe à {teammate_short} valait {times_better} fois plus. "
                "Un point à travailler pour votre équipe.",
            ),
        ],
        "tactical": [
            (
                "Leçon : la passe vers {teammate_short}",
                "Tir à {shot_xg} xG ; la passe de {pass_distance_m} m avait {pass_success_pct} % de réussite et "
                "{alt_xg} xG derrière. Le bon ballon était là.",
            ),
        ],
    },
    "lesson_run": {
        "casual": [
            (
                "L'appel de {runner_short} méritait le ballon",
                "{runner} avait {clear_of_line_m} m d'avance sur la {g_back_line} ; la prochaine fois, {player_short} "
                "peut le trouver. Ça pouvait être une occasion à {projected_xg_pct} %.",
            ),
        ],
        "tactical": [
            (
                "Appel ignoré : {runner_short}, {clear_of_line_m} m d'avance",
                "La passe en profondeur était possible à {pass_on_clock} : une occasion à {projected_xg} xG. "
                "La prochaine fois, {player_short} peut le trouver.",
            ),
        ],
    },
    "pressure_for": {
        "casual": [
            (
                "Votre équipe met la pression",
                "Votre équipe enferme {opp} depuis {spell_min|minute|minutes}. Il faut continuer.",
            ),
        ],
    },
    "hold_firm": {
        "casual": [
            (
                "Tenir bon : {team} pousse",
                "{team} enferme votre équipe depuis {spell_min|minute|minutes}. "
                "Il faut tenir et garder le ballon loin de la {g_box}.",
            ),
        ],
        "tactical": [
            (
                "Sous pression : {team} à {pressure_index}",
                "Indice de pression {pressure_index} depuis {spell_min|minute|minutes}, avec {team_field_tilt_pct} % "
                "de domination territoriale contre votre équipe.",
            ),
        ],
    },
    "momentum_against": {
        "casual": [
            (
                "Attention : {team} prend le contrôle",
                "La dynamique a bougé de {momentum_change} points vers {team} en {window_min} minutes. "
                "Votre équipe doit réagir.",
            ),
        ],
        "tactical": [
            (
                "La dynamique tourne contre votre équipe",
                "La dynamique a bougé de {momentum_change} points en {window_min} minutes ; {team} a "
                "{team_field_tilt_pct} % de domination territoriale.",
            ),
        ],
    },
    "full_time_won": {
        "casual": [("Fin du match : victoire de votre équipe !", _SCORE + ". Un résultat à savourer.")]
    },
    "full_time_lost": {
        "casual": [("Fin du match : défaite de votre équipe", _SCORE + ". Il faudra se relever.")]
    },
    "full_time_drawn": {"casual": [("Fin du match : match nul", _SCORE + ". Chacun repart avec un point.")]},
}
PACK["metric"]["momentum_against"] = [
    (
        "Attention : la dynamique pour {team}",
        "La dynamique a bougé de {change} points en faveur de {team}, au détriment de votre équipe.",
    ),
]
