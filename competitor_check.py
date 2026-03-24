"""
Competitor Price Comparison — finds the same flight/hotel on 5 booking sites simultaneously.
"""
import json
import re
import anthropic

_lang = "he"

BOOKING_SITES = [
    "Kayak (kayak.com)",
    "Expedia (expedia.com)",
    "Google Flights (flights.google.com)",
    "Booking.com",
    "Skyscanner (skyscanner.net)",
]


def compare_prices(
    origin: str,
    destination: str,
    date_out: str,
    date_return: str = "",
    travelers: int = 1,
    category: str = "flight",
) -> list:
    """
    Search for the same trip on multiple booking sites.
    Returns list of results sorted by price (cheapest first).
    """
    client = anthropic.Anthropic()

    trip_type = ("Round-trip flight" if _lang == "en" else "טיסה הלוך-חזור") if date_return else ("One-way flight" if _lang == "en" else "טיסה חד-כיוונית")
    if category == "hotel":
        trip_type = f"Hotel in {destination}"

    prompt = f"""חפש מחירים עבור:
סוג: {trip_type}
מסלול: {origin} → {destination}
תאריך יציאה: {date_out}
{f"תאריך חזרה: {date_return}" if date_return else ""}
נוסעים: {travelers}

חפש בכל אחד מהאתרים הבאים ומצא את המחיר הנוכחי הזול ביותר:
{chr(10).join(f"- {site}" for site in BOOKING_SITES)}

לכל אתר:
{{
  "site": "שם האתר",
  "price": 000,
  "currency": "USD",
  "airline": "שם חברת תעופה",
  "stops": 0,
  "duration_hours": 0.0,
  "url": "קישור ישיר להזמנה (אם ידוע)",
  "notes": "פרטים חשובים: מחיר כולל/לא כולל מזוודה וכו'",
  "available": true
}}

חשוב מאוד:
- מחירים אמיתיים בלבד — אל תמציא
- אם לא מצאת מחיר לאתר מסוים: "available": false
- כלול מזוודה בחישוב אם ידוע
- שים לב לעמלות ומסים (price = מחיר סופי כולל הכל)

החזר JSON array בלבד."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            thinking={"type": "adaptive"},
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            system="You are an expert in flight price comparison. Search for realistic and current prices only." + (" Respond in English. Use English for all text fields in the JSON." if _lang == "en" else ""),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            results = json.loads(arr.group(0))
            available = [r for r in results if r.get("available") and r.get("price")]
            return sorted(available, key=lambda x: x.get("price", 999_999))
    except Exception as e:
        return [{"error": str(e)}]
    return []
