"""
TradingView screenshot analyzer and trade idea translator using Claude API.

Two capabilities:
1. analyze_screenshot() — Takes a TradingView chart image and extracts a trade idea
2. translate_idea() — Converts free-form natural language into parser-compatible syntax

Usage:
    from vision.analyzer import analyze_screenshot, translate_idea
    result = analyze_screenshot(image_bytes, "image/png")
    if result.success:
        print(result.trade_idea)  # "buy when RSI below 30, sell when RSI above 70"

    result = translate_idea("go long on oversold RSI, short when overbought")
    if result.success:
        print(result.trade_idea)  # "buy when RSI below 30, sell when RSI above 70"
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass


@dataclass
class AnalysisResult:
    """Result of screenshot analysis."""
    trade_idea: str
    description: str
    success: bool
    error: str = ""


# The prompt instructs Claude to output in the exact syntax our parser understands
_SYSTEM_PROMPT = """You convert TradingView chart screenshots into a SPECIFIC machine-parseable format.

YOUR OUTPUT MUST USE ONLY THESE EXACT BUILDING BLOCKS (regex-parsed, no free text):

BUY CONDITIONS (pick one or combine with "and"):
  RSI below 30 | RSI above 70 | RSI(14) below 25
  SMA 20 crosses above SMA 50 | SMA 20 crosses below SMA 50
  EMA 12 crosses above EMA 26 | EMA 12 crosses below EMA 26
  golden cross | death cross
  price above SMA 200 | price below SMA 200
  price above EMA 50 | price below EMA 50
  price drops below lower Bollinger band | price above upper Bollinger band
  MACD crosses above signal | MACD crosses below signal
  MACD above zero | MACD below zero
  volume above 2x average | volume above 1.5x average

RISK (optional, append at end):
  stop loss 5% | take profit 10%

FORMAT: buy when [CONDITION], sell when [CONDITION], stop loss N%, take profit N%

VALID EXAMPLES — your output must look EXACTLY like one of these:
  buy when RSI below 30, sell when RSI above 70
  buy when EMA 12 crosses above EMA 26, sell when EMA 12 crosses below EMA 26
  buy when price drops below lower Bollinger band, sell when price above upper Bollinger band
  buy when MACD crosses above signal and RSI below 50, sell when MACD crosses below signal
  buy on golden cross, sell on death cross, stop loss 5%, take profit 15%
  buy when SMA 20 crosses above SMA 50 and volume above 2x average, sell when SMA 20 crosses below SMA 50
  buy when RSI below 25 and price below EMA 200, sell when RSI above 75

CRITICAL RULES:
- Output ONLY the trade idea string. No explanations. No quotes. No markdown.
- NEVER use words like "short", "pump", "spike", "breakout", "retest", "confluence", "setup" — these are NOT parseable.
- If chart shows annotations/text describing a setup, IGNORE the text. Only look at the actual INDICATORS visible on the chart.
- Look at: RSI panel numbers, MACD histogram, moving average lines, Bollinger bands, volume bars.
- If no standard indicators visible, use RSI below 30 / RSI above 70 as default with the visible stop loss/take profit.
- Always include BOTH buy and sell conditions.
- Numbers you can change: RSI thresholds (0-100), MA periods (any integer), volume multiplier (any decimal), SL/TP percentages."""

_USER_PROMPT = """Look at this TradingView chart. Identify the technical indicators actually drawn on the chart (RSI panel, MACD histogram, moving average lines, Bollinger bands, volume bars) and their period settings from the chart legend.

Convert what you see into ONE line using ONLY the exact syntax from my rules. Do NOT describe the setup in your own words. Do NOT use words like "short", "pump", "breakout", "retest". Only use the building blocks I gave you.

Output the single trade idea string:"""


def _load_api_key() -> str:
    """Load API key from environment or .env file."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key

    # Try .env file in project root
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    val = line.split("=", 1)[1].strip()
                    # Strip surrounding quotes
                    if (val.startswith('"') and val.endswith('"')) or \
                       (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    return val
    return ""


def analyze_screenshot(
    image_bytes: bytes,
    mime_type: str = "image/png",
    api_key: str = "",
) -> AnalysisResult:
    """Analyze a TradingView screenshot and extract a trade idea.

    Args:
        image_bytes: Raw image file bytes.
        mime_type: MIME type of the image (image/png, image/jpeg, image/webp).
        api_key: Optional API key override (if not set, uses env/`.env`).

    Returns:
        AnalysisResult with the extracted trade idea string.
    """
    if not api_key:
        api_key = _load_api_key()
    if not api_key:
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error="NO_API_KEY",
        )

    try:
        import anthropic
    except ImportError:
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error="anthropic package not installed. Run: pip install anthropic",
        )

    # Encode image to base64
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Normalize MIME type
    if mime_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        mime_type = "image/png"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": _USER_PROMPT,
                        },
                    ],
                }
            ],
        )

        # Extract the text response
        trade_idea = ""
        for block in response.content:
            if hasattr(block, "text"):
                trade_idea = block.text.strip()
                break

        if not trade_idea:
            return AnalysisResult(
                trade_idea="",
                description="",
                success=False,
                error="Vision API returned empty response.",
            )

        # Clean up: remove surrounding quotes if present
        if (trade_idea.startswith('"') and trade_idea.endswith('"')) or \
           (trade_idea.startswith("'") and trade_idea.endswith("'")):
            trade_idea = trade_idea[1:-1]

        # Build a description of what was detected
        description = f"Extracted from TradingView screenshot: {trade_idea}"

        return AnalysisResult(
            trade_idea=trade_idea,
            description=description,
            success=True,
        )

    except anthropic.AuthenticationError as e:
        err_msg = str(e).lower()
        if "credit" in err_msg or "balance" in err_msg or "billing" in err_msg:
            return AnalysisResult(
                trade_idea="",
                description="",
                success=False,
                error="NO_CREDITS",
            )
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error="Invalid API key. Double-check your key at console.anthropic.com/settings/keys",
        )
    except anthropic.PermissionDeniedError as e:
        err_msg = str(e).lower()
        if "credit" in err_msg or "balance" in err_msg or "billing" in err_msg:
            return AnalysisResult(
                trade_idea="",
                description="",
                success=False,
                error="NO_CREDITS",
            )
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error=f"API permission denied: {e}",
        )
    except anthropic.RateLimitError:
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error="Anthropic API rate limit exceeded. Wait a moment and try again.",
        )
    except Exception as e:
        err_msg = str(e).lower()
        if "credit" in err_msg or "balance" in err_msg or "billing" in err_msg:
            return AnalysisResult(
                trade_idea="",
                description="",
                success=False,
                error="NO_CREDITS",
            )
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error=f"Vision analysis failed: {str(e)}",
        )


