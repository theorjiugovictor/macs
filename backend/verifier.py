"""
Verifier — filters and classifies citizen field reports before bulletin ingestion.

Mock mode : keyword-based domain/severity classifier (no API key needed).
Live mode : Gemini reads the report + bulletin context and returns JSON.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from google import genai as google_genai
    from google.genai import types as google_types
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

# ── Keyword maps ──────────────────────────────────────────────────────────────

DOMAIN_KEYWORDS = {
    "MEDICAL":    ["hospital", "medical", "wounded", "injury", "blood", "doctor",
                   "nurse", "casualty", "casualties", "dead", "dying", "sick",
                   "disease", "ambulance", "triage", "surgery", "patient",
                   "medicine", "clinic", "health", "paramedic", "first aid"],
    "LOGISTICS":  ["road", "bridge", "convoy", "supplies", "food", "water", "truck",
                   "route", "blocked", "delivery", "aid", "cargo", "distribution",
                   "warehouse", "supply", "transport", "fuel", "shortage", "vehicle"],
    "POWER":      ["power", "electricity", "generator", "blackout", "grid", "lights",
                   "battery", "energy", "outage", "dark", "no power", "electric"],
    "COMMS":      ["radio", "signal", "communication", "phone", "network", "internet",
                   "connection", "relay", "broadcast", "contact", "reach", "satellite"],
    "EVACUATION": ["evacuate", "evacuation", "flee", "shelter", "civilian", "escape",
                   "bus", "trapped", "stranded", "safe zone", "move", "displaced",
                   "refugees", "crowd", "people leaving"],
}

CRITICAL_WORDS = ["critical", "dying", "immediately", "emergency", "life-threatening",
                  "fatal", "mass", "explosion", "strike", "attack", "NOW", "urgent now"]
HIGH_WORDS     = ["danger", "dangerous", "urgent", "help", "trapped", "serious",
                  "severe", "many", "multiple", "heavy", "lots of", "need help"]
SPAM_SIGNALS   = ["test", "testing", "hello", "hi", "abc", "123", "lol", "haha", "qwerty"]

LIVE_SYSTEM_PROMPT = """You are a crisis information verifier for MACS (Multi-Agent Crisis Response System).
Evaluate submitted field reports from civilians and field workers. Your job:
1. Determine credibility (not spam, not a test, not incoherent)
2. Classify domain and severity
3. Rewrite as a clear, actionable operational message (≤100 words)
Respond ONLY with valid JSON. No markdown, no explanation."""

LIVE_USER_PROMPT = """Current bulletin board context (last 10 events):
{context}

Submitted field report:
  Location: {location}
  Message: {message}

Classify and respond with JSON:
{{
  "credible": true/false,
  "domain": "MEDICAL|LOGISTICS|POWER|COMMS|EVACUATION|SYSTEM",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "message": "clear rewritten message for MACs (≤100 words)",
  "confidence": 0.0-1.0,
  "reject_reason": "reason if not credible, else empty string"
}}"""


class Verifier:
    def __init__(self, mock_mode: bool = True, anthropic_api_key: str = None,
                 google_api_key: str = None):
        self.mock_mode = mock_mode
        self._client  = None  # Anthropic
        self._gclient = None  # Gemini

        if not mock_mode:
            if google_api_key and _GOOGLE_AVAILABLE:
                self._gclient = google_genai.Client(api_key=google_api_key)
                logger.info(f"[VERIFIER] Live mode — using Gemini model: {GEMINI_MODEL}")
            elif anthropic_api_key:
                try:
                    import anthropic
                    self._client = anthropic.Anthropic(api_key=anthropic_api_key)
                    logger.info("[VERIFIER] Live mode — using Claude Haiku")
                except ImportError:
                    logger.warning("[VERIFIER] Anthropic SDK not available — falling back to mock")

    def verify(self, message: str, location: str = "", context: list = None) -> dict:
        """Verify and classify a citizen report. Returns structured result dict."""
        if self._gclient:
            return self._gemini_verify(message, location, context or [])
        if self._client:
            return self._live_verify(message, location, context or [])
        return self._mock_verify(message, location)

    # ── Mock verifier ─────────────────────────────────────────────────────────

    def _mock_verify(self, message: str, location: str) -> dict:
        text = (message + " " + location).lower()

        if len(message.strip()) < 10:
            return self._reject("Message too short to act on")
        if any(w in text for w in SPAM_SIGNALS) and len(message) < 40:
            return self._reject("Appears to be a test or spam submission")

        # Score each domain by keyword hits
        domain_scores = {
            domain: sum(1 for kw in keywords if kw in text)
            for domain, keywords in DOMAIN_KEYWORDS.items()
        }
        matched = {d: s for d, s in domain_scores.items() if s > 0}
        domain = max(matched, key=matched.get) if matched else "SYSTEM"

        # Severity
        if any(w in text for w in CRITICAL_WORDS):
            severity = "CRITICAL"
        elif any(w in text for w in HIGH_WORDS):
            severity = "HIGH"
        else:
            severity = "MEDIUM"

        # Confidence scales with how many keywords matched
        top_score = max(matched.values()) if matched else 0
        confidence = round(min(0.55 + top_score * 0.08, 0.95), 2)

        clean = message.strip()
        if location:
            clean = f"[{location}] {clean}"

        return {
            "credible": True,
            "domain": domain,
            "severity": severity,
            "message": clean[:200],
            "confidence": confidence,
            "reject_reason": "",
        }

    # ── Live verifier (Gemini) ───────────────────────────────────────────────

    def _gemini_verify(self, message: str, location: str, context: list) -> dict:
        ctx_str = json.dumps(context[-10:], indent=2)
        user_msg = LIVE_USER_PROMPT.format(
            context=ctx_str,
            location=location or "unknown",
            message=message,
        )
        try:
            response = self._gclient.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_msg,
                config=google_types.GenerateContentConfig(
                    system_instruction=LIVE_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    max_output_tokens=300,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            logger.warning(f"[VERIFIER] Gemini error: {e} — falling back to mock")
            return self._mock_verify(message, location)

    # ── Live verifier (Claude Haiku) ──────────────────────────────────────────

    def _live_verify(self, message: str, location: str, context: list) -> dict:
        ctx_str = json.dumps(context[-10:], indent=2)
        user_msg = LIVE_USER_PROMPT.format(
            context=ctx_str,
            location=location or "unknown",
            message=message,
        )
        try:
            response = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system=LIVE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.warning(f"[VERIFIER] Live error: {e} — falling back to mock")
            return self._mock_verify(message, location)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _reject(self, reason: str) -> dict:
        return {
            "credible": False,
            "domain": "",
            "severity": "",
            "message": "",
            "confidence": 0.0,
            "reject_reason": reason,
        }
