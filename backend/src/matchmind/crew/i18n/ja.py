"""日本語のスタジオ用フレーズ。en.py と同じ形式。選手名とクラブ名はそのまま表記。"""

PACK = {
    "your_team": "応援チーム",
    "labels": {
        "xg": "チャンスの質（xG）",
        "distance_m": "ゴールまでの距離",
        "shot_speed_kmh": "シュート速度",
        "score_home": "ホームの得点",
        "score_away": "アウェイの得点",
        "card": "カード",
        "shot_xg": "シュートのxG",
        "alt_xg": "味方のチャンスxG",
        "pass_success_pct": "パス成功の可能性",
        "alt_value": "パスの期待値",
        "times_better": "パス対シュート",
        "pass_distance_m": "パス距離",
        "nearest_marker_m": "最も近いマーカー",
        "clear_of_line_m": "最終ラインとの差",
        "projected_xg": "想定されるチャンスxG",
        "pass_on_clock": "パスが通せた時間",
        "one_on_one": "一対一",
        "momentum_change": "流れの変化",
        "window_min": "対象時間",
        "team_field_tilt_pct": "フィールドの支配率",
        "team_shots_5": "シュート数（直近5分）",
        "team_xg_total": "チームxG",
        "pressure_index": "プレッシャー指数",
        "spell_min": "継続時間",
        "team_box_entries_5": "ボックス進入（直近5分）",
        "speed_kmh": "スピード",
        "top_speed_kmh": "最高速度",
        "sprints": "スプリント回数",
        "milestone_km": "走行距離（推定）",
        "pass_difficulty": "パスの難易度",
        "xt_delta": "加算された脅威（xT）",
        "xg_home": "ホームxG",
        "xg_away": "アウェイxG",
        "shots_home": "ホームのシュート数",
        "shots_away": "アウェイのシュート数",
        "appearance_n": "クラブ出場数",
        "ruled_out_clock": "取り消されたゴール（得点時刻）",
        "xt_stopped": "防いだ脅威（xT）",
        "own_goal_distance_m": "自陣ゴールからの距離",
        "p_tackles_won": "タックル成功数",
        "last_ditch": "最後の砦（自陣ペナルティエリア内）",
        "distance_km": "走行距離（トラッキング推定）",
        "sprint_m": "スプリント距離",
    },
    "zones": {
        "Penalty Box": "ペナルティエリア",
        "Attacking Third": "アタッキングサード",
        "Middle Third": "ミドルサード",
        "Defensive Third": "ディフェンシブサード",
        "": "オープンプレー",
    },
    "outcomes": {
        "saved": "キーパーがセーブ",
        "blocked": "DFがブロック",
        "off_target": "枠を外れた",
        "goal": "ゴールネットを揺らした",
        "": "得点にはならず",
    },
    "card_name": {"yellow": "イエローカード", "red": "レッドカード"},
    "card_name_cap": {"yellow": "イエローカード", "red": "レッドカード"},
    "card_action": {"yellow": "に警告", "red": "が退場"},
    "var_reason": {"offside": "オフサイド", "handball": "ハンド", "foul": "ファウル"},
    "fav_goal": {
        "for": "応援チームにゴール！{player_short}",
        "against": "{player_short}のゴールで応援チームが失点",
    },
    "narr": {
        "goal": {
            "casual": [
                (
                    "ゴール！{team}の{player_short}",
                    "{assist}のパスから{player}が決めました。スコアは{home} {score_home}-{score_away} {away}。",
                ),
                (
                    "ゴール！{team}の{player_short}",
                    "{player}が決めました。スコアは{home} {score_home}-{score_away} {away}。",
                ),
            ],
            "tactical": [
                (
                    "{player_short}、{xg} xGの決定機を沈める",
                    "{assist_short}が{zone}、{distance_m}mの位置の{player_short}へ。"
                    "{home} {score_home}-{score_away} {away}。",
                ),
                (
                    "{player_short}、{xg} xGの決定機を沈める",
                    "{player_short}が{zone}、{distance_m}mから決めました。{home} {score_home}-{score_away} {away}。",
                ),
            ],
            "fantasy": [
                (
                    "得点{player_short}、アシスト{assist_short}",
                    "{player_short}の今日の成績：{p_goals}ゴール、シュート{p_shots}本で{p_xg} xG。"
                    "このチャンスの価値は{xg} xG。",
                ),
                (
                    "{player_short}がゴール",
                    "{player_short}の今日の成績：{p_goals}ゴール、シュート{p_shots}本で{p_xg} xG。"
                    "このチャンスの価値は{xg} xG。",
                ),
            ],
            "player_spotlight": [
                (
                    "{player_short}が決めた！",
                    "{player}が{distance_m}mの位置からキーパーを破りました。{home} {score_home}-{score_away} {away}。",
                )
            ],
        },
        "card": {
            "casual": [("{player_short}に{card_name}", "{player}{card_action}。{team}は注意が必要です。")],
            "tactical": [
                (
                    "{card_name}：{player_short}",
                    "{player}{card_action}。{team}はこのサイドの守備を慎重にせざるを得ません。",
                )
            ],
            "fantasy": [
                (
                    "{player_short}に{card_name}",
                    "{player_short}の今日の成績：{p_goals}ゴール、{p_assists}アシスト、{p_xg} xG。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}に{card_name}",
                    "{player}{card_action}。ここからはデュエルの一つひとつがリスクです。",
                )
            ],
        },
        "big_chance": {
            "casual": [
                (
                    "{player_short}に決定機！",
                    "{player}がゴールまで{distance_m}mでフリーになるも、結果は{outcome_phrase}。"
                    "こうしたチャンスが決まる確率は約{xg_pct}%です。",
                )
            ],
            "tactical": [
                (
                    "{team}に{xg} xGのチャンス",
                    "{player_short}が{zone}の{distance_m}mからシュートも、{outcome_phrase}。"
                    "シュートの価値は{xg} xG。",
                )
            ],
            "fantasy": [
                (
                    "{player_short}：{xg} xGのチャンス",
                    "{player_short}はシュート{p_shots}本で{p_xg} xG。この一本は決まらず。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}に決定機",
                    "{player_short}が{distance_m}mの位置でスペースを得るも、{outcome_phrase}。"
                    "今日はシュート{p_shots}本、{p_xg} xG。",
                )
            ],
        },
        "better_option": {
            "casual": [
                (
                    "{player_short}はパスすべきだった？",
                    "{player_short}はシュートを選びましたが、{teammate_short}がフリーでした。"
                    "パスの価値はシュートの{times_better}倍でした。",
                )
            ],
            "tactical": [
                (
                    "判断ミス：{player_short}、{teammate_short}を使わず",
                    "シュートは{shot_xg} xGでしたが、{pass_distance_m}mのパスは成功率{pass_success_pct}%で、"
                    "その先に{alt_xg} xGのチャンスがあり、期待値{alt_value}はシュートの{times_better}倍です。",
                )
            ],
            "fantasy": [
                (
                    "{player_short}、幻のアシスト",
                    "{teammate_short}へのパスは{alt_value}の期待ゴール、シュートは{shot_xg} xG。"
                    "{player_short}の今日はシュート{p_shots}本で{p_xg} xG。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}はシュートを選択",
                    "{teammate_short}は{pass_distance_m}m先でフリー、{nearest_marker_m}m以内に相手はいませんでした。"
                    "パスはシュートの{times_better}倍有効でした。",
                )
            ],
        },
        "unfound_run": {
            "casual": [
                (
                    "{runner_short}の走り込み、見逃される",
                    "{runner}が最終ラインの裏へ抜けましたが、{player_short}のパスは出ませんでした。"
                    "決定率{projected_xg_pct}%のチャンスになり得ました。",
                )
            ],
            "tactical": [
                (
                    "使われなかった裏抜け：{runner_short}",
                    "{runner_short}は最終ラインを{clear_of_line_m}m抜け、{pass_on_clock}にスルーパスのコースがありました。"
                    "想定チャンスは{projected_xg} xG。",
                )
            ],
            "fantasy": [
                (
                    "{runner_short}、{projected_xg} xGを逃す",
                    "{player_short}からのスルーパスは出ず。この走り込みの価値は{projected_xg} xGでした。",
                )
            ],
            "player_spotlight": [
                (
                    "{runner_short}が裏へ抜ける",
                    "{runner_short}はDFから{clear_of_line_m}m抜け出しましたが、{player_short}はボールを持ち続けました。",
                )
            ],
        },
        "momentum_swing": {
            "casual": [
                (
                    "{team}が主導権を握る",
                    "流れが{team}に傾きました。勢いの指標が{window_min}分間で{momentum_change}ポイント動いています。",
                )
            ],
            "tactical": [
                (
                    "流れが{team}へ",
                    "モメンタムが{window_min}分間で{momentum_change}ポイント変動。"
                    "{team}のフィールドティルトは{team_field_tilt_pct}%です。",
                )
            ],
            "fantasy": [
                (
                    "{team}が優勢：攻撃陣に注目",
                    "{team}は直近{window_min}分でシュート{team_shots_5}本。試合全体のxGは{team_xg_total}です。",
                )
            ],
        },
        "pressure_spell": {
            "casual": [
                (
                    "{team}が猛攻",
                    "{team}が{spell_min}分間、{opp}を押し込んでいます。そろそろ何かが起きそうです。",
                )
            ],
            "tactical": [
                (
                    "持続的なプレス：{team}、指数{pressure_index}",
                    "プレッシャー指数{pressure_index}が{spell_min}分間継続、フィールドティルトは{team_field_tilt_pct}%。"
                    "{opp}は落ち着いてビルドアップできません。",
                )
            ],
            "fantasy": [
                (
                    "{team}がハイプレス",
                    "{team}は直近{window_min}分でシュート{team_shots_5}本、試合全体で{team_xg_total} xG。"
                    "攻撃陣にチャンスが来ています。",
                )
            ],
        },
        "speed_burst": {
            "casual": [
                (
                    "{player_short}、時速{speed_kmh}km",
                    "{player}がトップスピードの時速{speed_kmh}kmに到達。ここまでのスプリントは{sprints}回です。",
                )
            ],
            "tactical": [
                (
                    "スプリント：{player_short}、時速{speed_kmh}km",
                    "{player_short}がスプリント基準の時速{speed_threshold_kmh}kmを超えました。今日のスプリントは{sprints}回。",
                )
            ],
            "fantasy": [
                (
                    "{player_short}が躍動",
                    "{player_short}のここまで：シュート{p_shots}本、{p_xg} xG、キーパス{p_key_passes}本。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}、全速力",
                    "時速{speed_kmh}km、今日の最高速度は時速{top_speed_kmh}km。スプリントは{sprints}回です。",
                )
            ],
        },
        "rocket_shot": {
            "casual": [
                (
                    "{player_short}の弾丸シュート！",
                    "{player}のシュートは時速{shot_speed_kmh}km、結果は{outcome_phrase}。",
                )
            ],
            "tactical": [
                (
                    "{player_short}、時速{shot_speed_kmh}kmの一撃",
                    "{distance_m}mから球速時速{shot_speed_kmh}km、{xg} xGのチャンス。"
                    "この球速ではキーパーの反応時間はほとんどありません。",
                )
            ],
            "fantasy": [
                (
                    "{player_short}のシュート：{xg} xG",
                    "{player_short}はシュート{p_shots}本で{p_xg} xGになりました。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}が振り抜く",
                    "{distance_m}mから時速{shot_speed_kmh}km、結果は{outcome_phrase}。",
                )
            ],
        },
        "distance_milestone": {
            "casual": [
                (
                    "{player_short}、推定{milestone_km}km突破",
                    "{player}の走行距離が推定{milestone_km}kmに達しました。足が止まりません。",
                )
            ],
            "tactical": [
                (
                    "運動量：{player_short}、推定{milestone_km}km",
                    "{player_short}は推定{milestone_km}kmを走り、スプリントは{sprints}回。最高速度は時速{top_speed_kmh}km。",
                )
            ],
            "fantasy": [
                (
                    "{player_short}：推定{milestone_km}km",
                    "よく走っています（距離は推定値）。攻撃面はシュート{p_shots}本、{p_xg} xG、キーパス{p_key_passes}本。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}、推定{milestone_km}km",
                    "{player_short}の走行距離は推定{milestone_km}km、スプリント{sprints}回、最高速度は時速{top_speed_kmh}km。",
                )
            ],
        },
        "hard_pass": {
            "casual": [
                (
                    "{player_short}の見事なパス！",
                    "{player}が{pass_distance_m}mのパスで{receiver_short}へ。難易度は{difficulty_scale}点中{pass_difficulty}点です。",
                )
            ],
            "tactical": [
                (
                    "PDR {pass_difficulty}：{player_short}から{receiver_short}へ",
                    "{pass_distance_m}m、難易度{pass_difficulty}のパスで{xt_delta} xTを上積み。",
                ),
                (
                    "PDR {pass_difficulty}：{player_short}から{receiver_short}へ",
                    "{pass_distance_m}m、難易度{pass_difficulty}のパスでラインを突破。",
                ),
            ],
            "fantasy": [
                (
                    "{player_short}がチャンスを創出",
                    "{player_short}の今日の成績：キーパス{p_key_passes}本、{p_xa} xA。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}が通した",
                    "{receiver_short}への{pass_distance_m}mのパス、難易度は{difficulty_scale}点中{pass_difficulty}点。",
                )
            ],
        },
        "key_tackle": {
            "casual": [
                (
                    "{player_short}の決定的なタックル",
                    "{player}が自陣ゴールから{own_goal_distance_m}mの位置で{victim_short}からボールを奪いました。{team}は危機を脱出。",
                ),
                (
                    "{player_short}の決定的なタックル",
                    "{player}が自陣ゴールから{own_goal_distance_m}mの位置でボールを奪いました。{team}は危機を脱出。",
                ),
            ],
            "tactical": [
                (
                    "キータックル：{player_short}",
                    "自陣ゴールから{own_goal_distance_m}mの守備ゾーンで奪取し、{opp}の{xt_stopped} xTの脅威を断ちました。{player_short}のタックル成功は今日{p_tackles_won}回。",
                )
            ],
            "fantasy": [
                (
                    "{player_short}が攻撃を断つ",
                    "{player_short}の守備：ここまでタックル成功{p_tackles_won}回。今回は自陣ゴールから{own_goal_distance_m}mの位置です。",
                )
            ],
            "player_spotlight": [
                (
                    "{player_short}がボール奪取",
                    "自陣ゴールから{own_goal_distance_m}mでのタックルで{xt_stopped} xTの脅威を消しました。今日のタックル成功：{p_tackles_won}回。",
                )
            ],
        },
        "correction": {
            "casual": [
                (
                    "ノーゴール！VARで{player_short}の得点取り消し",
                    "{ruled_out_clock}の{player}のゴールは、VARの確認で{reason_phrase}により取り消されました。スコアは{home} {score_home}-{score_away} {away}のまま。",
                )
            ],
            "tactical": [
                (
                    "VAR：{player_short}のゴールを取り消し",
                    "{reason_phrase}で判定が覆りました。スコアは{home} {score_home}-{score_away} {away}に戻ります。",
                )
            ],
            "fantasy": [
                (
                    "ゴール取り消し：{player_short}",
                    "VARで{reason_phrase}のためゴールは取り消し、シュートは記録に残ります。{player_short}の今日の成績：{p_goals}ゴール、シュート{p_shots}本で{p_xg} xG。",
                )
            ],
            "player_spotlight": [
                (
                    "ノーゴール！VARで{player_short}の得点取り消し",
                    "{ruled_out_clock}の{player}のゴールは、VARの確認で{reason_phrase}により取り消されました。スコアは{home} {score_home}-{score_away} {away}のまま。",
                )
            ],
        },
        "milestone.kick_off": {
            "casual": [
                (
                    "キックオフ：{home}対{away}",
                    "{home}対{away}の試合が始まりました。重要な場面をお知らせします。",
                )
            ],
            "tactical": [
                (
                    "キックオフ：{home}対{away}",
                    "{home}対{away}の試合が始まりました。開始直後からプレッシャーとモメンタムの推移に注目です。",
                )
            ],
            "fantasy": [
                (
                    "キックオフ：{home}対{away}",
                    "{home}対{away}の試合が始まりました。ゴール、アシスト、xG、xA、シュート、キーパスをライブで追跡します。",
                )
            ],
        },
        "milestone.half_time": {
            "casual": [
                (
                    "前半終了：{home} {score_home}-{score_away} {away}",
                    "ハーフタイムです。シュート数は{home}が{shots_home}本、{away}が{shots_away}本。",
                )
            ],
            "tactical": [
                (
                    "前半終了：{home} {score_home}-{score_away} {away}",
                    "期待ゴールは{xg_home}対{xg_away}、シュートは{shots_home}対{shots_away}。",
                )
            ],
            "fantasy": [
                (
                    "前半終了：{home} {score_home}-{score_away} {away}",
                    "前半のxG：{home} {xg_home}、{away} {xg_away}。",
                )
            ],
        },
        "milestone.full_time": {
            "casual": [
                (
                    "試合終了：{home} {score_home}-{score_away} {away}",
                    "試合終了です。シュート数は{home}が{shots_home}本、{away}が{shots_away}本でした。",
                )
            ],
            "tactical": [
                (
                    "試合終了：{home} {score_home}-{score_away} {away}",
                    "最終的な期待ゴールは{xg_home}対{xg_away}、シュートは{shots_home}対{shots_away}。",
                )
            ],
            "fantasy": [
                (
                    "試合終了：{home} {score_home}-{score_away} {away}",
                    "最終xG：{home} {xg_home}、{away} {xg_away}。シュート数は{shots_home}対{shots_away}。",
                )
            ],
        },
        "milestone.player": {
            "casual": [
                (
                    "{player_short}、クラブ通算{appearance_n}試合目",
                    "{player}は今日、{team}で通算{appearance_n}試合目を迎えました。",
                ),
                ("{player_short}、記念の一日", "{player}が今日、{team}で節目を迎えました。"),
            ],
            "tactical": [
                (
                    "{player_short}：クラブ通算{appearance_n}試合",
                    "{player}は{team}で通算{appearance_n}試合に到達。",
                ),
                ("{player_short}、記念の一日", "{player}が今日、{team}で節目を迎えました。"),
            ],
            "fantasy": [
                (
                    "{player_short}：通算{appearance_n}試合目",
                    "{player_short}の今日の成績：{p_goals}ゴール、{p_assists}アシスト、{p_xg} xG。",
                ),
                (
                    "{player_short}、記念の一日",
                    "{player_short}の今日の成績：{p_goals}ゴール、{p_assists}アシスト、{p_xg} xG。",
                ),
            ],
        },
    },
    "why": {
        "goal": ["{xg} xGのチャンスから、スコアは{home} {score_home}-{score_away} {away}に。"],
        "card": ["{player_short}{card_action}。{team}は守り方の修正を迫られます。"],
        "big_chance": ["{xg} xGは明確な決定機。{team}は危険なエリアに入り込んでいます。"],
        "better_option": [
            "{teammate_short}へのパスは{alt_value}の期待ゴール、シュートは{shot_xg}。パスの方が{times_better}倍有効でした。"
        ],
        "unfound_run": [
            "{pass_on_clock}、{runner_short}は最終ラインを{clear_of_line_m}m抜けていました。"
            "パスが出ていれば{projected_xg} xGのチャンスでした。"
        ],
        "momentum_swing": [
            "モメンタムが{window_min}分間で{momentum_change}ポイント変動。主導権が入れ替わりました。"
        ],
        "pressure_spell": [
            "プレッシャー指数{pressure_index}が{spell_min}分間続き、{opp}は落ち着いて組み立てられません。"
        ],
        "speed_burst": [
            "時速{speed_kmh}kmはスプリント基準の時速{speed_threshold_kmh}kmを超える速さ。スピードは守備を広げます。"
        ],
        "rocket_shot": ["時速{shot_speed_kmh}kmでは、キーパーが反応する時間はほとんどありません。"],
        "distance_milestone": [
            "推定{milestone_km}kmの走行距離が、{team}の組織を支える運動量を示しています。"
        ],
        "hard_pass": [
            "難易度{difficulty_scale}点中{pass_difficulty}点は、成功させられる選手が少ないパスです。"
        ],
        "key_tackle": [
            "ゴールから{own_goal_distance_m}mでのタックルが、{opp}の{xt_stopped} xTの脅威を消しました。"
        ],
        "correction": [
            "VARが{ruled_out_clock}のゴールを{reason_phrase}で取り消し、スコアは{home} {score_home}-{score_away} {away}に戻りました。"
        ],
        "milestone.kick_off": ["試合が始まりました。"],
        "milestone.half_time": ["前半の期待ゴールは{xg_home}対{xg_away}。"],
        "milestone.full_time": ["最終的な期待ゴールは{xg_home}対{xg_away}。"],
        "milestone.player": [
            "{player_short}がクラブ通算{appearance_n}試合に到達。",
            "{player_short}にとって節目の一日です。",
        ],
    },
    "metric": {
        "pressure": [
            (
                "プレッシャー指数：{team} {pressure_index}",
                "{team}のプレッシャー指数が{change}ポイント動き、{pressure_index}になりました。",
            )
        ],
        "xg": [("xG更新：{subject} {xg}", "{subject}のxGが{change}増えて{xg}になりました。")],
        "pass_difficulty": [
            (
                "パス難易度{pass_difficulty}",
                "{player_short}が難易度{difficulty_scale}点中{pass_difficulty}点のパスを成功させました。",
            )
        ],
        "top_speed": [
            (
                "最高速度更新：時速{top_speed_kmh}km",
                "{subject}が最高速度を時速{top_speed_kmh}kmに更新しました。",
            )
        ],
        "momentum": [("モメンタム：{team}が優勢", "モメンタムが{change}ポイント{team}に傾きました。")],
    },
    "recap": {
        "title_full": "試合終了：{home} {score_home}-{score_away} {away}",
        "title_live": "ここまでの試合：{home} {score_home}-{score_away} {away}",
        "headline_win": "{winner}が{score_w}-{score_l}で{loser}に勝利",
        "headline_draw": "{home}と{away}は{score_home}-{score_away}で引き分け",
        "headline_lead": "{winner}が{score_w}-{score_l}で{loser}をリード",
        "headline_level": "{score_home}-{score_away}の同点",
        "p1_full": "{home}対{away}は{score_home}-{score_away}で終了。期待ゴールは{xg_home}対{xg_away}、"
        "シュートは{shots_home}本対{shots_away}本でした。",
        "p1_live": "{generated_at}時点で{home} {score_home}-{score_away} {away}。ここまでの期待ゴールは"
        "{xg_home}対{xg_away}、シュートは{shots_home}本対{shots_away}本です。",
        "goals": "得点：{goals_line}。",
        "no_goals": "まだ得点はありませんが、決定機は{n_big_chances}回ありました。",
        "turning": "パスの方が良かったシュートが{n_better_options}回、使われなかった裏抜けが{n_unfound_runs}回ありました。",
        "potm": {
            "casual": "マン・オブ・ザ・マッチは{potm_team}の{potm}。{potm_goals}ゴール、{potm_assists}アシストでした。",
            "tactical": "プレスの時間帯が{n_pressure_spells}回、流れの変化が{n_momentum_swings}回。"
            "マン・オブ・ザ・マッチは{potm}で、キーパス{potm_key_passes}本、タックル成功{potm_tackles}回。",
            "fantasy": "マン・オブ・ザ・マッチは{potm}：{potm_goals}ゴール、{potm_assists}アシスト、"
            "{potm_xg} xG、{potm_xa} xA、キーパス{potm_key_passes}本。",
        },
        "focus": "{focus}：パス{focus_passes}本中{focus_passes_completed}本成功、走行距離は推定{focus_distance_km}km、"
        "最高速度は時速{focus_top_speed_kmh}km。",
    },
}

