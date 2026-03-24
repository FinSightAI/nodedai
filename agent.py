"""
Claude-powered price search agent.
Strategy:
  1. Amadeus API (רשמי, מדויק) — לטיסות ומלונות
  2. Claude + web_search (fallback) — לכל השאר / אם Amadeus לא מוגדר
"""
import json
import re
import os
from datetime import datetime
from typing import Optional

import anthropic
import amadeus_client

# ── Claude client ──────────────────────────────────────────────────────────────
_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
    return _client


# Module-level language (set by app.py)
_lang = "he"

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT_HE = """You are a professional travel price agent. Find the best prices for flights, hotels, apartments and vacation packages.

When searching for a price:
1. Search the internet for current prices
2. Check multiple sources (Google Flights, Booking.com, Airbnb, Kayak, etc.)
3. Find the best available price

Always return valid JSON in this format:
{
  "found": true/false,
  "price": 123.45,
  "currency": "USD" / "ILS" / "EUR" etc,
  "source": "website name / source",
  "details": "deal description - airline / hotel / etc",
  "deal_quality": "excellent" / "good" / "average" / "poor",
  "notes": "important notes"
}

If no price found, return {"found": false, "reason": "reason"}

Be accurate! Realistic prices only. Do not invent prices."""


def build_search_prompt(item: dict) -> str:
    """Build a search prompt from a watch item."""
    category = item["category"]
    destination = item["destination"]
    origin = item.get("origin", "")
    date_from = item.get("date_from", "")
    date_to = item.get("date_to", "")
    custom_query = item.get("query", "")

    today = datetime.now().strftime("%Y-%m-%d")

    if custom_query:
        base = custom_query
    elif category == "flight":
        base = f"Flight from {origin} to {destination}"
        if date_from:
            base += f" on {date_from}"
        if date_to:
            base += f" return {date_to}"
    elif category == "hotel":
        base = f"Hotel in {destination}"
        if date_from:
            base += f" check-in {date_from}"
        if date_to:
            base += f" check-out {date_to}"
    elif category == "apartment":
        base = f"Apartment rental in {destination}"
        if date_from:
            base += f" from {date_from}"
        if date_to:
            base += f" to {date_to}"
    elif category == "package":
        base = f"Vacation package to {destination}"
        if origin:
            base += f" from {origin}"
        if date_from:
            base += f" {date_from}"
    else:
        base = f"Price for {destination}"

    return (
        f"Find the best price for: {base}\n"
        f"(Check date: {today})\n\n"
        f"Search for realistic, current prices. "
        f"Check Google Flights, Booking.com, Airbnb, Kayak, Skyscanner, "
        f"and Israeli sites like Gulliver, Israir, Arkia.\n\n"
        f"Return JSON in the exact format specified."
    )


def search_price(item: dict) -> dict:
    """
    Find current price for a watch item.
    Strategy: Amadeus first (accurate) → Claude web search (fallback).
    """
    category = item["category"]
    destination = item["destination"]
    origin = item.get("origin", "TLV")
    date_from = item.get("date_from")
    date_to = item.get("date_to")

    # ── Try Amadeus first ──────────────────────────────────────────────────────
    if amadeus_client.is_configured():
        if category == "flight" and date_from:
            results = amadeus_client.search_flights(
                origin=origin,
                destination=destination,
                departure_date=date_from,
                return_date=date_to,
                max_results=3,
            )
            if results:
                best = results[0]
                best["amadeus"] = True
                return best

        elif category == "hotel" and date_from and date_to:
            results = amadeus_client.search_hotels(
                city=destination,
                check_in=date_from,
                check_out=date_to,
                max_results=3,
            )
            if results:
                best = results[0]
                best["amadeus"] = True
                return best

    # ── Fallback: Claude + web search ─────────────────────────────────────────
    return _claude_web_search(item)


def _claude_web_search(item: dict) -> dict:
    """
    Use Claude Opus 4.6 with web search to find the current price for a watch item.
    Returns a dict with price info or error.
    """
    client = get_client()
    prompt = build_search_prompt(item)
    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT_HE + (" Respond in English." if _lang == "en" else " השב בעברית."),
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the final text response
        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text += block.text

        # Parse JSON from the response
        return _extract_json(result_text)

    except anthropic.RateLimitError:
        return {"found": False, "error": "rate_limit", "reason": "Rate limit"}
    except anthropic.APIError as e:
        return {"found": False, "error": "api_error", "reason": str(e)[:100]}
    except Exception as e:
        return {"found": False, "error": "unknown", "reason": str(e)[:100]}


def _extract_json(text: str) -> dict:
    """Extract JSON object from Claude's response text."""
    # Try to find JSON block
    patterns = [
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
        r"(\{[^{}]*\"found\"[^{}]*\})",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                continue

    # Try to find the last JSON-like object
    try:
        # Find the last { ... } block
        start = text.rfind("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: try to extract price with regex
    price_match = re.search(r"\b(\d{2,6}(?:[.,]\d{1,2})?)\b", text)
    if price_match:
        try:
            price = float(price_match.group(1).replace(",", ""))
            if 10 < price < 100000:
                return {
                    "found": True,
                    "price": price,
                    "currency": "USD",
                    "source": "web search",
                    "details": text[:200],
                    "deal_quality": "unknown",
                    "notes": "",
                }
        except ValueError:
            pass

    return {"found": False, "reason": "Could not parse price from response"}


def analyze_deal(item: dict, price_history: list) -> str:
    """
    Use Claude to analyze whether this is a good deal based on price history.
    """
    client = get_client()

    if len(price_history) < 2:
        return "Not enough history to analyze"

    prices = [r["price"] for r in price_history[:20]]
    avg = sum(prices) / len(prices)
    minimum = min(prices)
    maximum = max(prices)
    current = prices[0]

    prompt = f"""Analyze whether this is a good deal:
- Item: {item['name']} ({item['category']}) to {item['destination']}
- Current price: {current}
- Average (up to 20 measurements): {avg:.0f}
- Minimum seen: {minimum}
- Maximum seen: {maximum}

Give a short recommendation (2-3 sentences){" in English" if _lang == "en" else " in Hebrew"}: Should I buy now? Why?"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text.strip()
    except Exception:
        pass

    return f"Current price {current:.0f} vs average {avg:.0f}"


def smart_search_opportunities(destinations: list[str]) -> list[dict]:
    """
    Ask Claude to proactively find good travel deals to a list of destinations.
    Returns a list of opportunity dicts.
    """
    client = get_client()

    dest_str = ", ".join(destinations)
    prompt = f"""Find 3 excellent travel opportunities right now to one of these destinations: {dest_str}

Search for:
- Cheap flights
- Hotels on sale
- Vacation packages

For each opportunity return JSON:
{{
  "destination": "...",
  "type": "flight/hotel/package",
  "deal": "deal description",
  "price": 000,
  "currency": "USD",
  "why_good": "why this is excellent right now",
  "urgency": "high/medium/low"
}}

Return JSON list: [{{}}, {{}}, ...]"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system="You are a travel expert searching for price opportunities. Always search for realistic prices." + (" Respond in English." if _lang == "en" else ""),
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text += block.text

        # Extract JSON array
        arr_match = re.search(r"\[.*\]", result_text, re.DOTALL)
        if arr_match:
            return json.loads(arr_match.group(0))

    except Exception:
        pass

    return []
