"""
Visa Requirements Checker — checks entry requirements for Israeli passport holders.
"""
import json
import re
import anthropic

_lang = "he"

VISA_PROMPT = """Check entry requirements for Israeli passport holders to the country/city: {destination}

Please provide accurate and current information about:
1. Is a visa required?
2. Is there Visa On Arrival?
3. Is there an eVisa (electronic visa)?
4. Maximum stay without a visa
5. Visa cost (if required)
6. Visa processing time
7. Required documents
8. Important notes (including diplomatic relations with Israel)

Return JSON:
{{
  "destination": "country/city name",
  "country_code": "XX",
  "visa_required": true/false,
  "visa_on_arrival": true/false,
  "e_visa": true/false,
  "visa_free": true/false,
  "max_stay_days": 0,
  "visa_cost_usd": 0,
  "processing_days": 0,
  "status": "visa_free" / "visa_on_arrival" / "e_visa" / "visa_required" / "not_allowed",
  "status_label": "status description",
  "requirements": ["document 1", "document 2"],
  "important_notes": ["important note 1", "important note 2"],
  "embassy_info": "embassy/consulate information",
  "last_updated": "YYYY-MM",
  "confidence": "high" / "medium" / "low",
  "source": "information source"
}}

Note: Current information for 2025-2026. If there are no diplomatic relations with Israel, mention it."""


def check_visa(destination: str, passport: str = "Israeli") -> dict:
    """
    Check visa requirements for the given destination for Israeli passport holders.
    """
    client = anthropic.Anthropic()

    prompt = VISA_PROMPT.format(destination=destination)

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            system="You are an expert in entry requirements and passports. Provide accurate and current information only." + (" Respond in English. Use English for all text fields in the JSON." if _lang == "en" else ""),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}


def check_multiple(destinations: list) -> list:
    """Check visa requirements for multiple destinations at once."""
    results = []
    for dest in destinations:
        result = check_visa(dest)
        result["destination_query"] = dest
        results.append(result)
    return results


STATUS_CONFIG = {
    "visa_free":       {"icon": "✅", "color": "#00ff88", "label": "ללא ויזה"},
    "visa_on_arrival": {"icon": "🟡", "color": "#ffd93d", "label": "ויזה בהגעה"},
    "e_visa":          {"icon": "🔵", "color": "#74b9ff", "label": "eVisa"},
    "visa_required":   {"icon": "🔴", "color": "#ff6b6b", "label": "ויזה נדרשת"},
    "not_allowed":     {"icon": "⛔", "color": "#ff0000", "label": "כניסה אסורה"},
}


def get_status_config(status: str) -> dict:
    labels_en = {
        "visa_free": "Visa Free",
        "visa_on_arrival": "Visa on Arrival",
        "e_visa": "eVisa",
        "visa_required": "Visa Required",
        "not_allowed": "Entry Not Allowed",
    }
    labels_he = {
        "visa_free": "ללא ויזה",
        "visa_on_arrival": "ויזה בהגעה",
        "e_visa": "eVisa",
        "visa_required": "ויזה נדרשת",
        "not_allowed": "כניסה אסורה",
    }
    base = STATUS_CONFIG.get(status, {"icon": "❓", "color": "#aaa", "label": "לא ידוע"})
    if _lang == "en":
        label = labels_en.get(status, "Unknown")
        return {**base, "label": label}
    return base
