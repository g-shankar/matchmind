import os
import httpx
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("pitchpulse.translator")

# Authentic Multilingual Football Translation Templates
TRANSLATION_TEMPLATES = {
    "fr": {
        "labels": {
            "why_it_matters": "POURQUOI C'EST DÉCISIF :",
            "tactical_context": "ANALYSE TACTIQUE",
            "stream": "Flux :",
            "all_updates": "Toutes les Mises à Jour",
            "ai_insights": "Analyses IA",
            "play_by_play": "Direct Commenté",
            "speed": "Vitesse",
            "distance": "Distance",
            "just_now": "À L'INSTANT"
        },
        "goal": {
            "headline": "BUT ! {player} DÉBLOQUE LE MATCH !",
            "why": "Exploite une structure défensive déséquilibrée avec {team} trouvant le surnombre central. La finition intervient après avoir transpercé le bloc adverse.",
            "tactical": "Frappe puissante à {speed} km/h suite à une pression territoriale soutenue dans la zone décisive.",
            "commentary": "BUT ! {player} frappe au fond des filets ({speed} km/h) pour {team} !"
        },
        "shot": {
            "headline": "Frappe Puissante de {player} ({speed} km/h)",
            "why": "La vitesse élevée ({speed} km/h) a surpris la défense. Met en évidence l'incapacité du double pivot adverse à contester le second ballon.",
            "tactical": "Frappe verticale agressive générant une menace immédiate sur le but.",
            "commentary": "{player} prend sa chance à {dist}m ! Frappe féroce ({speed} km/h) vers le but."
        },
        "line_break": {
            "headline": "Passe Cassant les Lignes par {player}",
            "why": "Élimine 2 lignes défensives avec une passe d'une précision chirurgicale, projetant le jeu dans le dernier tiers avant le repli adverse.",
            "tactical": "Superbe vision dans l'intervalle intérieur, déstabilisant complètement le bloc adverse.",
            "commentary": "Superbe passe cassant les lignes ! {player} trouve son coéquipier dans l'intervalle ({dist}m)."
        },
        "tackle": {
            "headline": "Récupération Sous Pression : {player}",
            "why": "Déclenche un contre-pressing immédiat. Perturbe la relance adverse et transforme la posture défensive en transition rapide.",
            "tactical": "Anticipation décisive dans la ligne de passe avec une intensité maximale ({press}% pression).",
            "commentary": "Tacle autoritaire de {player} qui récupère le ballon proprement."
        },
        "routine": {
            "headline": "{player} Contrôle le Rythme",
            "why": "Conserve la possession et dicte le tempo tout en éprouvant la rigueur du bloc défensif adverse.",
            "tactical": "Circulation fluide du ballon ({speed} km/h) pour étirer les lignes adverses.",
            "commentary": "{player} fait circuler le jeu avec une passe appliquée de {dist}m."
        }
    },
    "es": {
        "labels": {
            "why_it_matters": "¿POR QUÉ ES CLAVE? :",
            "tactical_context": "ANÁLISIS TÁCTICO",
            "stream": "Transmisión:",
            "all_updates": "Todas las Actualizaciones",
            "ai_insights": "Análisis IA",
            "play_by_play": "Minuto a Minuto",
            "speed": "Velocidad",
            "distance": "Distancia",
            "just_now": "AHORA MISMO"
        },
        "goal": {
            "headline": "¡GOLAZO! {player} ABRE EL MARCADOR",
            "why": "Aprovechó una estructura defensiva desorganizada, encontrando la superioridad central para {team}. La definición llega tras romper la contención rival.",
            "tactical": "Disparo ejecutado a {speed} km/h tras una presión territorial asfixiante.",
            "commentary": "¡GOL! {player} manda el balón al fondo de la red ({speed} km/h) para {team}!"
        },
        "shot": {
            "headline": "Disparo Potente de {player} ({speed} km/h)",
            "why": "La velocidad del remate ({speed} km/h) superó el repliegue defensivo. Demuestra la lentitud del doble pivote rival para tapar el tiro.",
            "tactical": "Disparo vertical agresivo que genera peligro inmediato en el área rival.",
            "commentary": "¡{player} dispara con potencia desde {dist}m ({speed} km/h) hacia la portería!"
        },
        "line_break": {
            "headline": "Pase Entre Líneas de {player}",
            "why": "Superó 2 líneas de contención con un pase milimétrico, llevando el juego al último tercio antes de la reorganización rival.",
            "tactical": "Gran visión por el pasillo interior, desarmando por completo el bloque rival.",
            "commentary": "¡Pase quirúrgico entre líneas! {player} conecta hacia adelante con precisión ({dist}m)."
        },
        "tackle": {
            "headline": "Recuperación Tras Presión Alta: {player}",
            "why": "Provocó una trampa de presión inmediata. Corta la salida limpia del rival y convierte la acción en ataque prometedor.",
            "tactical": "Anticipó la línea de pase con enorme agresividad defensiva ({press}% presión).",
            "commentary": "Entrada limpia y oportuna de {player} cortando el ataque rival."
        },
        "routine": {
            "headline": "{player} Marca el Ritmo del Juego",
            "why": "Mantiene la posesión y maneja los tiempos poniendo a prueba la disciplina del bloque rival.",
            "tactical": "Circulación del balón a {speed} km/h para ensanchar el campo.",
            "commentary": "{player} distribuye con criterio hacia su compañero ({dist}m)."
        }
    },
    "ar": {
        "labels": {
            "why_it_matters": "لماذا هذا مهم؟ :",
            "tactical_context": "السياق التكتيكي",
            "stream": "البث المباشر:",
            "all_updates": "كافة التحديثات",
            "ai_insights": "تحليلات الذكاء الاصطناعي",
            "play_by_play": "وصف تفصيلي",
            "speed": "السرعة",
            "distance": "المسافة",
            "just_now": "الآن"
        },
        "goal": {
            "headline": "هدف رائع! {player} يفتتح التسجيل !",
            "why": "استغلال مثالي للخلل في التمركز الدفاعي، مما منح {team} الزيادة العددية في العمق وإنهاء دقيق بعد اختراق خطوط الدفاع.",
            "tactical": "تسديدة صاروخية بسرعة {speed} كم/ساعة بعد ضغط هجومي متواصل.",
            "commentary": "هدف! {player} يسكن الكرة الشباك بقوة ({speed} كم/ساعة) لصالح {team}!"
        },
        "shot": {
            "headline": "تسديدة صاروخية من {player} ({speed} كم/س)",
            "why": "السرعة العالية للتسديدة ({speed} كم/ساعة) فاجأت الحارس والدفاع، وتكشف ثغرة واضحة في التغطية أمام المنطقة.",
            "tactical": "تسديدة هجومية مباشرة شكلت خطورة بالغة على مرمى الخصم.",
            "commentary": "{player} يطلق تسديدة قوية ومباغتة من مسافة {dist}م نحو المرمى!"
        },
        "line_break": {
            "headline": "تمريرة كاسرة للخطوط من {player}",
            "why": "تجاوزت خطين دفاعيين بتمريرة دقيقة جداً، لتنقل الكرة للثلث الأخير قبل تنظيم الدفاع.",
            "tactical": "رؤية ميدانية استثنائية عبر العمق لفك التكتل الدفاعي بذكاء.",
            "commentary": "تمريرة سحرية تكسر الخطوط الدفاعية ببراعة من {player} ({dist}م)!"
        },
        "tackle": {
            "headline": "استرجاع الكرة بضغط عالٍ: {player}",
            "why": "تطبيق ناجح لمصيدة الضغط العالي، وإحباط بناء هجمة الخصم والتحول السريع إلى هجوم معاكس.",
            "tactical": "قراءة ممتازة لمسار التمرير وتدخل دفاعي حاسم في الوقت المناسب.",
            "commentary": "تدخل دفاعي رائع وحاسم من {player} لاستعادة السيطرة على الكرة."
        },
        "routine": {
            "headline": "{player} يتحكم في إيقاع اللعب",
            "why": "الحفاظ على الاستحواذ وتسيير رتم المباراة لاختبار انضباط دفاع الخصم.",
            "tactical": "تدوير سلس للكرة بسرعة {speed} كم/ساعة لخلخلة تمركز المنافس.",
            "commentary": "{player} ينقل الكرة بدقة متناهية لمسافة {dist}م."
        }
    },
    "ja": {
        "labels": {
            "why_it_matters": "勝負の分かれ目 :",
            "tactical_context": "戦術的背景",
            "stream": "タイムライン:",
            "all_updates": "全アップデート",
            "ai_insights": "AI戦術インサイト",
            "play_by_play": "実況テキスト",
            "speed": "球速",
            "distance": "距離",
            "just_now": "たった今"
        },
        "goal": {
            "headline": "ゴール！{player}の先制弾！",
            "why": "相手守備のギャップを見逃さず中央を攻略。プレッシャーラインを突破した見事なフィニッシュで{team}が主導権を握ります。",
            "tactical": "時速{speed}kmの強烈なシュート。決定的なチャンスを確実に仕留めました。",
            "commentary": "ゴーーール！{player}が豪快にネットを揺らしました ({speed} km/h)！"
        },
        "shot": {
            "headline": "{player}の強烈なシュート ({speed} km/h)",
            "why": "時速{speed}kmの弾道が相手のブロックを突破。バイタルエリアでのプレッシャー遅れを鋭く突きました。",
            "tactical": "積極的な縦への仕掛けから生まれた高脅威のシュート。",
            "commentary": "{player}が{dist}mの位置から強烈なシュート ({speed} km/h) を放ちます！"
        },
        "line_break": {
            "headline": "{player}のラインブレイクパス",
            "why": "相手の2ラインを貫通する高難度パス。一気にアタッキングサードへボールを運び陣形を崩しました。",
            "tactical": "インサイドハーフのスペースを見通した見事な崩しの起点。",
            "commentary": "見事なラインブレイクパス！{player}が敵陣を切り裂きます ({dist}m)。"
        },
        "tackle": {
            "headline": "ハイプレスからのボール奪取: {player}",
            "why": "連動したプレッシングトラップが的中。相手のビルドアップを寸断し即座にカウンターへ移行。",
            "tactical": "パスコースを読み切った素早い出足でクリーンにボールを奪取。",
            "commentary": "{player}が鋭いタックルでボールを奪い返しました！"
        },
        "routine": {
            "headline": "{player}がリズムを支配",
            "why": "ポゼッションを維持しながら相手ブロックの隙を伺い、ゲームの主導権を握ります。",
            "tactical": "時速{speed}kmのスムーズなボール循環で相手陣形を揺さぶります。",
            "commentary": "{player}が味方へ正確なパス ({dist}m) を通します。"
        }
    }
}

