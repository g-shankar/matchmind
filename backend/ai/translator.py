import os
import httpx
import logging
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("pitchpulse.translator")

# High-fidelity multilingual football vocabulary dictionary for instant zero-latency localization
OFFLINE_DICTIONARY = {
    "es": {
        "GOAL!": "¡GOLAZO!",
        "Line-Breaking Pass": "Pase Entre Líneas",
        "High-Pressure Turnaround": "Recuperación Tras Presión Alta",
        "Fires Stunner": "Disparo Potente",
        "Orchestrates Rhythm": "Marca el Ritmo del Juego",
        "Why It Matters": "¿Por qué es clave?",
        "Tactical Context": "Contexto Táctico",
        "Control vs Chaos": "Control vs Caos",
        "Speed": "Velocidad",
        "Distance": "Distancia",
        "Pass Difficulty": "Dificultad de Pase"
    },
    "fr": {
        "GOAL!": "BUT MAGNIFIQUE !",
        "Line-Breaking Pass": "Passe Cassant les Lignes",
        "High-Pressure Turnaround": "Récupération Sous Pression",
        "Fires Stunner": "Frappe Puissante",
        "Orchestrates Rhythm": "Maître du Rythme",
        "Why It Matters": "Pourquoi c'est décisif",
        "Tactical Context": "Contexte Tactique",
        "Control vs Chaos": "Contrôle vs Chaos",
        "Speed": "Vitesse",
        "Distance": "Distance",
        "Pass Difficulty": "Difficulté de Passe"
    },
    "ar": {
        "GOAL!": "هدف رائع!",
        "Line-Breaking Pass": "تمريرة كاسرة للخطوط",
        "High-Pressure Turnaround": "استرجاع الكرة بضغط عالٍ",
        "Fires Stunner": "تسديدة صاروخية",
        "Orchestrates Rhythm": "يتحكم في إيقاع المباراة",
        "Why It Matters": "لماذا هذا مهم؟",
        "Tactical Context": "السياق التكتيكي",
        "Control vs Chaos": "السيطرة مقابل الفوضى",
        "Speed": "السرعة",
        "Distance": "المسافة",
        "Pass Difficulty": "صعوبة التمريرة"
    },
    "ja": {
        "GOAL!": "ゴール！圧巻のフィニッシュ！",
        "Line-Breaking Pass": "ラインブレイクパス",
        "High-Pressure Turnaround": "ハイプレスからのボール奪取",
        "Fires Stunner": "強烈なシュート",
        "Orchestrates Rhythm": "ゲームのリズムを支配",
        "Why It Matters": "勝負の分かれ目",
        "Tactical Context": "戦術的背景",
        "Control vs Chaos": "支配 vs 混沌",
        "Speed": "速度",
        "Distance": "走行距離",
        "Pass Difficulty": "パス難易度"
    }
}

class AzureMultilingualTranslator:
    """
    Translates match narratives in real-time.
    Supports Azure AI Translator REST API with fallback to specialized football lexicon.
    """
    def __init__(self):
        self.api_key = os.getenv("AZURE_TRANSLATOR_KEY")
        self.endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")
        self.region = os.getenv("AZURE_TRANSLATOR_REGION", "eastus")

    async def translate_text(self, text: str, target_lang: str) -> str:
        """Translates headline or narrative snippet into target language."""
        if target_lang == "en":
            return text

        # 1. Try Live Azure AI Translator
        if self.api_key and "placeholder" not in self.api_key:
            try:
                url = f"{self.endpoint.rstrip('/')}/translate?api-version=3.0&to={target_lang}"
                headers = {
                    "Ocp-Apim-Subscription-Key": self.api_key,
                    "Ocp-Apim-Subscription-Region": self.region,
                    "Content-Type": "application/json"
                }
                body = [{"text": text}]
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.post(url, headers=headers, json=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data[0]["translations"][0]["text"]
            except Exception as e:
                logger.warning(f"Azure Translator call failed ({e}); using offline dictionary.")

        # 2. Offline Football Dictionary / Localization Fallback
        lang_dict = OFFLINE_DICTIONARY.get(target_lang, {})
        for eng_phrase, localized_phrase in lang_dict.items():
            if eng_phrase.lower() in text.lower():
                return f"[{target_lang.upper()}] {localized_phrase}: {text}"

        return f"[{target_lang.upper()}] {text}"
