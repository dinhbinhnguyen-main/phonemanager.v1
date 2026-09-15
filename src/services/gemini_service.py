# src/services/gemini_service.py
import os
import re
import requests
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from src.utils.logger import logger
from src.utils.ai_prompt_helper import AIPromptHelper


class GeminiService:
    """
    Service for interacting with Google Gemini API to rewrite content,
    titles, and descriptions using generative AI.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or self._get_api_key()
        self.model = "gemini-3.5-flash"
        # Fallback models if primary model is busy or unavailable
        self.fallback_models = ["gemini-3.1-flash-lite", "gemini-3.6-flash"]

    def _get_api_key(self) -> str:
        """
        Retrieves Gemini API Key from environment variable, .env file, or system settings.
        """
        key = os.getenv("GEMINI_API_KEY", "")
        if key:
            return key.strip()

        # Try reading from .env in project root
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
            except Exception as e:
                logger.debug(f"Could not read .env for GEMINI_API_KEY: {e}")

        return ""

    def _clean_response(self, text: str) -> str:
        """
        Cleans up conversational filler, quotes, or markdown code blocks returned by Gemini.
        """
        if not text:
            return ""

        # 1. Remove markdown code blocks if wrapped
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

        # 2. Remove wrapping quotes
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1].strip()

        # 3. Strip common conversational prefixes
        prefixes_to_strip = [
            r"^dưới đây là[^:\n]*[:\n]*",
            r"^đây là[^:\n]*[:\n]*",
            r"^bài viết thảo luận[^:\n]*[:\n]*",
            r"^bài viết viết lại[^:\n]*[:\n]*",
            r"^đoạn viết lại[^:\n]*[:\n]*",
            r"^gửi bạn[^:\n]*[:\n]*"
        ]
        for pattern in prefixes_to_strip:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

        return text

    def rewrite_text(self, text: str, prompt: Optional[str] = None) -> str:
        """
        Calls Gemini API to rewrite text using requests.
        """
        api_key = self.api_key or self._get_api_key()
        if not api_key:
            logger.warning("⚠️ GEMINI_API_KEY is not configured. Returning original text.")
            return text

        final_prompt = prompt if prompt else AIPromptHelper.build_general_rewrite_prompt(text)

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": final_prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.85,
                "topP": 0.95,
                "topK": 40
            }
        }

        models_to_try = [self.model] + self.fallback_models
        last_error = None

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                response = requests.post(url, json=payload, timeout=15.0)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_result = parts[0].get("text", "").strip()
                            clean_res = self._clean_response(raw_result)
                            if clean_res:
                                return clean_res
                elif response.status_code == 429:
                    logger.warning(f"⚠️ Gemini API Quota Exceeded (HTTP 429) on model {model}. Retaining original template content.")
                    # 429 indicates project/key rate limit or quota exceeded; break early to avoid wasted timeouts
                    return text
                else:
                    logger.debug(f"Gemini model {model} returned status {response.status_code}: {response.text}")
                    last_error = f"HTTP {response.status_code}: {response.text}"
            except Exception as e:
                logger.debug(f"Error calling Gemini with model {model}: {e}")
                last_error = str(e)

        logger.warning(f"⚠️ Gemini rewrite failed ({last_error or 'no valid response'}). Falling back to original template content.")
        return text

    def rewrite_real_estate(
        self, 
        raw_title: str, 
        raw_desc: str
    ) -> Tuple[str, str]:
        """
        Rewrites both Title and Description for Real Estate listings using Gemini AI.
        If Gemini is unavailable or fails, returns the original template (raw_title, raw_desc).

        Returns:
            Tuple[str, str]: (rewritten_title, rewritten_description)
        """
        api_key = self.api_key or self._get_api_key()
        if not api_key:
            logger.warning("⚠️ GEMINI_API_KEY is not configured. Retaining original Title & Description from template.")
            return raw_title, raw_desc

        prompt = AIPromptHelper.build_real_estate_rewrite_prompt(raw_title, raw_desc)
        logger.info("🤖 Using Gemini AI to rewrite listing Title and Description...")

        try:
            raw_response = self.rewrite_text(text=raw_desc, prompt=prompt)
            if raw_response and raw_response.strip() and raw_response != raw_desc:
                rewritten_title, rewritten_desc = AIPromptHelper.parse_real_estate_rewrite_response(
                    raw_response, 
                    default_title=raw_title, 
                    default_desc=raw_desc
                )
                if rewritten_title or rewritten_desc:
                    logger.info(f"✨ Gemini AI rewritten successfully! New title: '{rewritten_title[:40]}...'")
                    return rewritten_title or raw_title, rewritten_desc or raw_desc
        except Exception as e:
            logger.warning(f"⚠️ Error during Gemini AI rewrite: {e}. Falling back to original template content.")

        logger.info("ℹ️ Using original Title & Description generated from Template.")
        return raw_title, raw_desc