class AzureMultilingualTranslator:
    """
    Translates match narratives in real-time.
    Supports Azure AI Translator REST API with fallback to specialized football templates.
    """
    def __init__(self):
        self.api_key = os.getenv("AZURE_TRANSLATOR_KEY")
        self.endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")
        self.region = os.getenv("AZURE_TRANSLATOR_REGION", "eastus")

    def get_bundle_translation(
        self,
        category: str,
        player_name: str,
        team_name: str,
        speed: float,
        dist: float,
        press: int,
        target_lang: str
    ) -> Dict[str, str]:
        """Translates headline, why_it_matters, and tactical_explanation for a given language."""
        if target_lang not in TRANSLATION_TEMPLATES:
            return {}

        lang_data = TRANSLATION_TEMPLATES[target_lang]
        cat_data = lang_data.get(category, lang_data["routine"])

        params = {
            "player": player_name,
            "team": team_name,
            "speed": f"{speed:.1f}",
            "dist": f"{dist:.1f}",
            "press": str(press)
        }

        return {
            "headline": cat_data["headline"].format(**params),
            "why_it_matters": cat_data["why"].format(**params),
            "tactical_explanation": cat_data["tactical"].format(**params)
        }

    def get_commentary_translation(
        self,
        category: str,
        player_name: str,
        team_name: str,
        speed: float,
        dist: float,
        target_lang: str
    ) -> str:
        """Translates the play-by-play commentary line."""
        if target_lang not in TRANSLATION_TEMPLATES:
            return ""

        cat_data = TRANSLATION_TEMPLATES[target_lang].get(category, TRANSLATION_TEMPLATES[target_lang]["routine"])
        return cat_data["commentary"].format(
            player=player_name,
            team=team_name,
            speed=f"{speed:.1f}",
            dist=f"{dist:.1f}",
            press="75"
        )

    async def translate_text(self, text: str, target_lang: str) -> str:
        """Translates arbitrary text via Azure Translator if available."""
        if target_lang == "en":
            return text

        if self.api_key and "placeholder" not in self.api_key:
            try:
                url = f"{self.endpoint.rstrip('/')}/translate?api-version=3.0&to={target_lang}"
                headers = {
                    "Ocp-Apim-Subscription-Key": self.api_key,
                    "Ocp-Apim-Subscription-Region": self.region,
                    "Content-Type": "application/json"
                }
                body = [{"text": text}]
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.post(url, headers=headers, json=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data[0]["translations"][0]["text"]
            except Exception as e:
                logger.warning(f"Azure Translator call failed ({e}); using template generator.")

        return text
