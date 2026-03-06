"""
Validator — three-layer input validation pipeline for MACS.

LAYER 1  SENSOR  — seismic/weather/environmental sensors (ground truth)
LAYER 2  API     — institutional feeds: EONET, govt alerts (institutional truth)
LAYER 3  CROWD   — citizen field reports (human truth, needs corroboration)

The validator cross-references crowd reports against SENSOR + API events
to produce a corroboration score.  This is the system's core moat:
agents never act on unvalidated single-source intel.

Mock mode : keyword-based domain/severity classifier (no API key needed).
Live mode : Gemini reads the report + bulletin context and returns JSON.
"""

import json
import logging
import os
import time
from dataclasses import asdict
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

LIVE_SYSTEM_PROMPT = """You are a crisis information validator for MACS (Multi-Agent Crisis Response System).
You operate a THREE-LAYER validation pipeline:
  SENSOR layer — seismic, weather, environmental ground truth (highest trust)
  API layer    — institutional feeds like EONET, govt alerts (high trust)
  CROWD layer  — citizen reports (must be corroborated to be trusted)

Evaluate the submitted field report. Your job:
1. Determine credibility (not spam, not a test, not incoherent)
2. Classify domain and severity
3. Check if the report is CORROBORATED by SENSOR or API evidence provided
4. Rewrite as a clear, actionable operational message (≤100 words)
5. If corroborated, note which events corroborate it
Respond ONLY with valid JSON. No markdown, no explanation."""

LIVE_USER_PROMPT = """Current bulletin board context (last 10 events):
{context}

Recent SENSOR + API events for corroboration:
{sensor_api_context}

Submitted field report (CROWD layer):
  Location: {location}
  Message: {message}

Classify and respond with JSON:
{{
  "credible": true/false,
  "domain": "MEDICAL|LOGISTICS|POWER|COMMS|EVACUATION|SYSTEM",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "message": "clear rewritten message for MACS (≤100 words)",
  "confidence": 0.0-1.0,
  "corroborated": true/false,
  "corroborated_by": ["event_id1", "event_id2"],
  "corroboration_score": 0.0-1.0,
  "reject_reason": "reason if not credible, else empty string"
}}"""

# ── Corroboration domain mapping ──────────────────────────────────────────────
# Maps CROWD report domains → event types from SENSOR/API layers that can
# corroborate them.

CORROBORATION_MAP = {
    "MEDICAL":    {"SEISMIC_ACTIVITY", "NATURAL_HAZARD_EVENT", "WEATHER_ALERT", "CRISIS_ALERT", "INFRASTRUCTURE_FAILURE"},
    "POWER":      {"SEISMIC_ACTIVITY", "WEATHER_ALERT", "WEATHER_STATUS", "NATURAL_HAZARD_EVENT", "CRISIS_ALERT", "INFRASTRUCTURE_FAILURE"},
    "COMMS":      {"SEISMIC_ACTIVITY", "WEATHER_ALERT", "NATURAL_HAZARD_EVENT", "CRISIS_ALERT", "INFRASTRUCTURE_FAILURE"},
    "LOGISTICS":  {"SEISMIC_ACTIVITY", "WEATHER_ALERT", "WEATHER_STATUS", "NATURAL_HAZARD_EVENT", "CRISIS_ALERT", "INFRASTRUCTURE_FAILURE"},
    "EVACUATION": {"SEISMIC_ACTIVITY", "WEATHER_ALERT", "NATURAL_HAZARD_EVENT", "CRISIS_ALERT", "INFRASTRUCTURE_FAILURE"},
}

# How much each source layer contributes to corroboration score
LAYER_WEIGHTS = {
    "SENSOR": 0.45,   # Ground truth — highest weight
    "API":    0.35,   # Institutional truth
    "SYSTEM": 0.30,   # Scenario/system events — simulation ground truth
    "CROWD":  0.15,   # Other citizen reports
    "AGENT":  0.05,   # Agent analysis (derivative, low weight)
}

# Time window (seconds) for corroboration — events must be recent
CORROBORATION_WINDOW = 600  # 10 minutes


