"""عبارات الاستوديو بالعربية. نفس صيغة en.py. الأرقام تُكتب بالأرقام الغربية،
وأسماء الأندية واللاعبين تبقى كما هي."""

PACK = {
    "your_team": "فريقك",
    "labels": {
        "xg": "جودة الفرصة (xG)",
        "distance_m": "المسافة إلى المرمى",
        "shot_speed_kmh": "سرعة التسديدة",
        "score_home": "أهداف أصحاب الأرض",
        "score_away": "أهداف الضيوف",
        "card": "البطاقة",
        "shot_xg": "xG التسديدة",
        "alt_xg": "xG الزميل",
        "pass_success_pct": "احتمال نجاح التمريرة",
        "alt_value": "القيمة المتوقعة للتمريرة",
        "times_better": "التمريرة مقابل التسديد",
        "pass_distance_m": "طول التمريرة",
        "nearest_marker_m": "أقرب مدافع",
        "clear_of_line_m": "التقدم على خط الدفاع",
        "projected_xg": "xG المتوقع للفرصة",
        "pass_on_clock": "كانت التمريرة متاحة عند",
        "one_on_one": "انفراد",
        "momentum_change": "تغيّر الزخم",
        "window_min": "الفترة",
        "team_field_tilt_pct": "السيطرة على الملعب",
        "team_shots_5": "التسديدات (آخر 5 دقائق)",
        "team_xg_total": "xG الفريق",
        "pressure_index": "مؤشر الضغط",
        "spell_min": "مدة الفترة",
        "team_box_entries_5": "دخول منطقة الجزاء (آخر 5 دقائق)",
        "speed_kmh": "السرعة",
        "top_speed_kmh": "أقصى سرعة",
        "sprints": "الانطلاقات السريعة",
        "milestone_km": "المسافة (تقديرية)",
        "pass_difficulty": "صعوبة التمريرة",
        "xt_delta": "التهديد المضاف (xT)",
        "xg_home": "xG أصحاب الأرض",
        "xg_away": "xG الضيوف",
        "shots_home": "تسديدات أصحاب الأرض",
        "shots_away": "تسديدات الضيوف",
        "appearance_n": "المشاركات مع النادي",
        "ruled_out_clock": "هدف ملغى (سُجل عند)",
        "xt_stopped": "الخطر الذي أُوقف (xT)",
        "own_goal_distance_m": "المسافة عن مرماه",
        "p_tackles_won": "التدخلات الناجحة",
        "last_ditch": "تدخل أخير (داخل منطقته)",
        "distance_km": "المسافة حتى الآن (تقدير التتبع)",
        "sprint_m": "طول الانطلاقة",
    },
    "zones": {
        "Penalty Box": "منطقة الجزاء",
        "Attacking Third": "الثلث الأخير",
        "Middle Third": "وسط الملعب",
        "Defensive Third": "الثلث الدفاعي",
        "": "اللعب المفتوح",
    },
    "outcomes": {
        "saved": "تصدى لها الحارس",
        "blocked": "صدها أحد المدافعين",
        "off_target": "ذهبت خارج المرمى",
        "goal": "سكنت الشباك",
        "": "لم تثمر",
    },
    "card_name": {"yellow": "بطاقة صفراء", "red": "بطاقة حمراء"},
    "card_name_cap": {"yellow": "بطاقة صفراء", "red": "بطاقة حمراء"},
    "card_action": {"yellow": "ينال إنذارًا", "red": "يُطرد"},
    "var_reason": {"offside": "التسلل", "handball": "لمسة اليد", "foul": "خطأ"},
    "fav_goal": {
        "for": "هدف لفريقك! {player_short} يسجل",
        "against": "{player_short} يسجل في مرمى فريقك",
    },
    "narr": {
        "goal": {
            "casual": [
                (
                    "هدف! {player_short} يسجل لـ{team}",
                    "{player} يضع الكرة في الشباك بعد تمريرة من {assist}. النتيجة: {home} {score_home}-{score_away} {away}.",
                ),
                (
                    "هدف! {player_short} يسجل لـ{team}",
                    "{player} يضع الكرة في الشباك. النتيجة: {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "tactical": [
                (
                    "{player_short} يحوّل فرصة بقيمة {xg} xG",
                    "{assist_short} يجد {player_short} على بعد {distance_m} م في {zone}. "
                    "النتيجة: {home} {score_home}-{score_away} {away}.",
                ),
                (
                    "{player_short} يحوّل فرصة بقيمة {xg} xG",
                    "{player_short} يسجل من {distance_m} م في {zone}. النتيجة: {home} {score_home}-{score_away} {away}.",
                ),
            ],
            "fantasy": [
                (
                    "هدف {player_short} وصناعة {assist_short}",
                    "{player_short} اليوم: الأهداف {p_goals}، التسديدات {p_shots}، و{p_xg} xG. "
                    "قيمة هذه الفرصة {xg} xG.",
                ),
                (
                    "هدف لـ{player_short}",
                    "{player_short} اليوم: الأهداف {p_goals}، التسديدات {p_shots}، و{p_xg} xG. "
                    "قيمة هذه الفرصة {xg} xG.",
                ),
            ],
            "player_spotlight": [
                (
                    "{player_short} يسجل!",
                    "{player} يهزم الحارس من {distance_m} م. النتيجة: {home} {score_home}-{score_away} {away}.",
                )
            ],
        },
        "card": {
            "casual": [
                ("{card_name_cap} لـ{player_short}", "{player} {card_action}. على {team} الحذر الآن.")
            ],
            "tactical": [
                (
                    "{card_name_cap}: {player_short}",
                    "{player} {card_action}. سيضطر {team} للدفاع بحذر أكبر في هذا الرواق.",
                )
            ],
            "fantasy": [
                (
                    "{card_name_cap} لـ{player_short}",
                    "{player_short} {card_action}. أرقامه اليوم: الأهداف {p_goals}، الصناعة {p_assists}، و{p_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{card_name_cap} لـ{player_short}",
                    "{player} {card_action}. كل التحام من الآن فصاعدًا مخاطرة.",
                )
            ],
        },
        "big_chance": {
            "casual": [
                (
                    "فرصة كبيرة لـ{player_short}!",
                    "{player} وجد نفسه أمام المرمى على بعد {distance_m} م، لكن الكرة {outcome_phrase}. "
                    "فرص كهذه تدخل الشباك في نحو {xg_pct}% من المرات.",
                )
            ],
            "tactical": [
                (
                    "فرصة بقيمة {xg} xG لـ{team}",
                    "{player_short} يسدد من {distance_m} م في {zone}، لكن الكرة {outcome_phrase}. "
                    "قيمة التسديدة: {xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{player_short}: فرصة بقيمة {xg} xG",
                    "رصيد {player_short} الآن {p_xg} xG من {p_shots} تسديدات. هذه لم تدخل.",
                )
            ],
            "player_spotlight": [
                (
                    "فرصة كبيرة لـ{player_short}",
                    "{player_short} يجد المساحة على بعد {distance_m} م، لكن الكرة {outcome_phrase}. "
                    "اليوم: التسديدات {p_shots}، و{p_xg} xG.",
                )
            ],
        },
        "better_option": {
            "casual": [
                (
                    "هل كان على {player_short} أن يمرر؟",
                    "{player_short} سدد، لكن {teammate_short} كان حرًا تمامًا. "
                    "التمريرة كانت تساوي {times_better} أضعاف التسديدة.",
                )
            ],
            "tactical": [
                (
                    "اختيار خاطئ: {player_short} تجاهل {teammate_short}",
                    "التسديدة بقيمة {shot_xg} xG، أما التمريرة لمسافة {pass_distance_m} م فنسبة نجاحها "
                    "{pass_success_pct}% وخلفها فرصة بقيمة {alt_xg} xG. القيمة المتوقعة {alt_value}، "
                    "أي {times_better} أضعاف التسديدة.",
                )
            ],
            "fantasy": [
                (
                    "صناعة ضائعة من {player_short}",
                    "التمرير إلى {teammate_short} كان يساوي {alt_value} هدف متوقع مقابل {shot_xg} xG للتسديدة. "
                    "{player_short} اليوم: {p_xg} xG من {p_shots} تسديدات.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} اختار التسديد",
                    "{teammate_short} كان حرًا على بعد {pass_distance_m} م ولا مدافع ضمن {nearest_marker_m} م. "
                    "التمريرة كانت أفضل بـ{times_better} أضعاف.",
                )
            ],
        },
        "unfound_run": {
            "casual": [
                (
                    "لم يرَ أحد انطلاقة {runner_short}",
                    "{runner} انطلق خلف الدفاع، لكن {player_short} لم يمرر الكرة أبدًا. "
                    "كانت ستصبح فرصة بنسبة {projected_xg_pct}%.",
                )
            ],
            "tactical": [
                (
                    "انطلاقة بلا تمريرة: {runner_short} خلف الخط",
                    "{runner_short} تقدم {clear_of_line_m} م خلف خط الدفاع الأخير، والتمريرة البينية كانت متاحة "
                    "عند الدقيقة {pass_on_clock}. الفرصة المتوقعة: {projected_xg} xG.",
                )
            ],
            "fantasy": [
                (
                    "{runner_short} يخسر فرصة بقيمة {projected_xg} xG",
                    "التمريرة البينية من {player_short} لم تأتِ. تلك الانطلاقة كانت تساوي {projected_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "{runner_short} ينطلق خلف الدفاع",
                    "{runner_short} ابتعد {clear_of_line_m} م عن المدافعين، لكن {player_short} احتفظ بالكرة.",
                )
            ],
        },
        "momentum_swing": {
            "casual": [
                (
                    "{team} يمسك بزمام المباراة",
                    "المباراة تميل لصالح {team}: الزخم تحرك {momentum_change} نقطة خلال {window_min} دقائق.",
                )
            ],
            "tactical": [
                (
                    "تحول الزخم لصالح {team}",
                    "الزخم تحرك {momentum_change} نقطة خلال {window_min} دقائق. "
                    "يسيطر {team} الآن على {team_field_tilt_pct}% من المناطق الهجومية.",
                )
            ],
            "fantasy": [
                (
                    "{team} في الأفضلية: راقبوا مهاجميه",
                    "التسديدات لـ{team} في آخر {window_min} دقائق: {team_shots_5}. "
                    "رصيده من xG في المباراة الآن {team_xg_total}.",
                )
            ],
        },
        "pressure_spell": {
            "casual": [
                (
                    "{team} يضغط بلا هوادة",
                    "{team} يحاصر {opp} منذ {spell_min} دقائق. قد ينكسر شيء ما قريبًا.",
                )
            ],
            "tactical": [
                (
                    "ضغط متواصل: {team} عند {pressure_index}",
                    "مؤشر الضغط {pressure_index} لمدة {spell_min} دقائق مع سيطرة إقليمية {team_field_tilt_pct}%. "
                    "لا يستطيع {opp} البناء بهدوء.",
                )
            ],
            "fantasy": [
                (
                    "{team} يضغط عاليًا",
                    "التسديدات لـ{team} في آخر {window_min} دقائق: {team_shots_5}، ورصيده {team_xg_total} xG "
                    "في المباراة. مهاجموه يصلون إلى المرمى.",
                )
            ],
        },
        "speed_burst": {
            "casual": [
                (
                    "{player_short} ينطلق بسرعة {speed_kmh} كم/س",
                    "{player} يبلغ سرعته القصوى عند {speed_kmh} كم/س. عدد انطلاقاته حتى الآن: {sprints}.",
                )
            ],
            "tactical": [
                (
                    "انطلاقة: {player_short} بسرعة {speed_kmh} كم/س",
                    "{player_short} يتجاوز حد الانطلاق البالغ {speed_threshold_kmh} كم/س. عدد الانطلاقات اليوم: {sprints}.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} في حركة دائمة",
                    "{player_short} حتى الآن: التسديدات {p_shots}، و{p_xg} xG، والتمريرات المفتاحية {p_key_passes}.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} بأقصى سرعة",
                    "{speed_kmh} كم/س، وأعلى سرعة له اليوم {top_speed_kmh} كم/س. الانطلاقات: {sprints}.",
                )
            ],
        },
        "rocket_shot": {
            "casual": [
                (
                    "صاروخ من {player_short}!",
                    "{player} يسدد بسرعة {shot_speed_kmh} كم/س، و{outcome_phrase}.",
                )
            ],
            "tactical": [
                (
                    "تسديدة بسرعة {shot_speed_kmh} كم/س من {player_short}",
                    "سرعة الكرة {shot_speed_kmh} كم/س من {distance_m} م في فرصة بقيمة {xg} xG. "
                    "بهذه السرعة لا يملك الحارس وقتًا للتصرف.",
                )
            ],
            "fantasy": [
                (
                    "تسديدة {player_short}: {xg} xG",
                    "رصيد {player_short} الآن {p_xg} xG من {p_shots} تسديدات.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} يطلق قذيفة",
                    "{shot_speed_kmh} كم/س من {distance_m} م، و{outcome_phrase}.",
                )
            ],
        },
        "distance_milestone": {
            "casual": [
                (
                    "{player_short} يتخطى {milestone_km} كم (تقديريًا)",
                    "{player} قطع نحو {milestone_km} كم حسب التقدير. لا يتوقف عن الركض.",
                )
            ],
            "tactical": [
                (
                    "جهد بدني: {player_short}، {milestone_km} كم تقديريًا",
                    "{player_short} يتخطى {milestone_km} كم تقديريًا، وعدد انطلاقاته {sprints}. "
                    "أعلى سرعة: {top_speed_kmh} كم/س.",
                )
            ],
            "fantasy": [
                (
                    "{player_short}: نحو {milestone_km} كم",
                    "ركض كثير (المسافة تقديرية)؛ وفي الهجوم: التسديدات {p_shots}، و{p_xg} xG، "
                    "والتمريرات المفتاحية {p_key_passes}.",
                )
            ],
            "player_spotlight": [
                (
                    "{milestone_km} كم تقديريًا لـ{player_short}",
                    "{player_short} يبلغ نحو {milestone_km} كم، مع {sprints} انطلاقات وأعلى سرعة "
                    "{top_speed_kmh} كم/س.",
                )
            ],
        },
        "hard_pass": {
            "casual": [
                (
                    "يا لها من تمريرة من {player_short}!",
                    "{player} يجد {receiver_short} بتمريرة لمسافة {pass_distance_m} م. "
                    "صعوبتها {pass_difficulty} من {difficulty_scale}.",
                )
            ],
            "tactical": [
                (
                    "PDR {pass_difficulty}: {player_short} يجد {receiver_short}",
                    "تمريرة لمسافة {pass_distance_m} م بصعوبة {pass_difficulty}، تضيف {xt_delta} xT.",
                ),
                (
                    "PDR {pass_difficulty}: {player_short} يجد {receiver_short}",
                    "تمريرة لمسافة {pass_distance_m} م بصعوبة {pass_difficulty}، تكسر الخطوط.",
                ),
            ],
            "fantasy": [
                (
                    "{player_short} يصنع الفرص",
                    "{player_short} اليوم: التمريرات المفتاحية {p_key_passes}، و{p_xa} xA.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} يمرر بين الخطوط",
                    "تمريرة لمسافة {pass_distance_m} م إلى {receiver_short}، صعوبتها {pass_difficulty} "
                    "من {difficulty_scale}.",
                )
            ],
        },
        "key_tackle": {
            "casual": [
                (
                    "تدخل حاسم من {player_short}",
                    "{player} يفتك الكرة من {victim_short} على بعد {own_goal_distance_m} م من مرماه. "
                    "{team} تتنفس الصعداء.",
                ),
                (
                    "تدخل حاسم من {player_short}",
                    "{player} يستعيد الكرة على بعد {own_goal_distance_m} م من مرماه. {team} تتنفس الصعداء.",
                ),
            ],
            "tactical": [
                (
                    "تدخل مفتاحي: {player_short}",
                    "استعادة في الثلث الدفاعي على بعد {own_goal_distance_m} م، حيث بلغ خطر {opp} "
                    "{xt_stopped} xT. التدخلات الناجحة لـ{player_short}: {p_tackles_won}.",
                )
            ],
            "fantasy": [
                (
                    "{player_short} يوقف الهجمة",
                    "عمل دفاعي من {player_short}: التدخلات الناجحة حتى الآن {p_tackles_won}. "
                    "هذا التدخل على بعد {own_goal_distance_m} م من مرماه.",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short} يستعيد الكرة",
                    "تدخل على بعد {own_goal_distance_m} م من مرماه ألغى خطرًا بقيمة {xt_stopped} xT. "
                    "التدخلات الناجحة اليوم: {p_tackles_won}.",
                )
            ],
        },
        "correction": {
            "casual": [
                (
                    "لا هدف! الـVAR يلغي هدف {player_short}",
                    "أُلغي هدف {player} عند {ruled_out_clock} بداعي {reason_phrase} بعد مراجعة الـVAR. تبقى النتيجة {home} {score_home}-{score_away} {away}.",
                )
            ],
            "tactical": [
                (
                    "الـVAR: إلغاء هدف {player_short}",
                    "أُلغي القرار بعد المراجعة بداعي {reason_phrase}. تعود النتيجة إلى {home} {score_home}-{score_away} {away}.",
                )
            ],
            "fantasy": [
                (
                    "هدف ملغى: {player_short}",
                    "الـVAR يلغي الهدف بداعي {reason_phrase}، والتسديدة تبقى محسوبة. {player_short} اليوم: الأهداف {p_goals}، التسديدات {p_shots}، و{p_xg} xG.",
                )
            ],
            "player_spotlight": [
                (
                    "لا هدف! الـVAR يلغي هدف {player_short}",
                    "أُلغي هدف {player} عند {ruled_out_clock} بداعي {reason_phrase} بعد مراجعة الـVAR. تبقى النتيجة {home} {score_home}-{score_away} {away}.",
                )
            ],
        },
        "milestone.kick_off": {
            "casual": [
                (
                    "صافرة البداية: {home} ضد {away}",
                    "انطلقت مباراة {home} و{away}. سننبهك إلى اللحظات المهمة.",
                )
            ],
            "tactical": [
                (
                    "صافرة البداية: {home} ضد {away}",
                    "انطلقت مباراة {home} و{away}. تابع مؤشري الضغط والزخم منذ الصافرة الأولى.",
                )
            ],
            "fantasy": [
                (
                    "صافرة البداية: {home} ضد {away}",
                    "انطلقت مباراة {home} و{away}. الأهداف والصناعة وxG وxA والتسديدات والتمريرات المفتاحية مباشرة.",
                )
            ],
        },
        "milestone.half_time": {
            "casual": [
                (
                    "نهاية الشوط الأول: {home} {score_home}-{score_away} {away}",
                    "استراحة ما بين الشوطين. التسديدات: {shots_home} لـ{home} و{shots_away} لـ{away}.",
                )
            ],
            "tactical": [
                (
                    "نهاية الشوط الأول: {home} {score_home}-{score_away} {away}",
                    "الأهداف المتوقعة {xg_home} مقابل {xg_away}، والتسديدات {shots_home} مقابل {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "نهاية الشوط الأول: {home} {score_home}-{score_away} {away}",
                    "xG بين الشوطين: {home} {xg_home}، {away} {xg_away}.",
                )
            ],
        },
        "milestone.full_time": {
            "casual": [
                (
                    "النهاية: {home} {score_home}-{score_away} {away}",
                    "انتهت المباراة. التسديدات: {shots_home} لـ{home} و{shots_away} لـ{away}.",
                )
            ],
            "tactical": [
                (
                    "النهاية: {home} {score_home}-{score_away} {away}",
                    "الأهداف المتوقعة النهائية {xg_home} مقابل {xg_away}، والتسديدات {shots_home} مقابل {shots_away}.",
                )
            ],
            "fantasy": [
                (
                    "النهاية: {home} {score_home}-{score_away} {away}",
                    "xG النهائي: {home} {xg_home}، {away} {xg_away}. التسديدات: {shots_home} مقابل {shots_away}.",
                )
            ],
        },
        "milestone.player": {
            "casual": [
                (
                    "المباراة رقم {appearance_n} لـ{player_short}",
                    "{player} يخوض اليوم مباراته رقم {appearance_n} مع {team}.",
                ),
                ("يوم مميز لـ{player_short}", "{player} يحتفل بإنجاز جديد مع {team} اليوم."),
            ],
            "tactical": [
                (
                    "{player_short}: المباراة رقم {appearance_n} مع النادي",
                    "{player} يبلغ {appearance_n} مباراة مع {team}.",
                ),
                ("يوم مميز لـ{player_short}", "{player} يحتفل بإنجاز جديد مع {team} اليوم."),
            ],
            "fantasy": [
                (
                    "{player_short}: المباراة رقم {appearance_n}",
                    "{player_short} اليوم: الأهداف {p_goals}، الصناعة {p_assists}، و{p_xg} xG.",
                ),
                (
                    "يوم مميز لـ{player_short}",
                    "{player_short} اليوم: الأهداف {p_goals}، الصناعة {p_assists}، و{p_xg} xG.",
                ),
            ],
        },
    },
    "why": {
        "goal": ["أصبحت النتيجة {home} {score_home}-{score_away} {away}، من فرصة بقيمة {xg} xG."],
        "card": ["{player_short} {card_action}، وعلى {team} تعديل طريقة الدفاع."],
        "big_chance": ["فرصة بقيمة {xg} xG فرصة واضحة: {team} يصل إلى المناطق الخطرة."],
        "better_option": [
            "التمريرة إلى {teammate_short} كانت تساوي {alt_value} هدف متوقع مقابل {shot_xg} للتسديدة، "
            "أي {times_better} أضعاف."
        ],
        "unfound_run": [
            "{runner_short} كان متقدمًا {clear_of_line_m} م خلف خط الدفاع عند الدقيقة {pass_on_clock}؛ "
            "والتمريرة كانت ستصنع فرصة بقيمة {projected_xg} xG."
        ],
        "momentum_swing": [
            "الزخم تحرك {momentum_change} نقطة خلال {window_min} دقائق: السيطرة انتقلت إلى الطرف الآخر."
        ],
        "pressure_spell": [
            "مؤشر ضغط عند {pressure_index} لمدة {spell_min} دقائق يمنع {opp} من البناء بهدوء."
        ],
        "speed_burst": [
            "{speed_kmh} كم/س تتجاوز حد الانطلاق البالغ {speed_threshold_kmh} كم/س؛ السرعة تمزق الدفاعات."
        ],
        "rocket_shot": ["بسرعة {shot_speed_kmh} كم/س لا يملك الحارس وقتًا للتصرف."],
        "distance_milestone": ["نحو {milestone_km} كم تقديريًا تظهر الجهد خلف تنظيم {team}."],
        "hard_pass": ["صعوبة {pass_difficulty} من {difficulty_scale} تعني تمريرة لا ينجح فيها إلا القليل."],
        "key_tackle": [
            "بتدخل على بعد {own_goal_distance_m} م من المرمى، أُلغي خطر بقيمة {xt_stopped} xT من {opp}."
        ],
        "correction": [
            "ألغى الـVAR هدف {ruled_out_clock} بداعي {reason_phrase}: تعود النتيجة إلى {home} {score_home}-{score_away} {away}."
        ],
        "milestone.kick_off": ["انطلقت المباراة."],
        "milestone.half_time": ["بين الشوطين، الأهداف المتوقعة {xg_home} مقابل {xg_away}."],
        "milestone.full_time": ["الأهداف المتوقعة النهائية: {xg_home} مقابل {xg_away}."],
        "milestone.player": [
            "{player_short} يبلغ {appearance_n} مباراة مع النادي.",
            "يوم مميز لـ{player_short}.",
        ],
    },
    "metric": {
        "pressure": [
            (
                "مؤشر الضغط: {team} {pressure_index}",
                "مؤشر الضغط لـ{team} تحرك {change} نقطة ليصل إلى {pressure_index}.",
            )
        ],
        "xg": [("تحديث xG: {subject} {xg}", "رصيد {subject} الآن {xg} xG، بزيادة {change}.")],
        "pass_difficulty": [
            (
                "صعوبة التمريرة {pass_difficulty}",
                "{player_short} ينجح في تمريرة صعوبتها {pass_difficulty} من {difficulty_scale}.",
            )
        ],
        "top_speed": [
            (
                "سرعة قصوى جديدة: {top_speed_kmh} كم/س",
                "{subject} يسجل سرعة قصوى جديدة تبلغ {top_speed_kmh} كم/س.",
            )
        ],
        "momentum": [("الزخم: {team} في الأفضلية", "الزخم تحرك {change} نقطة لصالح {team}.")],
    },
    "recap": {
        "title_full": "النهاية: {home} {score_home}-{score_away} {away}",
        "title_live": "المباراة حتى الآن: {home} {score_home}-{score_away} {away}",
        "headline_win": "{winner} يفوز على {loser} {score_w}-{score_l}",
        "headline_draw": "تعادل {home} و{away} {score_home}-{score_away}",
        "headline_lead": "{winner} يتقدم على {loser} {score_w}-{score_l}",
        "headline_level": "التعادل قائم {score_home}-{score_away}",
        "p1_full": "انتهت مباراة {home} و{away} بنتيجة {score_home}-{score_away}. الأهداف المتوقعة {xg_home} "
        "مقابل {xg_away}، من {shots_home} و{shots_away} تسديدة.",
        "p1_live": "{home} {score_home}-{score_away} {away} عند الدقيقة {generated_at}. الأهداف المتوقعة حتى الآن "
        "{xg_home} مقابل {xg_away}، من {shots_home} و{shots_away} تسديدة.",
        "goals": "الأهداف: {goals_line}.",
        "no_goals": "لا أهداف بعد، لكن عدد الفرص الكبيرة حتى الآن: {n_big_chances}.",
        "turning": "رصدنا تسديدات كان التمرير فيها أفضل: {n_better_options}، وانطلاقات بلا تمريرة: {n_unfound_runs}.",
        "potm": {
            "casual": "أفضل لاعب في المباراة: {potm} من {potm_team}، الأهداف {potm_goals} والصناعة {potm_assists}.",
            "tactical": "مراحل الضغط: {n_pressure_spells}، وتحولات الزخم: {n_momentum_swings}. أفضل لاعب {potm}: "
            "التمريرات المفتاحية {potm_key_passes}، والافتكاكات الناجحة {potm_tackles}.",
            "fantasy": "أفضل لاعب {potm}: الأهداف {potm_goals}، الصناعة {potm_assists}، {potm_xg} xG، "
            "{potm_xa} xA، والتمريرات المفتاحية {potm_key_passes}.",
        },
        "focus": "{focus}: {focus_passes_completed} تمريرة ناجحة من {focus_passes}، ونحو {focus_distance_km} كم "
        "تقديريًا، وأعلى سرعة {focus_top_speed_kmh} كم/س.",
    },
}

