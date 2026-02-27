"""
Natural language parser for trade ideas.

Converts text descriptions into RuleBasedStrategy objects.
Supports common trading patterns like:

  "buy when RSI below 30, sell when RSI above 70"
  "buy when EMA 12 crosses above EMA 26, sell when EMA 12 crosses below EMA 26"
  "buy when price drops below lower Bollinger band, sell when price above upper band"
  "buy when MACD crosses above signal with 5% stop loss and 10% take profit"

Also handles free-form natural language via smart normalization:
  "go long on oversold RSI, take profit at overbought"
  "short when moving averages cross down"
  "mean reversion with Bollinger bands, 3% stop loss"

The parser is pattern-matching based (no LLM needed). A normalization layer
rewrites trader slang and free-form descriptions into the exact syntax the
regex engine expects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from strategies.base import Strategy
from strategies.rule_based import (
    Rule,
    RuleBasedStrategy,
    RSIAbove,
    RSIBelow,
    SMACrossAbove,
    SMACrossBelow,
    EMACrossAbove,
    EMACrossBelow,
    PriceAboveSMA,
    PriceBelowSMA,
    PriceAboveEMA,
    PriceBelowEMA,
    PriceAboveBollinger,
    PriceBelowBollinger,
    MACDCrossAbove,
    MACDCrossBelow,
    MACDAboveZero,
    MACDBelowZero,
    VolumeAboveAvg,
)
from strategies.crt_cisd import CRTCISDStrategy


@dataclass
class ParseResult:
    """Result of parsing a trade idea."""

    strategy: Strategy | None   # Can be RuleBasedStrategy or a custom Strategy
    success: bool
    message: str
    warnings: list[str]


def _try_custom_strategy(text: str) -> ParseResult | None:
    """Check if the text matches a known custom strategy. Returns None if no match."""

    # CRT + CISD detection
    if re.search(r'\bcrt\b', text) or re.search(r'\bcisd\b', text) or \
       re.search(r'\bcandle\s*range\s*theory\b', text) or \
       re.search(r'\bliquidity\s*sweep\b', text) or \
       re.search(r'\bliquidity\s*grab\b', text):

        strategy = CRTCISDStrategy()

        # Extract RR target if specified (e.g. "3R", "2.5R", "rr 3")
        rr_match = re.search(r'(\d+(?:\.\d+)?)\s*[rR]\b', text)
        if rr_match:
            strategy.rr_target = float(rr_match.group(1))

        rr_match2 = re.search(r'rr\s*[:=]?\s*(\d+(?:\.\d+)?)', text)
        if rr_match2:
            strategy.rr_target = float(rr_match2.group(1))

        warnings = [
            "Using CRT + CISD candle pattern strategy (not indicator-based).",
            "LONG + SHORT: enters long on bullish CRT, enters short on bearish CRT.",
            f"Target: {strategy.rr_target}R (risk-to-reward). SL at C2 extreme.",
            "Note: Only daily candles available — multi-timeframe alignment not applied.",
        ]

        return ParseResult(
            strategy=strategy,
            success=True,
            message="CRT + CISD pattern strategy loaded.",
            warnings=warnings,
        )

    return None


def parse_trade_idea(text: str) -> ParseResult:
    """Parse a natural-language trade idea into a Strategy.

    Checks for known custom strategies first (e.g. CRT+CISD), then falls
    back to the regex-based NL parser for indicator strategies.

    Args:
        text: Free-form trade idea description.

    Returns:
        ParseResult with the built strategy or an error message.
    """
    original_text = text.strip()
    text_lower = original_text.lower()

    # ── Custom strategy detection ──────────────────────────────────
    custom = _try_custom_strategy(text_lower)
    if custom is not None:
        return custom
    warnings: list[str] = []

    # ── Step 1: Smart normalization ────────────────────────────────
    normalized = _normalize_text(text_lower)
    if normalized != text_lower:
        warnings.append(f"Interpreted as: \"{normalized}\"")

    # Detect unsupported concepts that were dropped during normalization
    if re.search(r'\bretest\b', text_lower):
        warnings.append("Dropped: \"retest of support/resistance\" — price-action patterns aren't backtestable with standard indicators.")
    if re.search(r'\bopen\s+interest\b', text_lower):
        warnings.append("Dropped: \"open interest\" — not available in OHLCV candle data.")
    if re.search(r'\b\d+\s*(?:m|min(?:ute)?s?)\s*(?:candles?)?\b', text_lower):
        warnings.append("Note: Only daily candles are available. Intraday timeframe was ignored.")

    # Split into buy/sell sections
    buy_text, sell_text = _split_buy_sell(normalized)

    if not buy_text and not sell_text:
        return ParseResult(
            strategy=None,
            success=False,
            message=(
                "Could not find buy/sell conditions. Try something like:\n"
                '  "buy when RSI below 30, sell when RSI above 70"\n'
                '  "buy when EMA 12 crosses above EMA 26, sell on death cross"'
            ),
            warnings=[],
        )

    buy_rules: list[Rule] = []
    sell_rules: list[Rule] = []

    if buy_text:
        buy_rules, buy_warns = _parse_conditions(buy_text)
        warnings.extend(buy_warns)

    if sell_text:
        sell_rules, sell_warns = _parse_conditions(sell_text)
        warnings.extend(sell_warns)

    if not buy_rules and not sell_rules:
        return ParseResult(
            strategy=None,
            success=False,
            message="NEEDS_AI_TRANSLATION",
            warnings=warnings,
        )

    # If only buy rules given, auto-generate mirror sell rules
    if buy_rules and not sell_rules:
        sell_rules = _generate_mirror_sell(buy_rules)
        if sell_rules:
            warnings.append("No sell conditions given — auto-generated mirror exit rules.")

    # If only sell rules given, that's unusual but allow it with warning
    if sell_rules and not buy_rules:
        warnings.append("No buy conditions found — strategy will never enter a trade. Try adding a buy condition.")

    # Parse stop-loss / take-profit from the full text
    stop_loss = _parse_stop_loss(text_lower)
    take_profit = _parse_take_profit(text_lower)

    # Build strategy name from the rules
    name = _build_name(buy_rules, sell_rules)

    strategy = RuleBasedStrategy(
        name=name,
        description=text.strip(),
        buy_rules=buy_rules,
        sell_rules=sell_rules,
        stop_loss_pct=stop_loss,
        take_profit_pct=take_profit,
    )

    return ParseResult(
        strategy=strategy,
        success=True,
        message="Strategy parsed successfully.",
        warnings=warnings,
    )


# ======================================================================
# Smart normalization — rewrites free-form language into parser syntax
# ======================================================================

def _normalize_text(text: str) -> str:
    """Rewrite free-form trader language into parser-compatible syntax.

    This is the "language bridge" — it understands trader slang, abbreviations,
    and common phrasing, and rewrites them into the exact keywords the regex
    engine expects.  Everything stays lowercase because _parse_single_condition
    matches case-insensitively already.
    """
    t = text.lower().strip()

    # ── Remove filler words & noise ────────────────────────────────
    # Remove time-based conditions we can't backtest on daily candles
    t = re.sub(r'\b(?:in\s+(?:under\s+)?\d+\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|days?))\b', '', t)
    t = re.sub(r'\b(?:within\s+\d+\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|days?))\b', '', t)
    # Remove percentage pump/dump phrases
    t = re.sub(r'\b(?:pumps?|dumps?|rises?|spikes?|moons?|tanks?|crashes?)\s*\d+(?:\.\d+)?%?\+?\s*', '', t)
    # Remove "then" clause fragments that describe price action (not indicators)
    t = re.sub(r'\bthen\s+(?:drops?\s+back|falls?\s+back|returns?\s+to|goes?\s+back|retraces?|retests?)\s+[^,;.]*', '', t)
    # Remove vague free-form descriptions
    t = re.sub(r'\b(?:the\s+)?(?:breakout|breakdown)\s+(?:origin|level|zone|area|point)\b', '', t)
    t = re.sub(r'\b(?:right\s+)?(?:before|after|during)\s+(?:a\s+)?(?:pump|dump|spike|crash|drop|rise)\b', '', t)
    # Remove price-action concepts that can't map to standard indicators
    t = re.sub(r'\b(?:on\s+)?retest\s+(?:of\s+)?(?:the\s+)?(?:broken\s+)?(?:support|resistance)(?:\s+(?:level|zone|area|line))?\b', '', t)
    t = re.sub(r'\bbroken\s+(?:support|resistance)(?:\s+(?:level|zone|area|line))?\b', '', t)
    t = re.sub(r'\b(?:declining|falling|rising|increasing)\s+open\s+interest\b', '', t)
    t = re.sub(r'\bopen\s+interest\b', '', t)
    # Remove candle/timeframe specs (we only support daily)
    t = re.sub(r'\b(?:use\s+)?(\d+[mhd]|(?:\d+\s*(?:min(?:ute)?|hour|day|week)\w*))(?:\s+candles?)?\b', '', t)
    # Remove leftover noise words
    t = re.sub(r'\b(?:basically|essentially|just|simply|the|a|an)\b', ' ', t)

    # ── Strategy pattern shortcuts (FULL REPLACEMENTS — do first) ──
    # "RSI strategy" / "RSI trading" (no specifics) → default RSI strategy
    if re.search(r'\brsi\s+(?:strategy|trading|system)\b', t) and not re.search(r'rsi\s*(?:\(\d+\)\s*)?(?:below|above|under|over)', t):
        # Extract stop loss / take profit before replacing
        sl = re.search(r'(?:stop.?loss|sl)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        tp = re.search(r'(?:take.?profit|tp)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        sl_str = f', stop loss {sl.group(1)}%' if sl else ''
        tp_str = f', take profit {tp.group(1)}%' if tp else ''
        t = f'buy when rsi below 30, sell when rsi above 70{sl_str}{tp_str}'
    # "MACD strategy" → default MACD
    if re.search(r'\bmacd\s+(?:strategy|trading|system|crossover\s+strategy)\b', t) and not re.search(r'macd\s*(?:crosses|above|below)', t):
        sl = re.search(r'(?:stop.?loss|sl)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        tp = re.search(r'(?:take.?profit|tp)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        sl_str = f', stop loss {sl.group(1)}%' if sl else ''
        tp_str = f', take profit {tp.group(1)}%' if tp else ''
        t = f'buy when macd crosses above signal, sell when macd crosses below signal{sl_str}{tp_str}'
    # "Bollinger strategy" / "BB strategy" → default BB
    if re.search(r'\b(?:bollinger|bb)\s+(?:strategy|trading|system)\b', t) and not re.search(r'bollinger\s+band', t):
        sl = re.search(r'(?:stop.?loss|sl)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        tp = re.search(r'(?:take.?profit|tp)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        sl_str = f', stop loss {sl.group(1)}%' if sl else ''
        tp_str = f', take profit {tp.group(1)}%' if tp else ''
        t = f'buy when price drops below lower bollinger band, sell when price above upper bollinger band{sl_str}{tp_str}'
    # "mean reversion" / "Bollinger bounce" → full strategy
    if re.search(r'\b(?:mean\s+reversion|bb\s+bounce|bollinger\s+(?:band\s+)?bounce)\b', t):
        sl = re.search(r'(?:stop.?loss|sl)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        tp = re.search(r'(?:take.?profit|tp)\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', t)
        sl_str = f', stop loss {sl.group(1)}%' if sl else ''
        tp_str = f', take profit {tp.group(1)}%' if tp else ''
        t = f'buy when price drops below lower bollinger band, sell when price above upper bollinger band{sl_str}{tp_str}'

    # ── Normalize long/short into buy/sell ─────────────────────────
    # Detect "short" setups: in a long-only backtester, "short when X" means
    # "buy (default entry), sell when X" — we flip the logic so X becomes the exit.
    is_short_setup = bool(re.search(r'\b(?:go\s+)?short\b', t))
    t = re.sub(r'\b(?:go\s+)?long\b', 'buy', t)
    t = re.sub(r'\b(?:go\s+)?short\b', 'sell', t)
    t = re.sub(r'\benter\b', 'buy', t)
    t = re.sub(r'\b(?:close|exit)\s+(?:position|trade)?\s*(?:when|if|on|at)?\b', 'sell when ', t)

    # ── Stop-loss / take-profit normalization (do early) ───────────
    t = re.sub(r'\bsl\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', r'stop loss \1%', t)
    t = re.sub(r'\btp\s*(?:at\s+|of\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', r'take profit \1%', t)
    t = re.sub(r'\brisk\s+(\d+(?:\.\d+)?)\s*%', r'stop loss \1%', t)
    t = re.sub(r'\btarget\s+(\d+(?:\.\d+)?)\s*%', r'take profit \1%', t)
    t = re.sub(r'\b(\d+(?:\.\d+)?)\s*%\s*stop\b', r'stop loss \1%', t)
    t = re.sub(r'\b(\d+(?:\.\d+)?)\s*%\s*(?:target|profit)\b', r'take profit \1%', t)
    # "stop loss X% above entry" → "stop loss X%" (remove "above entry" noise)
    t = re.sub(r'(stop loss \d+(?:\.\d+)?%)\s*(?:above|below|from)\s*(?:entry|position)', r'\1', t)
    t = re.sub(r'(take profit \d+(?:\.\d+)?%)\s*(?:above|below|from)\s*(?:entry|position)', r'\1', t)

    # ── RSI normalization ──────────────────────────────────────────
    # "buy the dip on RSI" / "dip buying RSI" → rsi below 30
    t = re.sub(r'\b(?:the\s+)?dip\s*(?:on|in|of|with)?\s*(?:the\s+)?rsi\b', 'rsi below 30', t)
    t = re.sub(r'\brsi\s+dip(?:s|ping)?\b', 'rsi below 30', t)
    t = re.sub(r'\b(?:rsi\s+(?:is\s+)?)?oversold\s*(?:rsi)?\b', 'rsi below 30', t)
    t = re.sub(r'\b(?:rsi\s+(?:is\s+)?)?overbought\s*(?:rsi)?\b', 'rsi above 70', t)
    t = re.sub(r'\brsi\s*(?:\(\d+\)\s*)?(?:at|hits?|reaches?|touches?|gets?\s+to)\s*(\d+)',
               lambda m: f'rsi below {m.group(1)}' if int(m.group(1)) <= 50 else f'rsi above {m.group(1)}', t)
    t = re.sub(r'\brsi\s+(?:dips?|drops?|falls?|tanks?)\b(?!\s*(?:below|under|to|from))', 'rsi below 30', t)
    t = re.sub(r'\brsi\s+(?:spikes?|rises?|climbs?|jumps?)\b(?!\s*(?:above|over|to))', 'rsi above 70', t)

    # ── Moving average normalization ───────────────────────────────
    t = re.sub(r'\b(?:moving\s+averages?\s+cross\s*(?:down|under)|ma\s+(?:bearish\s+)?cross\s*down)\b', 'sma 20 crosses below sma 50', t)
    t = re.sub(r'\b(?:moving\s+averages?\s+cross(?:over)?|ma\s+cross(?:over)?)\b', 'sma 20 crosses above sma 50', t)
    t = re.sub(r'\b(\d+)[\s-]*(?:day|period|bar)?\s*(?:ma|moving\s+average)\b', r'sma \1', t)
    t = re.sub(r'\bfast\s+(?:ma|moving\s+average)\b', 'sma 20', t)
    t = re.sub(r'\bslow\s+(?:ma|moving\s+average)\b', 'sma 50', t)

    # ── MACD normalization ─────────────────────────────────────────
    t = re.sub(r'\bmacd\s+(?:turns?|goes?|flips?)\s+(?:positive|bullish|up)\b', 'macd crosses above signal', t)
    t = re.sub(r'\bmacd\s+(?:turns?|goes?|flips?)\s+(?:negative|bearish|down)\b', 'macd crosses below signal', t)
    t = re.sub(r'\bmacd\s+(?:bullish\s+)?crossover\b', 'macd crosses above signal', t)
    t = re.sub(r'\bmacd\s+(?:bearish\s+)?crossunder\b', 'macd crosses below signal', t)
    t = re.sub(r'\bmacd\s+(?:and\s+)?signal\s+(?:line\s+)?cross(?:over)?\b', 'macd crosses above signal', t)
    t = re.sub(r'\bmacd\s+histogram\s+(?:positive|green|above)\b', 'macd above zero', t)
    t = re.sub(r'\bmacd\s+histogram\s+(?:negative|red|below)\b', 'macd below zero', t)

    # ── Bollinger normalization ────────────────────────────────────
    t = re.sub(r'\b(?:price\s+)?(?:touches?|hits?|reaches?|at)\s+(?:the\s+)?lower\s+(?:bollinger\s+)?band\b',
               'price drops below lower bollinger band', t)
    t = re.sub(r'\b(?:price\s+)?(?:touches?|hits?|reaches?|at)\s+(?:the\s+)?upper\s+(?:bollinger\s+)?band\b',
               'price above upper bollinger band', t)
    t = re.sub(r'\b(?:price\s+)?(?:below|under)\s+(?:lower\s+)?bb\b', 'price drops below lower bollinger band', t)
    t = re.sub(r'\b(?:price\s+)?(?:above|over)\s+(?:upper\s+)?bb\b', 'price above upper bollinger band', t)

    # ── Volume normalization ───────────────────────────────────────
    t = re.sub(r'\b(?:high|big|huge|large|heavy|strong)\s+volume\b', 'volume above 2x average', t)
    # "volume spike above 2x average" → "volume above 2x average" (don't double up)
    t = re.sub(r'\bvolume\s+(?:spike|surge|burst|explosion)\s+(?=above\s+\d)', 'volume ', t)
    # "volume spike" (no multiplier given) → "volume above 2x average"
    t = re.sub(r'\bvolume\s+(?:spike|surge|burst|explosion)\b', 'volume above 2x average', t)

    # ── Remove leftover noise words ────────────────────────────────
    # Don't remove "on" after buy/sell (it's valid syntax: "buy on golden cross")
    t = re.sub(r'\b(?:strategy|trading|system|with|using|after)\b', ' ', t)
    # Remove standalone "on" that isn't after buy/sell
    t = re.sub(r'(?<!\bbuy )(?<!\bsell )\bon\b', ' ', t)

    # ── Ensure buy/sell structure exists ────────────────────────────
    has_indicators = bool(re.search(r'\b(?:rsi|sma|ema|macd|bollinger|golden\s+cross|death\s+cross|volume\s+above)', t))
    has_buy = bool(re.search(r'\bbuy\b', t))
    has_sell = bool(re.search(r'\bsell\b', t))

    if has_indicators and not has_buy and not has_sell:
        t = f"buy when {t}"
    elif is_short_setup and has_sell and not has_buy and has_indicators:
        # "Short when X" → add a default buy entry, keep X as the sell/exit
        # Use price above SMA 200 as a reasonable default long entry for short setups
        t = f"buy when price above sma 200, {t}"

    # ── Ensure "when" keyword after buy/sell ────────────────────────
    t = re.sub(r'\bbuy\s+(?!when\b|on\b|if\b)(?=\w)', 'buy when ', t)
    t = re.sub(r'\bsell\s+(?!when\b|on\b|if\b)(?=\w)', 'sell when ', t)

    # ── Fix "and" spacing issues (but protect "band" etc.) ─────────
    # Only split "XYZand" if XYZ is not "b" (to protect "band", "bollinger band")
    t = re.sub(r'(?<![b])(?<=\w)and\b', r' and', t)
    t = re.sub(r'\band(?=[a-z])', r'and ', t)

    # ── Clean up whitespace and dangling connectors ─────────────────
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r',\s*,', ',', t)
    t = re.sub(r',\s*$', '', t)
    t = re.sub(r'^\s*,', '', t)
    # Remove dangling "and" at end of phrases (from stripped conditions)
    t = re.sub(r'\band\s*([,;.])', r'\1', t)
    t = re.sub(r'\band\s*$', '', t)
    # Remove empty sentences (periods with nothing between)
    t = re.sub(r'\.\s*\.', '.', t)
    t = re.sub(r'\s+([.,;])', r'\1', t)
    t = t.strip()

    return t


# ======================================================================
# Internal parsing
# ======================================================================

def _split_buy_sell(text: str) -> tuple[str, str]:
    """Split text into buy-conditions and sell-conditions sections."""
    buy_text = ""
    sell_text = ""

    # Try splitting on "sell when" / "exit when" / "close when"
    sell_patterns = [
        r'[,;.]?\s*(?:and\s+)?sell\s+(?:when|if|on)',
        r'[,;.]?\s*(?:and\s+)?exit\s+(?:when|if|on)',
        r'[,;.]?\s*(?:and\s+)?close\s+(?:when|if|on)',
    ]

    for pat in sell_patterns:
        match = re.search(pat, text)
        if match:
            buy_text = text[:match.start()].strip()
            sell_text = text[match.end():].strip()
            break

    if not sell_text:
        # No sell section found — treat entire text as buy
        buy_text = text

    # Strip leading buy/entry keywords from buy_text
    buy_text = re.sub(r'^(?:buy|enter|long)\s+(?:when|if|on)\s+', '', buy_text).strip()

    return buy_text, sell_text


def _parse_conditions(text: str) -> tuple[list[Rule], list[str]]:
    """Parse a conditions section into a list of Rule objects."""
    rules: list[Rule] = []
    warnings: list[str] = []

    # Split on "and" / "&" / "+"
    parts = re.split(r'\s+and\s+|\s*&\s*|\s*\+\s*', text)

    for part in parts:
        part = part.strip().strip(',').strip(';').strip()
        if not part:
            continue

        rule = _parse_single_condition(part)
        if rule:
            rules.append(rule)
        else:
            # Don't warn on stop-loss/take-profit fragments — they're parsed separately
            if not re.search(r'stop.?loss|take.?profit|sl\b|tp\b', part):
                warnings.append(f"Could not parse condition: \"{part}\"")

    return rules, warnings


def _parse_single_condition(text: str) -> Rule | None:
    """Try to parse a single condition string into a Rule."""

    # RSI below/under N
    m = re.search(r'rsi\s*(?:\((\d+)\))?\s*(?:below|under|<|drops?\s+(?:below|under))\s*(\d+(?:\.\d+)?)', text)
    if m:
        period = int(m.group(1)) if m.group(1) else 14
        threshold = float(m.group(2))
        return RSIBelow(threshold=threshold, period=period)

    # RSI above/over N
    m = re.search(r'rsi\s*(?:\((\d+)\))?\s*(?:above|over|>|rises?\s+(?:above|over))\s*(\d+(?:\.\d+)?)', text)
    if m:
        period = int(m.group(1)) if m.group(1) else 14
        threshold = float(m.group(2))
        return RSIAbove(threshold=threshold, period=period)

    # SMA golden cross / death cross shorthand
    if re.search(r'golden\s+cross', text):
        m = re.search(r'(\d+)\s*(?:/|,)\s*(\d+)', text)
        if m:
            return SMACrossAbove(fast=int(m.group(1)), slow=int(m.group(2)))
        return SMACrossAbove(fast=50, slow=200)

    if re.search(r'death\s+cross', text):
        m = re.search(r'(\d+)\s*(?:/|,)\s*(\d+)', text)
        if m:
            return SMACrossBelow(fast=int(m.group(1)), slow=int(m.group(2)))
        return SMACrossBelow(fast=50, slow=200)

    # SMA N crosses above/below SMA N
    m = re.search(r'sma\s*(\d+)\s*cross(?:es)?\s*(above|below|over|under)\s*sma\s*(\d+)', text)
    if m:
        fast, direction, slow = int(m.group(1)), m.group(2), int(m.group(3))
        if direction in ("above", "over"):
            return SMACrossAbove(fast=fast, slow=slow)
        return SMACrossBelow(fast=fast, slow=slow)

    # EMA N crosses above/below EMA N
    m = re.search(r'ema\s*(\d+)\s*cross(?:es)?\s*(above|below|over|under)\s*ema\s*(\d+)', text)
    if m:
        fast, direction, slow = int(m.group(1)), m.group(2), int(m.group(3))
        if direction in ("above", "over"):
            return EMACrossAbove(fast=fast, slow=slow)
        return EMACrossBelow(fast=fast, slow=slow)

    # Price above/below SMA N
    m = re.search(r'price\s*(?:is\s+)?(?:above|over|>)\s*sma\s*(?:\()?(\d+)(?:\))?', text)
    if m:
        return PriceAboveSMA(period=int(m.group(1)))

    m = re.search(r'price\s*(?:is\s+)?(?:below|under|<)\s*sma\s*(?:\()?(\d+)(?:\))?', text)
    if m:
        return PriceBelowSMA(period=int(m.group(1)))

    # Price above/below EMA N
    m = re.search(r'price\s*(?:is\s+)?(?:above|over|>)\s*ema\s*(?:\()?(\d+)(?:\))?', text)
    if m:
        return PriceAboveEMA(period=int(m.group(1)))

    m = re.search(r'price\s*(?:is\s+)?(?:below|under|<)\s*ema\s*(?:\()?(\d+)(?:\))?', text)
    if m:
        return PriceBelowEMA(period=int(m.group(1)))

    # Bollinger Band conditions
    if re.search(r'(?:below|under|drops?\s+below)\s*(?:the\s+)?(?:lower\s+)?bollinger', text):
        m = re.search(r'bollinger\s*(?:\((\d+))?', text)
        period = int(m.group(1)) if m and m.group(1) else 20
        return PriceBelowBollinger(period=period)

    if re.search(r'(?:above|over|rises?\s+above)\s*(?:the\s+)?(?:upper\s+)?bollinger', text):
        m = re.search(r'bollinger\s*(?:\((\d+))?', text)
        period = int(m.group(1)) if m and m.group(1) else 20
        return PriceAboveBollinger(period=period)

    # "price below lower bollinger band" / "price breaks upper band"
    if re.search(r'lower\s+(?:bollinger|band)', text):
        return PriceBelowBollinger()
    if re.search(r'upper\s+(?:bollinger|band)', text):
        return PriceAboveBollinger()

    # MACD crosses above/below signal
    m = re.search(r'macd\s*(?:\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\))?\s*cross(?:es)?\s*(above|below|over|under)\s*(?:the\s+)?signal', text)
    if m:
        fast = int(m.group(1)) if m.group(1) else 12
        slow = int(m.group(2)) if m.group(2) else 26
        sig = int(m.group(3)) if m.group(3) else 9
        if m.group(4) in ("above", "over"):
            return MACDCrossAbove(fast=fast, slow=slow, signal=sig)
        return MACDCrossBelow(fast=fast, slow=slow, signal=sig)

    # Shorthand: "MACD bullish crossover" / "MACD bearish crossover"
    if re.search(r'macd\s*(?:bullish|positive)\s*cross', text):
        return MACDCrossAbove()
    if re.search(r'macd\s*(?:bearish|negative)\s*cross', text):
        return MACDCrossBelow()

    # MACD above/below zero
    if re.search(r'macd\s*(?:line\s+)?(?:above|over|>)\s*(?:zero|0)', text):
        return MACDAboveZero()
    if re.search(r'macd\s*(?:line\s+)?(?:below|under|<)\s*(?:zero|0)', text):
        return MACDBelowZero()

    # Volume spike
    m = re.search(r'volume\s*(?:above|over|>|spike)\s*(?:(\d+(?:\.\d+)?)x?\s*)?(?:average|avg|mean)?\s*(?:\((\d+)\))?', text)
    if m:
        mult = float(m.group(1)) if m.group(1) else 1.5
        period = int(m.group(2)) if m.group(2) else 20
        return VolumeAboveAvg(period=period, multiplier=mult)

    return None


def _generate_mirror_sell(buy_rules: list[Rule]) -> list[Rule]:
    """Try to generate opposite sell rules from buy rules."""
    sell_rules: list[Rule] = []

    for r in buy_rules:
        if isinstance(r, RSIBelow):
            sell_rules.append(RSIAbove(threshold=100 - r.threshold, period=r.period))
        elif isinstance(r, RSIAbove):
            sell_rules.append(RSIBelow(threshold=100 - r.threshold, period=r.period))
        elif isinstance(r, SMACrossAbove):
            sell_rules.append(SMACrossBelow(fast=r.fast, slow=r.slow))
        elif isinstance(r, SMACrossBelow):
            sell_rules.append(SMACrossAbove(fast=r.fast, slow=r.slow))
        elif isinstance(r, EMACrossAbove):
            sell_rules.append(EMACrossBelow(fast=r.fast, slow=r.slow))
        elif isinstance(r, EMACrossBelow):
            sell_rules.append(EMACrossAbove(fast=r.fast, slow=r.slow))
        elif isinstance(r, PriceAboveSMA):
            sell_rules.append(PriceBelowSMA(period=r.period))
        elif isinstance(r, PriceBelowSMA):
            sell_rules.append(PriceAboveSMA(period=r.period))
        elif isinstance(r, PriceAboveEMA):
            sell_rules.append(PriceBelowEMA(period=r.period))
        elif isinstance(r, PriceBelowEMA):
            sell_rules.append(PriceAboveEMA(period=r.period))
        elif isinstance(r, MACDCrossAbove):
            sell_rules.append(MACDCrossBelow(fast=r.fast, slow=r.slow, signal=r.signal))
        elif isinstance(r, MACDCrossBelow):
            sell_rules.append(MACDCrossAbove(fast=r.fast, slow=r.slow, signal=r.signal))
        elif isinstance(r, PriceBelowBollinger):
            sell_rules.append(PriceAboveBollinger(period=r.period, num_std=r.num_std))
        elif isinstance(r, PriceAboveBollinger):
            sell_rules.append(PriceBelowBollinger(period=r.period, num_std=r.num_std))

    return sell_rules


def _parse_stop_loss(text: str) -> float | None:
    """Extract stop-loss percentage from text."""
    m = re.search(r'(?:stop.?loss|sl)\s*(?:of\s+|at\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', text)
    if m:
        return float(m.group(1)) / 100.0
    return None


def _parse_take_profit(text: str) -> float | None:
    """Extract take-profit percentage from text."""
    m = re.search(r'(?:take.?profit|tp)\s*(?:of\s+|at\s+|=\s*)?(\d+(?:\.\d+)?)\s*%', text)
    if m:
        return float(m.group(1)) / 100.0
    return None


def _build_name(buy_rules: list[Rule], sell_rules: list[Rule]) -> str:
    """Build a short strategy name from the rule types."""
    indicators_used = set()
    for r in buy_rules + sell_rules:
        class_name = type(r).__name__
        if "RSI" in class_name:
            indicators_used.add("RSI")
        elif "SMA" in class_name:
            indicators_used.add("SMA")
        elif "EMA" in class_name:
            indicators_used.add("EMA")
        elif "MACD" in class_name:
            indicators_used.add("MACD")
        elif "Bollinger" in class_name:
            indicators_used.add("BB")
        elif "Volume" in class_name:
            indicators_used.add("VOL")

    if indicators_used:
        return " + ".join(sorted(indicators_used)) + " Strategy"
    return "Custom Strategy"


# ======================================================================
# Quick-test helpers
# ======================================================================

_EXAMPLE_IDEAS = [
    "buy when RSI below 30, sell when RSI above 70",
    "buy when EMA 12 crosses above EMA 26, sell when EMA 12 crosses below EMA 26",
    "buy when price drops below lower Bollinger band, sell when price above upper Bollinger band",
    "buy when MACD crosses above signal and RSI below 50, sell when MACD crosses below signal",
    "buy on golden cross, sell on death cross, stop loss 5%, take profit 15%",
    "buy when SMA 20 crosses above SMA 50 and volume above 2x average, sell when SMA 20 crosses below SMA 50",
    "buy when RSI below 25 and price below EMA 200, sell when RSI above 75",
]


def demo_parser() -> None:
    """Run the parser on example ideas and print results."""
    for idea in _EXAMPLE_IDEAS:
        print(f"INPUT: \"{idea}\"")
        result = parse_trade_idea(idea)
        if result.success:
            print(f"  ✓ {result.message}")
            print(result.strategy.describe_rules())
        else:
            print(f"  ✗ {result.message}")
        if result.warnings:
            for w in result.warnings:
                print(f"  ⚠ {w}")
        print()
