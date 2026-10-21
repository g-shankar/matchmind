"""日本語のスタジオ用フレーズ。en.py と同じ形式。選手名とクラブ名はそのまま表記。"""

PACK = {
    "your_team": "応援チーム",
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
                    "ポイントは減点。{player_short}の今日の成績：{p_goals}ゴール、{p_assists}アシスト、{p_xg} xG。",
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
                    "最終xG：{home} {xg_home}、{away} {xg_away}。ポイントを確認しましょう。",
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