# مفردات كرة القدم التي تستخدمها القوالب بصيغة `{g_<المصطلح>}` (docs/LANGUAGES.md).
PACK["glossary"] = {
    "box": "منطقة الجزاء",
    "keeper": "الحارس",
    "back_line": "خط الدفاع",
    "equaliser": "هدف التعادل",
    "comeback": "العودة في النتيجة",
    "let_off": "نجاة",
    "rocket": "قذيفة",
}

_SCORE = "{home} {score_home}-{score_away} {away}"

# قلب النادي (crew/club_heart.py): الحقائق نفسها، تُروى من جهة المشجع.
PACK["heart"] = {
    "goal_for": {
        "casual": [
            (
                "هدف لفريقك! {player_short} يسجل",
                "{player} يهزم {g_keeper} من {distance_m} م. النتيجة: " + _SCORE + ".",
            ),
        ],
        "tactical": [
            (
                "{player_short} يحوّل {xg} xG لصالح فريقك",
                "تسديدة من {distance_m} م في {zone}. " + _SCORE + " عند {match_clock}.",
            ),
        ],
        "fantasy": [
            (
                "هدف {player_short} لفريقك",
                "{player_short} اليوم: الأهداف {p_goals}، والتسديدات {p_shots}، و{p_xg} xG. قيمة هذه الفرصة {xg} xG.",
            ),
        ],
    },
    "goal_for_level": {
        "casual": [
            (
                "تعادل! {player_short} يعيد فريقك",
                "{player} يسجل {g_equaliser} عند {match_clock}. " + _SCORE + "، و{g_comeback} بدأت.",
            ),
        ],
        "tactical": [
            (
                "{player_short} يعادل من فرصة {xg} xG",
                "تسديدة من {distance_m} م في {zone}. " + _SCORE + " عند {match_clock}.",
            ),
        ],
    },
    "goal_for_pull_back": {
        "casual": [
            (
                "{player_short} يقلص الفارق!",
                _SCORE + " عند {match_clock}. فريقك عاد إلى المباراة، و{g_comeback} تبدأ من هنا.",
            ),
        ],
        "tactical": [
            (
                "فريقك يقلص الفارق: {player_short}، {xg} xG",
                "تسديدة من {distance_m} م في {zone}. " + _SCORE + " عند {match_clock}.",
            ),
        ],
    },
    "goal_for_lead": {
        "casual": [
            ("هدف! {player_short} يضع فريقك في المقدمة", "{player} يسجل عند {match_clock}. " + _SCORE + "."),
        ],
        "tactical": [
            (
                "تقدم لفريقك: {player_short}، {xg} xG",
                "تسديدة من {distance_m} م في {zone} عند {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "goal_against": {
        "casual": [
            ("{player_short} يسجل في مرمى فريقك", _SCORE + " عند {match_clock}. ما زال لدى فريقك وقت للرد."),
        ],
        "tactical": [
            (
                "هدف في مرمى فريقك: {player_short}، {xg} xG",
                "تسديدة من {distance_m} م في {zone}. "
                + _SCORE
                + " عند {match_clock}، وما زال هناك وقت للرد.",
            ),
        ],
        "fantasy": [
            (
                "{player_short} يسجل في مرمى فريقك",
                "{player_short} اليوم: الأهداف {p_goals}، والتسديدات {p_shots}، و{p_xg} xG. قيمة هذه الفرصة {xg} xG.",
            ),
        ],
    },
    "goal_against_level": {
        "casual": [
            (
                "تعادل: {player_short} يدرك التعادل",
                _SCORE + " عند {match_clock}. على فريقك أن يستعيد تركيزه ويبدأ من جديد.",
            ),
        ],
        "tactical": [
            (
                "{g_equaliser} للمنافس: {player_short}، {xg} xG",
                "تسديدة من {distance_m} م في {zone}. " + _SCORE + " عند {match_clock}.",
            ),
        ],
    },
    "goal_against_lead_cut": {
        "casual": [
            (
                "{player_short} يقلص تقدم فريقك",
                _SCORE + " عند {match_clock}. فريقك ما زال متقدمًا، والهدوء مطلوب.",
            ),
        ],
        "tactical": [
            (
                "تقليص الفارق: {player_short}، {xg} xG",
                "تسديدة من {distance_m} م في {zone}. فريقك ما زال متقدمًا عند {match_clock}: " + _SCORE + ".",
            ),
        ],
    },
    "goal_against_late": {
        "casual": [
            (
                "ضربة متأخرة: {player_short} يسجل",
                _SCORE + " عند {match_clock}. ضربة قاسية لفريقك في هذا الوقت المتأخر.",
            ),
        ],
        "tactical": [
            (
                "ضربة متأخرة: {player_short}، {xg} xG",
                "تسديدة من {distance_m} م في {zone} عند {match_clock}. " + _SCORE + ".",
            ),
        ],
    },
    "card_own": {
        "casual": [
            (
                "{card_name_cap} لـ{player_short}",
                "{player} {card_action} عند {match_clock}. فريقك يحتاج إلى الهدوء الآن.",
            ),
        ],
    },
    "card_rival": {
        "casual": [
            (
                "{card_name_cap} لـ{player_short}",
                "{player} {card_action} عند {match_clock}. فرصة لفريقك لاستغلال الأفضلية.",
            ),
        ],
    },
    "let_off": {
        "casual": [
            (
                "{g_let_off} لفريقك!",
                "{player} أتيحت له فرصة واضحة لصالح {team} على بعد {distance_m} م، لكن {outcome_phrase}. "
                "فرص كهذه تدخل الشباك في نحو {xg_pct}% من المرات.",
            ),
        ],
        "tactical": [
            (
                "خطر: فرصة {xg} xG لصالح {team}",
                "{player_short} يسدد من {distance_m} م في {zone}، لكن {outcome_phrase}. انكشف {g_back_line} لدى فريقك.",
            ),
        ],
    },
    "let_off_shot": {
        "casual": [
            (
                "{g_let_off}: {g_rocket} من {player_short}",
                "{player} يسدد بسرعة {shot_speed_kmh} كم/س من {distance_m} م، و{outcome_phrase}. فريقك ينجو.",
            ),
        ],
    },
    "let_off_choice": {
        "casual": [
            (
                "{g_let_off}: {player_short} فضّل التسديد",
                "{teammate_short} كان حرًا، والتمريرة كانت تساوي {times_better} أضعاف التسديدة. فريقك نجا.",
            ),
        ],
        "tactical": [
            (
                "فريقك ينجو: {player_short} تجاهل {teammate_short}",
                "التسديدة {shot_xg} xG؛ والتمريرة لمسافة {pass_distance_m} م كانت نسبة نجاحها {pass_success_pct}%. "
                "فريقك نجا.",
            ),
        ],
    },
    "let_off_run": {
        "casual": [
            (
                "{g_let_off}: لم يرَ أحد انطلاقة {runner_short}",
                "{runner} اخترق خلف {g_back_line} لدى فريقك، لكن {player_short} لم يمرر الكرة. "
                "كانت ستصبح فرصة بنسبة {projected_xg_pct}%.",
            ),
        ],
        "tactical": [
            (
                "{g_let_off}: {runner_short} متقدم بـ{clear_of_line_m} م",
                "{runner_short} تجاوز {g_back_line} لدى فريقك عند {pass_on_clock}؛ والتمريرة كانت ستصنع فرصة "
                "{projected_xg} xG. {player_short} لم يرها.",
            ),
        ],
    },
    "lesson_choice": {
        "casual": [
            (
                "في المرة القادمة، ابحث عن {teammate_short}",
                "{player_short} سدد، لكن التمريرة إلى {teammate_short} كانت تساوي {times_better} أضعاف التسديدة. "
                "درس يتعلم منه فريقك.",
            ),
        ],
        "tactical": [
            (
                "درس: التمريرة إلى {teammate_short}",
                "التسديدة {shot_xg} xG؛ والتمريرة لمسافة {pass_distance_m} م كانت نسبة نجاحها {pass_success_pct}% "
                "وخلفها {alt_xg} xG. الكرة الأفضل كانت متاحة.",
            ),
        ],
    },
    "lesson_run": {
        "casual": [
            (
                "انطلاقة {runner_short} كانت تستحق الكرة",
                "{runner} كان متقدمًا بـ{clear_of_line_m} م على {g_back_line}؛ وفي المرة القادمة يستطيع {player_short} "
                "إيجاده. كانت ستصبح فرصة بنسبة {projected_xg_pct}%.",
            ),
        ],
        "tactical": [
            (
                "انطلاقة بلا تمريرة: {runner_short}، {clear_of_line_m} م",
                "التمريرة البينية كانت متاحة عند {pass_on_clock}: فرصة {projected_xg} xG. "
                "في المرة القادمة يستطيع {player_short} إيجاده.",
            ),
        ],
    },
    "pressure_for": {
        "casual": [
            ("فريقك يضغط بقوة", "فريقك يحاصر {opp} منذ {spell_min} دقائق. استمروا هكذا."),
        ],
    },
    "hold_firm": {
        "casual": [
            (
                "الصمود: {team} يضغط",
                "{team} يحاصر فريقك منذ {spell_min} دقائق. حان وقت الصمود وإبعاد الكرة عن {g_box}.",
            ),
        ],
        "tactical": [
            (
                "تحت الضغط: {team} عند {pressure_index}",
                "مؤشر الضغط {pressure_index} لمدة {spell_min} دقائق، مع سيطرة على الملعب بنسبة {team_field_tilt_pct}% "
                "ضد فريقك.",
            ),
        ],
    },
    "momentum_against": {
        "casual": [
            (
                "تحذير: {team} يفرض سيطرته",
                "تحرك الزخم {momentum_change} نقطة نحو {team} في {window_min} دقائق. فريقك يحتاج إلى رد.",
            ),
        ],
        "tactical": [
            (
                "الزخم يتحول ضد فريقك",
                "تحرك الزخم {momentum_change} نقطة في {window_min} دقائق؛ و{team} يسيطر على الملعب بنسبة "
                "{team_field_tilt_pct}%.",
            ),
        ],
    },
    "full_time_won": {"casual": [("النهاية: فوز لفريقك!", _SCORE + ". نتيجة تستحق الاحتفال.")]},
    "full_time_lost": {"casual": [("النهاية: خسارة لفريقك", _SCORE + ". حان وقت النهوض من جديد.")]},
    "full_time_drawn": {"casual": [("النهاية: تعادل", _SCORE + ". نقطة لكل فريق.")]},
}
PACK["metric"]["momentum_against"] = [
    ("تحذير: الزخم لصالح {team}", "تحرك الزخم {change} نقطة نحو {team}، بعيدًا عن فريقك."),
]
PACK["heart"]["attack_stopped"] = {
    "casual": [
        (
            "{player_short} يوقف هجمة فريقك",
            "{player} استعاد الكرة على بعد {own_goal_distance_m} م من مرماه. فريقك يبدأ من جديد.",
        ),
    ],
    "tactical": [
        (
            "هجمة أُوقفت: أُلغي خطر بقيمة {xt_stopped} xT",
            "{player_short} استعادها في ثلثه الدفاعي على بعد {own_goal_distance_m} م. على فريقك إعادة البناء.",
        ),
    ],
}
