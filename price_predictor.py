import os
"""
AI price prediction — האם המחיר יעלה או ירד?
Claude מנתח היסטוריה, עונתיות ומגמות שוק.
"""
import json
from datetime import datetime
from typing import Optional
import anthropic

_lang = "he"

PREDICTION_PROMPT = """You are an expert in travel price analysis. Analyze the following data and predict where the price is heading.

Item: {name} | {category} | {destination}
Travel dates: {dates}
Price history (most recent first):
{history}

Average: {avg:.0f} | Minimum: {min_p:.0f} | Maximum: {max_p:.0f} | Current: {current:.0f}

Perform deep analysis:
1. Trend (rising/falling/stable)
2. Seasonality (is this peak season?)
3. How much time until travel?
4. Recommendation: buy now / wait / fair price

Return JSON:
{{
  "trend": "rising" | "falling" | "stable",
  "trend_pct": 5.2,
  "recommendation": "buy_now" | "wait" | "fair_price",
  "confidence": "high" | "medium" | "low",
  "predicted_price_7d": 000,
  "predicted_price_30d": 000,
  "reasoning": "detailed explanation (3-4 sentences)",
  "urgency_score": 8
}}"""


def predict_price(item: dict, history: list[dict]) -> Optional[dict]:
    """
    Predict whether price will go up or down.
    Returns prediction dict or None if not enough data.
    """
    if len(history) < 3:
        return None

    prices = [r["price"] for r in history]
    avg = sum(prices) / len(prices)
    current = prices[0]

    history_str = "\n".join(
        f"  {r['checked_at'][:16]}: {r['price']:.0f} {r['currency']}"
        for r in history[:15]
    )

    dates = ""
    if item.get("date_from"):
        dates = item["date_from"]
        if item.get("date_to"):
            dates += f" → {item['date_to']}"

    prompt = PREDICTION_PROMPT.format(
        name=item["name"],
        category=item["category"],
        destination=item["destination"],
        dates=dates or ("Not specified" if _lang == "en" else "לא צוין"),
        history=history_str,
        avg=avg,
        min_p=min(prices),
        max_p=max(prices),
        current=current,
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "missing_api_key", "reason": "ANTHROPIC_API_KEY not configured"}
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        text = "".join(b.text for b in response.content if b.type == "text")

        import re
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            result["analyzed_at"] = datetime.now().isoformat()
            result["current_price"] = current
            return result

    except Exception as e:
        return {"error": str(e), "reasoning": "Analysis error" if _lang == "en" else "שגיאה בניתוח"}

    return None


def format_prediction(pred: dict) -> dict:
    """Format prediction for display."""
    if not pred or "error" in pred:
        return {"text": "Cannot analyze" if _lang == "en" else "לא ניתן לנתח", "color": "gray", "icon": "❓"}

    trend = pred.get("trend", "stable")
    rec = pred.get("recommendation", "fair_price")
    confidence = pred.get("confidence", "low")

    icons = {"rising": "📈", "falling": "📉", "stable": "➡️"}
    colors = {"buy_now": "green", "wait": "orange", "fair_price": "blue"}
    rec_text = {
        "buy_now": "🔥 Buy Now!" if _lang == "en" else "🔥 קנה עכשיו!",
        "wait": "⏳ Wait" if _lang == "en" else "⏳ המתן",
        "fair_price": "✅ Fair Price" if _lang == "en" else "✅ מחיר הוגן",
    }
    conf_text = {
        "high": "High confidence" if _lang == "en" else "ביטחון גבוה",
        "medium": "Medium confidence" if _lang == "en" else "ביטחון בינוני",
        "low": "Low confidence" if _lang == "en" else "ביטחון נמוך",
    }

    return {
        "icon": icons.get(trend, "➡️"),
        "trend": trend,
        "color": colors.get(rec, "gray"),
        "recommendation": rec_text.get(rec, rec),
        "confidence": conf_text.get(confidence, confidence),
        "reasoning": pred.get("reasoning", ""),
        "predicted_7d": pred.get("predicted_price_7d"),
        "predicted_30d": pred.get("predicted_price_30d"),
        "urgency": pred.get("urgency_score", 5),
        "trend_pct": pred.get("trend_pct", 0),
    }
