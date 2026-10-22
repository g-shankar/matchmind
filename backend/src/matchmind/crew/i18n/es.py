"""Frases de estudio en español. Mismo formato que en.py."""

PACK = {
    "your_team": "tu equipo",
    "labels": {
        "xg": "Calidad de la ocasión (xG)",
        "distance_m": "Distancia a portería",
        "shot_speed_kmh": "Velocidad del disparo",
        "score_home": "Goles local",
        "score_away": "Goles visitante",
        "card": "Tarjeta",
        "shot_xg": "xG del disparo",
        "alt_xg": "xG del compañero",
        "pass_success_pct": "Probabilidad de acierto del pase",
        "alt_value": "Valor esperado del pase",
        "times_better": "Pase frente a disparo",
        "pass_distance_m": "Distancia del pase",
        "nearest_marker_m": "Marcador más cercano",
        "clear_of_line_m": "Ventaja sobre la línea defensiva",
        "projected_xg": "xG proyectado de la ocasión",
        "pass_on_clock": "El pase era posible en el",
        "one_on_one": "Mano a mano",
        "momentum_change": "Cambio de dominio",
        "window_min": "Ventana",
        "team_field_tilt_pct": "Dominio territorial",
        "team_shots_5": "Disparos (últimos 5 min)",
        "team_xg_total": "xG del equipo",
        "pressure_index": "Índice de presión",
        "spell_min": "Duración de la fase",
        "team_box_entries_5": "Entradas al área (últimos 5 min)",
        "speed_kmh": "Velocidad",
        "top_speed_kmh": "Velocidad máxima",
        "sprints": "Sprints",
        "milestone_km": "Distancia (estimada)",
        "pass_difficulty": "Dificultad del pase",
        "xt_delta": "Amenaza añadida (xT)",
        "xg_home": "xG local",
        "xg_away": "xG visitante",
        "shots_home": "Disparos local",
        "shots_away": "Disparos visitante",
        "appearance_n": "Partidos con el club",
        "xt_stopped": "Amenaza frenada (xT)",
        "own_goal_distance_m": "Distancia a su portería",
        "p_tackles_won": "Entradas ganadas",
        "last_ditch": "Al límite (en su área)",
        "distance_km": "Distancia (est. por seguimiento)",
        "sprint_m": "Longitud del esprint",
    },
    "zones": {
        "Penalty Box": "el área",
        "Attacking Third": "el último tercio",
        "Middle Third": "la zona media",
        "Defensive Third": "su propio campo",
        "": "juego abierto",
    },
    "outcomes": {
        "saved": "el portero la atajó",
        "blocked": "un defensa la bloqueó",
        "off_target": "se fue fuera",
        "goal": "acabó dentro",
        "": "no prosperó",
    },
    "card_name": {"yellow": "tarjeta amarilla", "red": "tarjeta roja"},
    "card_name_cap": {"yellow": "Tarjeta amarilla", "red": "Tarjeta roja"},
    "card_action": {"yellow": "ve la amarilla", "red": "es expulsado"},
    "fav_goal": {
        "for": "¡GOL de tu equipo! Marca {player_short}",
        "against": "{player_short} marca contra tu equipo",
    },
    "narr": {
        "goal": {
            "casual": [
                (
                    "¡GOL! {player_short} marca para {team}",
                    "{player} define tras el pase de {assist}. {home} {score_home}-{score_away} {away}.",
                ),
                (
                    "¡GOL! {player_short} marca para {team}",
                    "{player} la manda dentro. {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "tactical": [
                (
                    "{player_short} convierte una ocasión de {xg} xG",
                    "{assist_short} encuentra a {player_short} a {distance_m} m, en {zone}. "
                    "{home} {score_home}-{score_away} {away}.",
                ),
                (
                    "{player_short} convierte una ocasión de {xg} xG",
                    "{player_short} define desde {distance_m} m, en {zone}. {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "fantasy": [
                (
                    "Gol de {player_short}, asistencia de {assist_short}",
                    "{player_short} hoy: {p_goals|gol|goles} y {p_xg} xG en {p_shots|tiro|tiros}. "
                    "Esta ocasión valía {xg} xG.",
                ),
                (
                    "Gol de {player_short}",
                    "{player_short} hoy: {p_goals|gol|goles} y {p_xg} xG en {p_shots|tiro|tiros}. "
                    "Esta ocasión valía {xg} xG.",
                ),
            ],
            "player_spotlight": [
                (
                    "¡Marca {player_short}!",
                    "{player} bate al portero desde {distance_m} m. {home} {score_home}-{score_away} {away}.",
                )
            ],
        },
        "card": {
            "casual": [
                (
                    "{card_name_cap} para {player_short}",
                    "{player} {card_action}. {team} tendrá que tener cuidado.",
                )
            ],
            "tactical": [
                (
                    "{card_name_cap}: {player_short}",
                    "{player} {card_action}. {team} tendrá que defender esa banda con más cautela.",
                )
            ],
            "fantasy": [
                (
                    "{card_name_cap} para {player_short}",
                    "{player_short} {card_action}. Hoy: {p_goals|gol|goles}, {p_assists|asistencia|asistencias}, "
                    "{p_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{card_name_cap} para {player_short}",
                    "{player} {card_action}. Cada duelo a partir de ahora es un riesgo.",
                )
            ],
        },
        "big_chance": {
            "casual": [
                (
                    "¡Ocasión clara de {player_short}!",
                    "{player} se plantó ante el gol a {distance_m} m, pero {outcome_phrase}. "
                    "Ocasiones así acaban en gol un {xg_pct}% de las veces.",
                )
            ],
            "tactical": [
                (
                    "Ocasión de {xg} xG para {team}",
                    "{player_short} remata desde {distance_m} m, en {zone}, pero {outcome_phrase}. "
                    "Valor del tiro: {xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{player_short}: ocasión de {xg} xG",
                    "{player_short} suma {p_xg} xG en {p_shots|tiro|tiros}. Esta no entró.",
                )
            ],
            "player_spotlight": [
                (
                    "Ocasión clara de {player_short}",
                    "{player_short} encuentra espacio a {distance_m} m, pero {outcome_phrase}. "
                    "Hoy: {p_shots|tiro|tiros}, {p_xg} xG.",
                )
            ],
        },
        "better_option": {
            "casual": [
                (
                    "¿Debió pasarla {player_short}?",
                    "{player_short} buscó el gol, pero {teammate_short} estaba solo. "
                    "El pase valía {times_better} veces más que el tiro.",
                )
            ],
            "tactical": [
                (
                    "Mala elección: {player_short} ignoró a {teammate_short}",
                    "Tiro de {shot_xg} xG; el pase de {pass_distance_m} m tenía un {pass_success_pct}% de éxito "
                    "y una ocasión de {alt_xg} xG detrás. Valor esperado {alt_value}, {times_better} veces el tiro.",
                )
            ],
            "fantasy": [
                (
                    "Asistencia perdida para {player_short}",
                    "Pasar a {teammate_short} valía {alt_value} goles esperados frente a {shot_xg} xG del tiro. "
                    "{player_short} hoy: {p_xg} xG en {p_shots|tiro|tiros}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} eligió el tiro",
                    "{teammate_short} estaba libre a {pass_distance_m} m, sin rival a menos de {nearest_marker_m} m. "
                    "El pase era {times_better} veces mejor que el tiro.",
                )
            ],
        },
        "unfound_run": {
            "casual": [
                (
                    "Nadie vio el desmarque de {runner_short}",
                    "{runner} se escapó a la espalda de la defensa, pero {player_short} nunca dio el pase. "
                    "Podía ser una ocasión del {projected_xg_pct}%.",
                )
            ],
            "tactical": [
                (
                    "Desmarque sin premio: {runner_short} rompe la línea",
                    "{runner_short} ganó {clear_of_line_m} m a la última línea y el pase al hueco estaba "
                    "disponible en el minuto {pass_on_clock}. Ocasión proyectada: {projected_xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{runner_short} se queda sin {projected_xg} xG",
                    "El pase al hueco de {player_short} nunca llegó. Ese desmarque valía {projected_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{runner_short} ataca la espalda",
                    "{runner_short} se escapó {clear_of_line_m} m de la defensa, pero {player_short} se guardó el balón.",
                )
            ],
        },
        "momentum_swing": {
            "casual": [
                (
                    "{team} toma el control",
                    "El partido se inclina hacia {team}: el impulso cambió {momentum_change} puntos "
                    "en {window_min} minutos.",
                )
            ],
            "tactical": [
                (
                    "Cambio de dinámica a favor de {team}",
                    "El impulso se movió {momentum_change} puntos en {window_min} minutos. "
                    "{team} tiene ahora un {team_field_tilt_pct}% de dominio territorial.",
                )
            ],
            "fantasy": [
                (
                    "{team} manda: atentos a sus atacantes",
                    "{team} suma {team_shots_5|tiro|tiros} en los últimos {window_min} minutos. "
                    "Su xG del partido ya es {team_xg_total}.",
                )
            ],
        },
        "pressure_spell": {
            "casual": [
                (
                    "{team} aprieta sin descanso",
                    "{team} lleva {spell_min} minutos encerrando a {opp}. Algo puede romperse.",
                )
            ],
            "tactical": [
                (
                    "Presión sostenida: {team} en {pressure_index}",
                    "Índice de presión {pressure_index} durante {spell_min} minutos con un {team_field_tilt_pct}% "
                    "de dominio territorial. {opp} no puede salir con calma.",
                )
            ],
            "fantasy": [
                (
                    "{team} presiona arriba",
                    "{team} suma {team_shots_5|tiro|tiros} en los últimos {window_min} minutos "
                    "y {team_xg_total} xG en el partido. Sus atacantes están llegando.",
                )
            ],
        },
        "speed_burst": {
            "casual": [
                (
                    "{player_short} vuela a {speed_kmh} km/h",
                    "{player} mete la directa a {speed_kmh} km/h. Lleva {sprints|esprint|esprints}.",
                )
            ],
            "tactical": [
                (
                    "Esprint: {player_short} a {speed_kmh} km/h",
                    "{player_short} supera la línea de esprint de {speed_threshold_kmh} km/h. "
                    "Esprints hoy: {sprints}.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} en movimiento",
                    "{player_short} hasta ahora: {p_shots|tiro|tiros}, {p_xg} xG y "
                    "{p_key_passes|pase clave|pases clave}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} a toda velocidad",
                    "{speed_kmh} km/h; su punta de hoy es {top_speed_kmh} km/h. Esprints: {sprints}.",
                )
            ],
        },
        "rocket_shot": {
            "casual": [
                (
                    "¡Cañonazo de {player_short}!",
                    "{player} le pega a {shot_speed_kmh} km/h y {outcome_phrase}.",
                )
            ],
            "tactical": [
                (
                    "Disparo a {shot_speed_kmh} km/h de {player_short}",
                    "Balón a {shot_speed_kmh} km/h desde {distance_m} m en una ocasión de {xg} xG. "
                    "A esa velocidad el portero apenas tiene tiempo de reaccionar.",
                )
            ],
            "fantasy": [
                ("Tiro de {player_short}: {xg} xG", "{player_short} suma {p_xg} xG en {p_shots|tiro|tiros}.")
            ],
            "player_spotlight": [
                (
                    "{player_short} prueba desde lejos",
                    "{shot_speed_kmh} km/h desde {distance_m} m, y {outcome_phrase}.",
                )
            ],
        },
        "distance_milestone": {
            "casual": [
                (
                    "{player_short} supera {milestone_km} km (est.)",
                    "{player} ya ha recorrido {milestone_km} km, según nuestra estimación. No para de correr.",
                )
            ],
            "tactical": [
                (
                    "Despliegue: {player_short}, {milestone_km} km (est.)",
                    "{player_short} supera {milestone_km} km estimados con {sprints|esprint|esprints}. "
                    "Velocidad punta: {top_speed_kmh} km/h.",
                )
            ],
            "fantasy": [
                (
                    "{player_short}: {milestone_km} km (estimación)",
                    "Mucho trabajo (distancia estimada); en ataque suma {p_shots|tiro|tiros}, {p_xg} xG y "
                    "{p_key_passes|pase clave|pases clave}.",
                )
            ],
            "player_spotlight": [
                (
                    "{milestone_km} km (est.) para {player_short}",
                    "{player_short} llega a {milestone_km} km (estimación), con {sprints|esprint|esprints} "
                    "y una punta de {top_speed_kmh} km/h.",
                )
            ],
        },
        "hard_pass": {
            "casual": [
                (
                    "¡Qué pase de {player_short}!",
                    "{player} encuentra a {receiver_short} con un pase de {pass_distance_m} m. "
                    "Su dificultad: {pass_difficulty} sobre {difficulty_scale}.",
                )
            ],
            "tactical": [
                (
                    "PDR {pass_difficulty}: {player_short} encuentra a {receiver_short}",
                    "Pase de {pass_distance_m} m con dificultad {pass_difficulty}, que suma {xt_delta} xT.",
                ),
                (
                    "PDR {pass_difficulty}: {player_short} encuentra a {receiver_short}",
                    "Pase de {pass_distance_m} m con dificultad {pass_difficulty}, entre líneas.",
                ),
            ],
            "fantasy": [
                (
                    "{player_short} genera ocasiones",
                    "{player_short} hoy: {p_key_passes|pase clave|pases clave} y {p_xa} xA.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} filtra el pase",
                    "Pase de {pass_distance_m} m a {receiver_short}, dificultad {pass_difficulty} "
                    "sobre {difficulty_scale}.",
                )
            ],
        },
        "key_tackle": {
            "casual": [
                (
                    "Gran entrada de {player_short}",
                    "{player} le roba el balón a {victim_short} a {own_goal_distance_m} m de su portería. "
                    "{team} respira.",
                ),
                (
                    "Gran entrada de {player_short}",
                    "{player} recupera el balón a {own_goal_distance_m} m de su portería. {team} respira.",
                ),
            ],
            "tactical": [
                (
                    "Entrada clave: {player_short}",
                    "Recuperación en el tercio defensivo, a {own_goal_distance_m} m, donde {opp} acumulaba "
                    "{xt_stopped} xT. {player_short} suma {p_tackles_won|entrada ganada|entradas ganadas}.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} corta el ataque",
                    "Trabajo defensivo de {player_short}: {p_tackles_won|entrada ganada|entradas ganadas} "
                    "hasta ahora. Esta, a {own_goal_distance_m} m de su portería.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} recupera el balón",
                    "Una entrada a {own_goal_distance_m} m de su portería que anula una amenaza de "
                    "{xt_stopped} xT. Entradas ganadas hoy: {p_tackles_won}.",
                )
            ],
        },
        "milestone.kick_off": {
            "casual": [
                (
                    "Arranca: {home} contra {away}",
                    "Ya rueda el balón entre {home} y {away}. Te avisaremos de los momentos clave.",
                )
            ],
            "tactical": [
                (
                    "Arranca: {home} contra {away}",
                    "Ya rueda el balón entre {home} y {away}. Atentos a la presión y al impulso desde el inicio.",
                )
            ],
            "fantasy": [
                (
                    "Arranca: {home} contra {away}",
                    "Ya rueda el balón entre {home} y {away}. Goles, asistencias, xG, xA, tiros y pases clave en directo.",
                )
            ],
        },
        "milestone.half_time": {
            "casual": [
                (
                    "Descanso: {home} {score_home}-{score_away} {away}",
                    "Llega el descanso. Tiros: {shots_home} de {home} y {shots_away} de {away}.",
                )
            ],
            "tactical": [
                (
                    "Descanso: {home} {score_home}-{score_away} {away}",
                    "Goles esperados {xg_home} a {xg_away}; tiros {shots_home} a {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "Descanso: {home} {score_home}-{score_away} {away}",
                    "xG al descanso: {home} {xg_home}, {away} {xg_away}.",
                )
            ],
        },
        "milestone.full_time": {
            "casual": [
                (
                    "Final: {home} {score_home}-{score_away} {away}",
                    "Se acabó. {home} hizo {shots_home|tiro|tiros} y {away}, {shots_away|tiro|tiros}.",
                )
            ],
            "tactical": [
                (
                    "Final: {home} {score_home}-{score_away} {away}",
                    "Goles esperados finales {xg_home} a {xg_away}; tiros {shots_home} a {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "Final: {home} {score_home}-{score_away} {away}",
                    "xG final: {home} {xg_home}, {away} {xg_away}. Tiros: {shots_home} contra {shots_away}.",
                )
            ],
        },
        "milestone.player": {
            "casual": [
                (
                    "{player_short} cumple {appearance_n} partidos",
                    "{player} llega hoy a {appearance_n} partidos con {team}.",
                ),
                ("Día especial para {player_short}", "{player} celebra un hito con {team} hoy."),
            ],
            "tactical": [
                (
                    "{player_short}: {appearance_n} partidos con el club",
                    "{player} llega a {appearance_n} partidos con {team}.",
                ),
                ("Día especial para {player_short}", "{player} celebra un hito con {team} hoy."),
            ],
            "fantasy": [
                (
                    "{player_short}: {appearance_n} partidos con el club",
                    "{player_short} hoy: {p_goals|gol|goles}, {p_assists|asistencia|asistencias}, {p_xg} xG.",
                ),
                (
                    "Día especial para {player_short}",
                    "{player_short} hoy: {p_goals|gol|goles}, {p_assists|asistencia|asistencias}, {p_xg} xG.",
                ),
            ],
        },
    },
    "why": {
        "goal": ["El marcador queda {home} {score_home}-{score_away} {away}, tras una ocasión de {xg} xG."],
        "card": ["{player_short} {card_action}, así que {team} debe ajustar su forma de defender."],
        "big_chance": [
            "Una ocasión de {xg} xG es una oportunidad clara: {team} está llegando a zonas de peligro."
        ],
        "better_option": [
            "El pase a {teammate_short} valía {alt_value} goles esperados frente a {shot_xg} del tiro: "
            "{times_better} veces más."
        ],
        "unfound_run": [
            "{runner_short} estaba {clear_of_line_m} m por detrás de la última línea en el minuto {pass_on_clock}; "
            "el pase habría creado una ocasión de {projected_xg} xG."
        ],
        "momentum_swing": [
            "El impulso se movió {momentum_change} puntos en {window_min} minutos: el control ha cambiado de manos."
        ],
        "pressure_spell": [
            "Un índice de presión de {pressure_index} durante {spell_min} minutos impide a {opp} salir con calma."
        ],
        "speed_burst": [
            "{speed_kmh} km/h supera la línea de esprint de {speed_threshold_kmh} km/h; la velocidad estira a la defensa."
        ],
        "rocket_shot": ["A {shot_speed_kmh} km/h el portero apenas tiene tiempo de reaccionar."],
        "distance_milestone": [
            "Un recorrido estimado de {milestone_km} km muestra el trabajo detrás del bloque de {team}."
        ],
        "hard_pass": [
            "Una dificultad de {pass_difficulty} sobre {difficulty_scale} es un pase que pocos completan."
        ],
        "key_tackle": [
            "Ganada a {own_goal_distance_m} m de la portería, la entrada le quita a {opp} una amenaza de {xt_stopped} xT."
        ],
        "milestone.kick_off": ["Comienza el partido."],
        "milestone.half_time": ["Al descanso, los goles esperados van {xg_home} a {xg_away}."],
        "milestone.full_time": ["Goles esperados finales: {xg_home} a {xg_away}."],
        "milestone.player": [
            "{player_short} alcanza {appearance_n} partidos con el club.",
            "Un día especial para {player_short}.",
        ],
    },
    "metric": {
        "pressure": [
            (
                "Índice de presión: {team} {pressure_index}",
                "El índice de presión de {team} cambió {change} puntos hasta {pressure_index}.",
            )
        ],
        "xg": [("xG: {subject} {xg}", "{subject} llega a {xg} xG, {change} más.")],
        "pass_difficulty": [
            (
                "Dificultad de pase {pass_difficulty}",
                "{player_short} completa un pase de dificultad {pass_difficulty} sobre {difficulty_scale}.",
            )
        ],
        "top_speed": [
            (
                "Nueva punta: {top_speed_kmh} km/h",
                "{subject} marca una nueva velocidad punta de {top_speed_kmh} km/h.",
            )
        ],
        "momentum": [("Impulso: manda {team}", "El impulso se movió {change} puntos a favor de {team}.")],
    },
    "recap": {
        "title_full": "Final: {home} {score_home}-{score_away} {away}",
        "title_live": "El partido hasta ahora: {home} {score_home}-{score_away} {away}",
        "headline_win": "{winner} vence {score_w}-{score_l} a {loser}",
        "headline_draw": "{home} y {away} empatan {score_home}-{score_away}",
        "headline_lead": "{winner} gana {score_w}-{score_l} a {loser}",
        "headline_level": "Empate a {score_home}",
        "p1_full": "{home} y {away} terminaron {score_home}-{score_away}. Los goles esperados fueron {xg_home} "
        "a {xg_away}, con {shots_home} y {shots_away} tiros.",
        "p1_live": "{home} {score_home}-{score_away} {away} en el minuto {generated_at}. Goles esperados hasta ahora: "
        "{xg_home} a {xg_away}, con {shots_home} y {shots_away} tiros.",
        "goals": "Los goles: {goals_line}.",
        "no_goals": "Aún no hay goles, pero sí {n_big_chances|ocasión clara|ocasiones claras}.",
        "turning": "Señalamos {n_better_options|tiro en el que el pase era mejor|tiros en los que el pase era mejor} "
        "y {n_unfound_runs|desmarque sin premio|desmarques sin premio}.",
        "potm": {
            "casual": "Jugador del partido: {potm}, de {potm_team}, con {potm_goals|gol|goles} "
            "y {potm_assists|asistencia|asistencias}.",
            "tactical": "Lo marcaron {n_pressure_spells|fase de presión|fases de presión} y "
            "{n_momentum_swings|cambio de impulso|cambios de impulso}. Jugador del partido, {potm}: "
            "{potm_key_passes|pase clave|pases clave} y {potm_tackles|entrada ganada|entradas ganadas}.",
            "fantasy": "Jugador del partido, {potm}: {potm_goals|gol|goles}, {potm_assists|asistencia|asistencias}, "
            "{potm_xg} xG, {potm_xa} xA y {potm_key_passes|pase clave|pases clave}.",
        },
        "focus": "{focus}: {focus_passes_completed} de {focus_passes} pases completados, {focus_distance_km} km "
        "recorridos y una punta de {focus_top_speed_kmh} km/h.",
    },
}

# Vocabulario futbolero que usan las plantillas como `{g_<término>}` (docs/LANGUAGES.md).
PACK["glossary"] = {
    "box": "área",
    "keeper": "portero",
    "back_line": "zaga",
    "equaliser": "gol del empate",
    "comeback": "remontada",
    "let_off": "susto",
    "rocket": "zapatazo",
}

_SCORE = "{home} {score_home}-{score_away} {away}"

# Corazón de club (crew/club_heart.py): los mismos datos, contados desde el lado del aficionado.
PACK["heart"] = {
    "goal_for": {
        "casual": [
            (
                "¡GOL de tu equipo! Marca {player_short}",
                "{player} bate al {g_keeper} desde {distance_m} m. " + _SCORE + ".",
            ),
        ],
        "tactical": [
            (
                "{player_short} convierte {xg} xG para tu equipo",
                "Desde {distance_m} m, en {zone}. " + _SCORE + " en el {match_clock}.",
            ),
        ],
        "fantasy": [
            (
                "Gol de {player_short} para tu equipo",
                "{player_short} hoy: {p_goals|gol|goles} y {p_xg} xG en {p_shots|tiro|tiros}. Esta ocasión valía {xg} xG.",
            ),
        ],
    },
    "goal_for_level": {
        "casual": [
            (
                "¡Empate! {player_short} iguala para tu equipo",
                "{player} marca el {g_equaliser} en el {match_clock}. "
                + _SCORE
                + ": la {g_comeback} está en marcha.",
            ),
        ],
        "tactical": [
            (
                "{player_short} empata con {xg} xG",
                "Remate desde {distance_m} m, en {zone}. " + _SCORE + " en el {match_clock}.",
            ),
        ],
    },
    "goal_for_pull_back": {
        "casual": [
            (
                "¡{player_short} recorta distancias!",
                _SCORE + " en el {match_clock}. Tu equipo sigue vivo y la {g_comeback} empieza aquí.",
            ),
        ],
        "tactical": [
            (
                "Tu equipo recorta: {player_short}, {xg} xG",
                "Remate desde {distance_m} m, en {zone}. " + _SCORE + " en el {match_clock}.",
            ),
        ],
    },
    "goal_for_lead": {
        "casual": [
            (
                "¡GOL! {player_short} adelanta a tu equipo",
                "{player} marca en el {match_clock}. " + _SCORE + ".",
            ),
        ],
        "tactical": [
            (
                "Ventaja para tu equipo: {player_short}, {xg} xG",
                "Remate desde {distance_m} m, en {zone}, en el {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "goal_against": {
        "casual": [
            (
                "{player_short} marca contra tu equipo",
                _SCORE + " en el {match_clock}. Aún hay tiempo para reaccionar.",
            ),
        ],
        "tactical": [
            (
                "Gol encajado: {player_short}, {xg} xG",
                "Remate desde {distance_m} m, en {zone}. "
                + _SCORE
                + " en el {match_clock}: hay tiempo para reaccionar.",
            ),
        ],
        "fantasy": [
            (
                "{player_short} marca contra tu equipo",
                "{player_short} hoy: {p_goals|gol|goles} y {p_xg} xG en {p_shots|tiro|tiros}. Esta ocasión valía {xg} xG.",
            ),
        ],
    },
    "goal_against_level": {
        "casual": [
            (
                "Empate: {player_short} iguala el partido",
                _SCORE + " en el {match_clock}. Tu equipo tiene que rehacerse y volver a empezar.",
            ),
        ],
        "tactical": [
            (
                "{g_equaliser} rival: {player_short}, {xg} xG",
                "Remate desde {distance_m} m, en {zone}. " + _SCORE + " en el {match_clock}.",
            ),
        ],
    },
    "goal_against_lead_cut": {
        "casual": [
            (
                "{player_short} recorta la ventaja de tu equipo",
                _SCORE + " en el {match_clock}. Tu equipo sigue por delante: calma.",
            ),
        ],
        "tactical": [
            (
                "Ventaja recortada: {player_short}, {xg} xG",
                "Remate desde {distance_m} m, en {zone}. Sigue por delante en el {match_clock}: "
                + _SCORE
                + ".",
            ),
        ],
    },
    "goal_against_late": {
        "casual": [
            (
                "Golpe tardío: marca {player_short}",
                _SCORE + " en el {match_clock}. Duro para tu equipo a estas alturas.",
            ),
        ],
        "tactical": [
            (
                "Golpe tardío: {player_short}, {xg} xG",
                "Remate desde {distance_m} m, en {zone}, en el {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "card_own": {
        "casual": [
            (
                "{card_name_cap} para {player_short}",
                "{player} {card_action} en el {match_clock}. Tu equipo necesita cabeza fría.",
            ),
        ],
    },
    "card_rival": {
        "casual": [
            (
                "{card_name_cap} para {player_short}",
                "{player} {card_action} en el {match_clock}. Tu equipo puede aprovechar la ventaja.",
            ),
        ],
    },
    "let_off": {
        "casual": [
            (
                "¡Qué {g_let_off} para tu equipo!",
                "{player} tuvo una ocasión clara para {team} a {distance_m} m, pero {outcome_phrase}. "
                "Ocasiones así entran alrededor del {xg_pct}% de las veces.",
            ),
        ],
        "tactical": [
            (
                "Peligro: ocasión de {xg} xG para {team}",
                "{player_short} remata desde {distance_m} m, en {zone}, pero {outcome_phrase}. "
                "La {g_back_line} de tu equipo quedó abierta.",
            ),
        ],
    },
    "let_off_shot": {
        "casual": [
            (
                "{g_let_off}: el {g_rocket} de {player_short}",
                "{player} le pega a {shot_speed_kmh} km/h desde {distance_m} m, y {outcome_phrase}. Tu equipo se salva.",
            ),
        ],
    },
    "let_off_choice": {
        "casual": [
            (
                "{g_let_off}: {player_short} prefirió tirar",
                "{teammate_short} estaba solo y el pase valía {times_better} veces más que el tiro. Tu equipo se salvó.",
            ),
        ],
        "tactical": [
            (
                "Tu equipo se salva: {player_short} ignoró a {teammate_short}",
                "Tiro de {shot_xg} xG; el pase de {pass_distance_m} m tenía un {pass_success_pct}% de éxito. "
                "Tu equipo se salvó.",
            ),
        ],
    },
    "let_off_run": {
        "casual": [
            (
                "{g_let_off}: nadie vio el desmarque de {runner_short}",
                "{runner} se metió a la espalda de la {g_back_line} de tu equipo, pero {player_short} nunca dio el pase. "
                "Podía ser una ocasión del {projected_xg_pct}%.",
            ),
        ],
        "tactical": [
            (
                "{g_let_off}: {runner_short}, {clear_of_line_m} m en ventaja",
                "{runner_short} superó a la {g_back_line} de tu equipo en el {pass_on_clock}; el pase habría dado "
                "una ocasión de {projected_xg} xG. {player_short} no lo vio.",
            ),
        ],
    },
    "lesson_choice": {
        "casual": [
            (
                "La próxima vez, busca a {teammate_short}",
                "{player_short} tiró, pero el pase a {teammate_short} valía {times_better} veces más. "
                "Algo que tu equipo puede mejorar.",
            ),
        ],
        "tactical": [
            (
                "Lección: el pase a {teammate_short}",
                "Tiro de {shot_xg} xG; el pase de {pass_distance_m} m tenía un {pass_success_pct}% de éxito y "
                "{alt_xg} xG detrás. El mejor balón estaba ahí.",
            ),
        ],
    },
    "lesson_run": {
        "casual": [
            (
                "El desmarque de {runner_short} merecía el balón",
                "{runner} estaba {clear_of_line_m} m por delante de la {g_back_line}; la próxima vez {player_short} "
                "puede encontrarlo. Podía ser una ocasión del {projected_xg_pct}%.",
            ),
        ],
        "tactical": [
            (
                "Desmarque sin premio: {runner_short}, {clear_of_line_m} m",
                "El pase al hueco estaba en el {pass_on_clock}: una ocasión de {projected_xg} xG. "
                "La próxima vez {player_short} puede encontrarlo.",
            ),
        ],
    },
    "pressure_for": {
        "casual": [
            (
                "Tu equipo aprieta",
                "Tu equipo lleva {spell_min|minuto|minutos} encerrando a {opp}. Que siga así.",
            ),
        ],
    },
    "hold_firm": {
        "casual": [
            (
                "Aguanta: {team} aprieta",
                "{team} lleva {spell_min|minuto|minutos} encerrando a tu equipo. Toca resistir y alejar el balón del {g_box}.",
            ),
        ],
        "tactical": [
            (
                "Bajo presión: {team} en {pressure_index}",
                "Índice de presión {pressure_index} durante {spell_min|minuto|minutos}, con un {team_field_tilt_pct}% "
                "de dominio territorial contra tu equipo.",
            ),
        ],
    },
    "momentum_against": {
        "casual": [
            (
                "Aviso: {team} toma el control",
                "El impulso se movió {momentum_change} puntos hacia {team} en {window_min} minutos. "
                "Tu equipo necesita reaccionar.",
            ),
        ],
        "tactical": [
            (
                "Cambio de impulso contra tu equipo",
                "El impulso se movió {momentum_change} puntos en {window_min} minutos; {team} tiene un "
                "{team_field_tilt_pct}% de dominio territorial.",
            ),
        ],
    },
    "full_time_won": {"casual": [("Final: ¡gana tu equipo!", _SCORE + ". Un resultado para disfrutar.")]},
    "full_time_lost": {
        "casual": [("Final: derrota de tu equipo", _SCORE + ". Toca levantarse y volver a empezar.")]
    },
    "full_time_drawn": {"casual": [("Final: reparto de puntos", _SCORE + ". Empate en el marcador.")]},
}
PACK["metric"]["momentum_against"] = [
    ("Aviso: impulso para {team}", "El impulso se movió {change} puntos hacia {team}, lejos de tu equipo."),
]
PACK["heart"]["attack_stopped"] = {
    "casual": [
        (
            "{player_short} corta el ataque de tu equipo",
            "{player} recuperó el balón a {own_goal_distance_m} m de su portería. Tu equipo vuelve a empezar.",
        ),
    ],
    "tactical": [
        (
            "Ataque cortado: {xt_stopped} xT anulados",
            "{player_short} la ganó en su tercio, a {own_goal_distance_m} m. Tu equipo debe rehacer la jugada.",
        ),
    ],
}
