#!/usr/bin/env python3
"""
Lightweight HTTP server that serves the web UI and handles backtest API calls.

Usage:
    python web_server.py              # Start on port 8877
    python web_server.py --port 9000  # Custom port

Endpoints:
    GET  /                       → serves ui/index.html
    GET  /api/coins              → list of cached coin symbols
    POST /api/backtest           → run a backtest from a trade idea
    GET  /api/examples           → list example trade ideas
    POST /api/analyze-screenshot → analyze a TradingView screenshot via Claude Vision
    POST /api/translate-idea     → translate free-form text to parser syntax via AI
"""

import argparse
import copy
import json
import os
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from data.storage import load_ohlcv, has_cached_data, list_cached_symbols
from engine.backtester import run_backtest, BacktestConfig
from strategies.parser import parse_trade_idea, _EXAMPLE_IDEAS
from vision.analyzer import analyze_screenshot, translate_idea


UI_DIR = PROJECT_ROOT / "ui"


class BacktestHandler(BaseHTTPRequestHandler):
    """Handle HTTP requests for the backtest web UI."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_file(UI_DIR / "index.html", "text/html")
        elif path == "/api/coins":
            self._handle_coins()
        elif path == "/api/examples":
            self._handle_examples()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/backtest":
            self._handle_backtest()
        elif parsed.path == "/api/analyze-screenshot":
            self._handle_analyze_screenshot()
        elif parsed.path == "/api/translate-idea":
            self._handle_translate_idea()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    # API handlers
    # ------------------------------------------------------------------

    def _handle_coins(self):
        symbols = sorted(list_cached_symbols("1d"))
        self._json_response({"coins": symbols})

    def _handle_examples(self):
        self._json_response({"examples": _EXAMPLE_IDEAS})

    def _handle_analyze_screenshot(self):
        """Accept an image upload and analyze it with Claude Vision."""
        content_type = self.headers.get("Content-Type", "")

        try:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                self._json_response({"error": "No data received."}, status=400)
                return
            if length > 10 * 1024 * 1024:  # 10 MB limit
                self._json_response({"error": "Image too large (max 10 MB)."}, status=400)
                return

            body = self.rfile.read(length)

            # Parse multipart form data
            api_key = ""
            if "multipart/form-data" in content_type:
                image_bytes, mime_type, fields = _parse_multipart(content_type, body)
                api_key = fields.get("api_key", "")
            elif content_type.startswith("image/"):
                image_bytes = body
                mime_type = content_type.split(";")[0].strip()
                fields = {}
            else:
                self._json_response(
                    {"error": "Expected multipart/form-data or direct image upload."},
                    status=400,
                )
                return

            if not image_bytes:
                self._json_response({"error": "No image found in upload."}, status=400)
                return

        except Exception as e:
            self._json_response({"error": f"Failed to read upload: {e}"}, status=400)
            return

        # Save API key to .env if provided and not already saved
        if api_key:
            _save_api_key(api_key)

        # Analyze with Claude Vision
        result = analyze_screenshot(image_bytes, mime_type, api_key=api_key)

        if result.success:
            self._json_response({
                "trade_idea": result.trade_idea,
                "description": result.description,
                "success": True,
            })
        else:
            self._json_response({
                "error": result.error,
                "success": False,
            }, status=400)

    def _handle_translate_idea(self):
        """Use AI to translate free-form text into parser-compatible syntax."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception as e:
            self._json_response({"error": f"Invalid request body: {e}"}, status=400)
            return

        idea = data.get("idea", "").strip()
        if not idea:
            self._json_response({"error": "No trade idea provided."}, status=400)
            return

        result = translate_idea(idea)

        if result.success:
            self._json_response({
                "trade_idea": result.trade_idea,
                "description": result.description,
                "success": True,
            })
        else:
            self._json_response({
                "error": result.error,
                "success": False,
            }, status=400)

    def _handle_backtest(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception as e:
            self._json_response({"error": f"Invalid request body: {e}"}, status=400)
            return

        idea = data.get("idea", "").strip()
        symbols = data.get("symbols", [])
        capital = data.get("capital", 10000)
        fee_pct = data.get("fee_pct", 0.001)
        slippage_pct = data.get("slippage_pct", 0.001)
        period_days = data.get("period_days", None)  # None = use all data

        if not idea:
            self._json_response({"error": "No trade idea provided."}, status=400)
            return

        if not symbols:
            self._json_response({"error": "No coins selected."}, status=400)
            return

        # Parse the trade idea
        parse_result = parse_trade_idea(idea)
        if not parse_result.success:
            self._json_response({
                "error": parse_result.message,
                "warnings": parse_result.warnings,
            }, status=400)
            return

        # Include normalization warnings in response
        if parse_result.warnings:
            warnings_from_parse = parse_result.warnings
        else:
            warnings_from_parse = []

        strategy = parse_result.strategy
        config = BacktestConfig(
            starting_capital=float(capital),
            fee_pct=float(fee_pct),
            slippage_pct=float(slippage_pct),
        )

        # Run backtest for each symbol
        results = []
        for sym in symbols:
            sym = sym.strip().upper()
            if not has_cached_data(sym, "1d"):
                results.append({"symbol": sym, "error": f"No cached data for {sym}"})
                continue

            df = load_ohlcv(sym, "1d")
            if df is None or df.empty:
                results.append({"symbol": sym, "error": f"Empty data for {sym}"})
                continue

            # Filter by period if specified
            if period_days:
                cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(period_days))
                df = df[df["timestamp"] >= cutoff].reset_index(drop=True)
                if df.empty:
                    results.append({"symbol": sym, "error": f"No data for {sym} in the selected period"})
                    continue

            strat_copy = copy.deepcopy(strategy)
            bt_result = run_backtest(strat_copy, df, symbol=sym, config=config)
            metrics = bt_result.summary()

            # Build trade log
            trades = []
            for t in bt_result.trades:
                trades.append({
                    "entry_date": _fmt_ts(t.entry_time),
                    "exit_date": _fmt_ts(t.exit_time),
                    "entry_price": round(t.entry_price, 2),
                    "exit_price": round(t.exit_price, 2),
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 4),
                    "quantity": round(t.quantity, 8),
                    "fees": round(t.fees, 2),
                })

            # Build equity curve (downsample for large datasets)
            equity = bt_result.equity_curve
            step = max(1, len(equity) // 500)
            eq_sampled = equity[::step]
            if equity and eq_sampled[-1] != equity[-1]:
                eq_sampled.append(equity[-1])

            equity_data = [
                {"date": _fmt_ts(ts), "equity": round(eq, 2)}
                for ts, eq in eq_sampled
            ]

            results.append({
                "symbol": sym,
                "metrics": metrics,
                "trades": trades,
                "equity_curve": equity_data,
            })

        # Strategy description
        rule_desc = strategy.describe_rules()

        self._json_response({
            "strategy_name": strategy.name,
            "strategy_description": rule_desc,
            "warnings": warnings_from_parse,
            "results": results,
        })

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(_sanitize_for_json(data), default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filepath: Path, content_type: str):
        if not filepath.exists():
            self.send_error(404, f"File not found: {filepath.name}")
            return
        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        """Log all requests (needed for Render visibility)."""
        sys.stderr.write("%s - [%s] %s\n" %
                         (self.client_address[0],
                          self.log_date_time_string(),
                          format % args))


def _sanitize_for_json(obj):
    """Replace Infinity/NaN floats with JSON-safe values (recursive)."""
    import math
    if isinstance(obj, float):
        if math.isinf(obj):
            return 9999.99 if obj > 0 else -9999.99
        if math.isnan(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _parse_multipart(content_type: str, body: bytes) -> tuple[bytes | None, str, dict]:
    """Extract image data and text fields from a multipart/form-data body.

    Returns (image_bytes, mime_type, text_fields) or (None, "", {}) if no image found.
    """
    boundary = ""
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[len("boundary="):]
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
            break

    if not boundary:
        return None, "", {}

    delimiter = f"--{boundary}".encode()
    parts = body.split(delimiter)

    image_bytes = None
    mime_type = ""
    text_fields: dict[str, str] = {}

    for part in parts:
        if not part or part.strip() == b"--" or part.strip() == b"":
            continue

        for sep in [b"\r\n\r\n", b"\n\n"]:
            if sep in part:
                header_section, file_data = part.split(sep, 1)
                header_text = header_section.decode("utf-8", errors="replace")

                # Strip trailing \r\n
                if file_data.endswith(b"\r\n"):
                    file_data = file_data[:-2]
                elif file_data.endswith(b"\n"):
                    file_data = file_data[:-1]

                # Extract field name from Content-Disposition
                field_name = ""
                for hdr_part in header_text.split(";"):
                    hdr_part = hdr_part.strip()
                    if hdr_part.startswith('name="') and hdr_part.endswith('"'):
                        field_name = hdr_part[6:-1]
                    elif hdr_part.startswith("name="):
                        field_name = hdr_part[5:].strip('"')

                if "filename=" in header_text.lower():
                    # It's a file upload
                    mime = "image/png"
                    for line in header_text.split("\n"):
                        line_lower = line.strip().lower()
                        if line_lower.startswith("content-type:"):
                            mime = line_lower.split(":", 1)[1].strip()
                            break
                    image_bytes = file_data
                    mime_type = mime
                elif field_name:
                    # It's a text field
                    text_fields[field_name] = file_data.decode("utf-8", errors="replace")
                break

    return image_bytes, mime_type, text_fields


def _save_api_key(api_key: str):
    """Save API key to .env file so it persists across restarts."""
    # On Render the filesystem is ephemeral — just set the env var
    if os.environ.get("RENDER"):
        os.environ["ANTHROPIC_API_KEY"] = api_key
        return

    env_path = PROJECT_ROOT / ".env"
    lines = []
    found = False

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    found = True
                    lines.append(f'ANTHROPIC_API_KEY={api_key}\n')
                else:
                    lines.append(line)

    if not found:
        lines.append(f'ANTHROPIC_API_KEY={api_key}\n')

    with open(env_path, "w") as f:
        f.writelines(lines)

    os.environ["ANTHROPIC_API_KEY"] = api_key


def _fmt_ts(val) -> str:
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    return str(val)[:10]


def main():
    parser = argparse.ArgumentParser(description="Backtester Web UI Server")
    parser.add_argument("--port", type=int, default=None, help="Port to serve on")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    # Render sets PORT env var; local dev uses --port flag or default 8877
    port = int(os.environ.get("PORT", args.port or 8877))
    host = "0.0.0.0"

    UI_DIR.mkdir(parents=True, exist_ok=True)

    server = HTTPServer((host, port), BacktestHandler)
    url = f"http://localhost:{port}"

    print(f"Server running at {url}")

    # Only open browser in local dev (not on Render)
    if not args.no_open and not os.environ.get("RENDER"):
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