class Verifier:
    """Three-layer input validator with corroboration engine."""

    def __init__(self, mock_mode: bool = True, anthropic_api_key: str = None,
                 google_api_key: str = None, bulletin=None):
        self.mock_mode = mock_mode
        self._client  = None  # Anthropic
        self._gclient = None  # Gemini
        self._bulletin = bulletin  # Reference to shared bulletin board

        if not mock_mode:
            if google_api_key and _GOOGLE_AVAILABLE:
                self._gclient = google_genai.Client(api_key=google_api_key)
                logger.info(f"[VALIDATOR] Live mode — using Gemini model: {GEMINI_MODEL}")
            elif anthropic_api_key:
                try:
                    import anthropic
                    self._client = anthropic.Anthropic(api_key=anthropic_api_key)
                    logger.info("[VALIDATOR] Live mode — using Claude Haiku")
                except ImportError:
                    logger.warning("[VALIDATOR] Anthropic SDK not available — falling back to mock")

    def set_bulletin(self, bulletin):
        """Set bulletin board reference for corroboration lookups."""
        self._bulletin = bulletin

    def verify(self, message: str, location: str = "", context: list = None) -> dict:
        """Validate and classify a citizen report with corroboration."""
        if self._gclient:
            result = self._gemini_verify(message, location, context or [])
        elif self._client:
            result = self._live_verify(message, location, context or [])
        else:
            result = self._mock_verify(message, location)

        # Always run corroboration engine on credible reports
        if result.get("credible") and self._bulletin:
            corr = self._corroborate(result, message, location)
            result["corroborated_by"] = corr["matching_event_ids"]
            result["corroboration_score"] = corr["score"]
            # Boost confidence when corroborated by hard evidence
            if corr["score"] > 0.3:
                result["confidence"] = min(result["confidence"] + corr["score"] * 0.3, 0.99)

        return result

    # ── Corroboration engine (the moat) ───────────────────────────────────────

    def _corroborate(self, result: dict, message: str, location: str) -> dict:
        """Cross-reference a crowd report against SENSOR + API events.

        Returns:
            {"score": float 0-1, "matching_event_ids": [str], "layers_matched": [str]}
        """
        domain = result.get("domain", "SYSTEM")
        now = time.time()
        matching_ids = []
        layers_matched = set()
        raw_score = 0.0

        # Get corroborating event types for this domain
        corr_types = CORROBORATION_MAP.get(domain, set())
        if not corr_types:
            return {"score": 0.0, "matching_event_ids": [], "layers_matched": []}

        # Scan recent bulletin events for corroboration
        try:
            recent = self._bulletin.snapshot(max_events=100)
        except Exception:
            return {"score": 0.0, "matching_event_ids": [], "layers_matched": []}

        for event in recent:
            # Accept SENSOR, API, SYSTEM (scenario events) as corroboration
            layer = event.get("source_layer", "SYSTEM")
            if layer not in ("SENSOR", "API", "SYSTEM"):
                continue

            # Must be a corroborating event type
            if event.get("event_type") not in corr_types:
                continue

            # Must be within the time window
            try:
                evt_time = event.get("timestamp", 0)
                if isinstance(evt_time, str):
                    from datetime import datetime
                    evt_time = datetime.fromisoformat(evt_time).timestamp()
                if now - evt_time > CORROBORATION_WINDOW:
                    continue
            except (ValueError, TypeError):
                pass  # Can't parse time — still count it if it's in recent snapshot

            # Match! Add this event as corroboration
            weight = LAYER_WEIGHTS.get(layer, 0.05)
            raw_score += weight
            matching_ids.append(event.get("id", "unknown"))
            layers_matched.add(layer)

        # Normalize: cap at 1.0, and give bonus if multiple layers agree
        multi_layer_bonus = 0.15 if len(layers_matched) > 1 else 0.0
        final_score = round(min(raw_score + multi_layer_bonus, 1.0), 2)

        return {
            "score": final_score,
            "matching_event_ids": matching_ids[:5],  # Limit to 5 IDs
            "layers_matched": list(layers_matched),
        }

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
        # Extract SENSOR + API events for the LLM to reference
        sensor_api = [e for e in context if e.get("source_layer") in ("SENSOR", "API")]
        sensor_api_str = json.dumps(sensor_api[-10:], indent=2) if sensor_api else "None available"
        user_msg = LIVE_USER_PROMPT.format(
            context=ctx_str,
            sensor_api_context=sensor_api_str,
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
                    max_output_tokens=400,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            logger.warning(f"[VALIDATOR] Gemini error: {e} — falling back to mock")
            return self._mock_verify(message, location)

    # ── Live verifier (Claude Haiku) ──────────────────────────────────────────

    def _live_verify(self, message: str, location: str, context: list) -> dict:
        ctx_str = json.dumps(context[-10:], indent=2)
        sensor_api = [e for e in context if e.get("source_layer") in ("SENSOR", "API")]
        sensor_api_str = json.dumps(sensor_api[-10:], indent=2) if sensor_api else "None available"
        user_msg = LIVE_USER_PROMPT.format(
            context=ctx_str,
            sensor_api_context=sensor_api_str,
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
            logger.warning(f"[VALIDATOR] Live error: {e} — falling back to mock")
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