# テンプレートが `{g_<用語>}` として使うサッカー用語（docs/LANGUAGES.md）。
PACK["glossary"] = {
    "box": "ペナルティエリア",
    "keeper": "キーパー",
    "back_line": "最終ライン",
    "equaliser": "同点ゴール",
    "comeback": "反撃",
    "let_off": "命拾い",
    "rocket": "弾丸シュート",
}

_SCORE = "{home} {score_home}-{score_away} {away}"

# クラブ目線（crew/club_heart.py）：同じ事実を、応援する側から伝える。
PACK["heart"] = {
    "goal_for": {
        "casual": [
            (
                "応援チームにゴール！{player_short}",
                "{player}が{distance_m}mから{g_keeper}を破りました。" + _SCORE + "。",
            ),
        ],
        "tactical": [
            (
                "{player_short}、{xg} xGを決める",
                "{zone}の{distance_m}mから。{match_clock}時点で" + _SCORE + "。",
            ),
        ],
        "fantasy": [
            (
                "{player_short}のゴールで応援チーム得点",
                "{player_short}の今日の成績：{p_goals}ゴール、シュート{p_shots}本で{p_xg} xG。このチャンスは{xg} xG。",
            ),
        ],
    },
    "goal_for_level": {
        "casual": [
            (
                "同点！{player_short}が応援チームを救う",
                "{player}が{match_clock}に{g_equaliser}。" + _SCORE + "、{g_comeback}開始です。",
            ),
        ],
        "tactical": [
            (
                "{player_short}が{xg} xGで同点弾",
                "{zone}の{distance_m}mから。{match_clock}時点で" + _SCORE + "。",
            ),
        ],
    },
    "goal_for_pull_back": {
        "casual": [
            (
                "{player_short}が点差を縮める！",
                "{match_clock}時点で" + _SCORE + "。応援チームはまだ戦える、{g_comeback}はここから。",
            ),
        ],
        "tactical": [
            (
                "点差を縮める：{player_short}、{xg} xG",
                "{zone}の{distance_m}mから。{match_clock}時点で" + _SCORE + "。",
            ),
        ],
    },
    "goal_for_lead": {
        "casual": [
            (
                "ゴール！{player_short}で応援チームが勝ち越し",
                "{player}が{match_clock}にゴール。" + _SCORE + "。",
            ),
        ],
        "tactical": [
            (
                "勝ち越し：{player_short}、{xg} xG",
                "{match_clock}、{zone}の{distance_m}mから。" + _SCORE + "。",
            ),
        ],
    },
    "goal_against": {
        "casual": [
            (
                "{player_short}のゴールで応援チームが失点",
                "{match_clock}時点で" + _SCORE + "。まだ反撃の時間があります。",
            ),
        ],
        "tactical": [
            (
                "失点：{player_short}、{xg} xG",
                "{zone}の{distance_m}mから。{match_clock}時点で" + _SCORE + "、まだ時間はあります。",
            ),
        ],
        "fantasy": [
            (
                "{player_short}のゴールで応援チームが失点",
                "{player_short}の今日の成績：{p_goals}ゴール、シュート{p_shots}本で{p_xg} xG。このチャンスは{xg} xG。",
            ),
        ],
    },
    "goal_against_level": {
        "casual": [
            (
                "追いつかれる：{player_short}が同点弾",
                "{match_clock}時点で" + _SCORE + "。応援チームは気持ちを切り替えたいところ。",
            ),
        ],
        "tactical": [
            (
                "相手の{g_equaliser}：{player_short}、{xg} xG",
                "{zone}の{distance_m}mから。{match_clock}時点で" + _SCORE + "。",
            ),
        ],
    },
    "goal_against_lead_cut": {
        "casual": [
            (
                "{player_short}のゴールでリードが縮まる",
                "{match_clock}時点で" + _SCORE + "。応援チームはまだリード、落ち着いて。",
            ),
        ],
        "tactical": [
            (
                "リード縮小：{player_short}、{xg} xG",
                "{zone}の{distance_m}mから。{match_clock}時点でまだリード：" + _SCORE + "。",
            ),
        ],
    },
    "goal_against_late": {
        "casual": [
            (
                "痛恨の失点：{player_short}",
                "{match_clock}時点で" + _SCORE + "。この時間帯の失点は応援チームにとって痛い。",
            ),
        ],
        "tactical": [
            (
                "終盤の失点：{player_short}、{xg} xG",
                "{match_clock}、{zone}の{distance_m}mから。" + _SCORE + "。",
            ),
        ],
    },
    "card_own": {
        "casual": [
            (
                "{player_short}に{card_name}",
                "{match_clock}、{player}に{card_name}。応援チームは冷静さが必要です。",
            ),
        ],
    },
    "card_rival": {
        "casual": [
            (
                "{player_short}に{card_name}",
                "{match_clock}、{player}に{card_name}。応援チームにとってはチャンスです。",
            ),
        ],
    },
    "let_off": {
        "casual": [
            (
                "応援チーム、{g_let_off}！",
                "{team}の{player}がゴールまで{distance_m}mで決定機も、結果は{outcome_phrase}。"
                "こうしたチャンスが決まる確率は約{xg_pct}%です。",
            ),
        ],
        "tactical": [
            (
                "危険：{team}に{xg} xGのチャンス",
                "{player_short}が{zone}の{distance_m}mからシュートも、{outcome_phrase}。応援チームの{g_back_line}が破られました。",
            ),
        ],
    },
    "let_off_shot": {
        "casual": [
            (
                "{g_let_off}：{player_short}の{g_rocket}",
                "{player}が{distance_m}mから時速{shot_speed_kmh}kmのシュート、結果は{outcome_phrase}。応援チームは助かりました。",
            ),
        ],
    },
    "let_off_choice": {
        "casual": [
            (
                "{g_let_off}：{player_short}はシュートを選択",
                "{teammate_short}がフリーで、パスの価値はシュートの{times_better}倍でした。応援チームは助かりました。",
            ),
        ],
        "tactical": [
            (
                "{g_let_off}：{player_short}が{teammate_short}を使わず",
                "シュートは{shot_xg} xG、{pass_distance_m}mのパスは成功率{pass_success_pct}%でした。応援チームは助かりました。",
            ),
        ],
    },
    "let_off_run": {
        "casual": [
            (
                "{g_let_off}：{runner_short}の動き出しは見逃された",
                "{runner}が応援チームの{g_back_line}の裏を取りましたが、{player_short}はパスを出しませんでした。"
                "決定率{projected_xg_pct}%のチャンスになり得ました。",
            ),
        ],
        "tactical": [
            (
                "{g_let_off}：{runner_short}が{clear_of_line_m}m抜け出す",
                "{pass_on_clock}、{runner_short}は応援チームの{g_back_line}を越えていました。"
                "パスが出ていれば{projected_xg} xGのチャンスでした。",
            ),
        ],
    },
    "lesson_choice": {
        "casual": [
            (
                "次は{teammate_short}を見つけよう",
                "{player_short}はシュートを選びましたが、{teammate_short}へのパスは{times_better}倍の価値がありました。"
                "応援チームの次への課題です。",
            ),
        ],
        "tactical": [
            (
                "課題：{teammate_short}へのパス",
                "シュートは{shot_xg} xG、{pass_distance_m}mのパスは成功率{pass_success_pct}%で、その先に{alt_xg} xG。"
                "より良い選択肢がありました。",
            ),
        ],
    },
    "lesson_run": {
        "casual": [
            (
                "{runner_short}の動き出しはパスに値した",
                "{runner}は{g_back_line}を{clear_of_line_m}m抜けていました。次は{player_short}が見つけられるはずです。",
            ),
        ],
        "tactical": [
            (
                "見逃された動き出し：{runner_short}、{clear_of_line_m}m",
                "{pass_on_clock}にスルーパスの選択肢があり、{projected_xg} xGのチャンスでした。次は{player_short}が見つけたい。",
            ),
        ],
    },
    "pressure_for": {
        "casual": [
            (
                "応援チームが押し込む",
                "応援チームが{spell_min}分間、{opp}を押し込んでいます。この勢いを続けたい。",
            ),
        ],
    },
    "hold_firm": {
        "casual": [
            (
                "耐えどころ：{team}が猛攻",
                "{team}が{spell_min}分間、応援チームを押し込んでいます。{g_box}からボールを遠ざけたい。",
            ),
        ],
        "tactical": [
            (
                "劣勢：{team}のプレス指数{pressure_index}",
                "プレッシャー指数{pressure_index}が{spell_min}分間継続、{team}のフィールドティルトは{team_field_tilt_pct}%。",
            ),
        ],
    },
    "momentum_against": {
        "casual": [
            (
                "警戒：{team}が主導権",
                "勢いの指標が{window_min}分間で{momentum_change}ポイント{team}に傾きました。応援チームは立て直しが必要です。",
            ),
        ],
        "tactical": [
            (
                "モメンタムが応援チームに不利",
                "モメンタムが{window_min}分間で{momentum_change}ポイント変動、{team}のフィールドティルトは{team_field_tilt_pct}%。",
            ),
        ],
    },
    "full_time_won": {"casual": [("試合終了：応援チームの勝利！", _SCORE + "。喜びたい結果です。")]},
    "full_time_lost": {"casual": [("試合終了：応援チームは敗戦", _SCORE + "。次に向けて立て直しです。")]},
    "full_time_drawn": {"casual": [("試合終了：引き分け", _SCORE + "。勝ち点を分け合いました。")]},
}
PACK["metric"]["momentum_against"] = [
    ("警戒：モメンタムが{team}へ", "モメンタムが{change}ポイント{team}に傾き、応援チームには逆風です。"),
]
PACK["heart"]["attack_stopped"] = {
    "casual": [
        (
            "{player_short}が応援チームの攻撃を止める",
            "{player}が自陣ゴールから{own_goal_distance_m}mでボールを奪いました。応援チームは仕切り直しです。",
        ),
    ],
    "tactical": [
        (
            "攻撃阻止：{xt_stopped} xTを消す",
            "{player_short}が自陣の守備ゾーン、ゴールから{own_goal_distance_m}mで奪取。応援チームは組み立て直しです。",
        ),
    ],
}