# ======================================================================
# Trade idea translator (text → parser-compatible syntax)
# ======================================================================

_TRANSLATE_SYSTEM_PROMPT = """You translate free-form trading ideas into a SPECIFIC machine-parseable format.

The user will give you a trading idea in natural language. Convert it into EXACTLY the syntax below.

YOUR OUTPUT MUST USE ONLY THESE EXACT BUILDING BLOCKS (regex-parsed, no free text):

BUY CONDITIONS (pick one or combine with "and"):
  RSI below 30 | RSI above 70 | RSI(14) below 25
  SMA 20 crosses above SMA 50 | SMA 20 crosses below SMA 50
  EMA 12 crosses above EMA 26 | EMA 12 crosses below EMA 26
  golden cross | death cross
  price above SMA 200 | price below SMA 200
  price above EMA 50 | price below EMA 50
  price drops below lower Bollinger band | price above upper Bollinger band
  MACD crosses above signal | MACD crosses below signal
  MACD above zero | MACD below zero
  volume above 2x average | volume above 1.5x average

RISK (optional, append at end):
  stop loss 5% | take profit 10%

FORMAT: buy when [CONDITION], sell when [CONDITION], stop loss N%, take profit N%

VALID EXAMPLES — your output must look EXACTLY like one of these:
  buy when RSI below 30, sell when RSI above 70
  buy when EMA 12 crosses above EMA 26, sell when EMA 12 crosses below EMA 26
  buy when price drops below lower Bollinger band, sell when price above upper Bollinger band
  buy when MACD crosses above signal and RSI below 50, sell when MACD crosses below signal
  buy on golden cross, sell on death cross, stop loss 5%, take profit 15%
  buy when SMA 20 crosses above SMA 50 and volume above 2x average, sell when SMA 20 crosses below SMA 50
  buy when RSI below 25 and price below EMA 200, sell when RSI above 75

CRITICAL RULES:
- Output ONLY the trade idea string. No explanations. No quotes. No markdown.
- NEVER use words like "short", "pump", "spike", "breakout", "retest", "confluence", "setup"
- Always include BOTH buy and sell conditions.
- If the user mentions "short" or selling, translate it as an EXIT condition (sell when).
- If the idea is vague, pick the CLOSEST matching indicator strategy.
- If percentages for stop/take-profit are mentioned, include them.
- Numbers you can change: RSI thresholds (0-100), MA periods (any integer), volume multiplier (any decimal), SL/TP percentages."""


def translate_idea(
    text: str,
    api_key: str = "",
) -> AnalysisResult:
    """Translate a free-form trade idea into parser-compatible syntax using Claude.

    Args:
        text: Free-form natural language trade idea.
        api_key: Optional API key override (if not set, uses env/`.env`).

    Returns:
        AnalysisResult with the translated trade idea string.
    """
    if not api_key:
        api_key = _load_api_key()
    if not api_key:
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error="NO_API_KEY",
        )

    try:
        import anthropic
    except ImportError:
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error="anthropic package not installed. Run: pip install anthropic",
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_TRANSLATE_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Translate this trading idea into the exact syntax:\n\n{text}",
                }
            ],
        )

        # Extract the text response
        trade_idea = ""
        for block in response.content:
            if hasattr(block, "text"):
                trade_idea = block.text.strip()
                break

        if not trade_idea:
            return AnalysisResult(
                trade_idea="",
                description="",
                success=False,
                error="AI returned empty response.",
            )

        # Clean up: remove surrounding quotes if present
        if (trade_idea.startswith('"') and trade_idea.endswith('"')) or \
           (trade_idea.startswith("'") and trade_idea.endswith("'")):
            trade_idea = trade_idea[1:-1]

        # Remove any markdown formatting that slipped through
        trade_idea = trade_idea.strip('`').strip()
        # Take only the first line if multiple were returned
        trade_idea = trade_idea.split('\n')[0].strip()

        return AnalysisResult(
            trade_idea=trade_idea,
            description=f"AI translated: \"{text}\" → \"{trade_idea}\"",
            success=True,
        )

    except Exception as e:
        err_msg = str(e).lower()
        if "credit" in err_msg or "balance" in err_msg or "billing" in err_msg:
            return AnalysisResult(
                trade_idea="",
                description="",
                success=False,
                error="NO_CREDITS",
            )
        return AnalysisResult(
            trade_idea="",
            description="",
            success=False,
            error=f"AI translation failed: {str(e)}",
        )
