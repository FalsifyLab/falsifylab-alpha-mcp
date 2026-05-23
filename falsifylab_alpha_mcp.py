#!/usr/bin/env python3
"""falsifylab-alpha-mcp — MCP server for Claude/Cursor surfacing
FalsifyLab daily alpha (yield farms, HL vaults, insider trades, SEC 8-Ks).

Architecture:
  - MCP server (this file) runs LOCALLY on user's machine via stdio
  - Server calls backend at https://falsifylab.com/api/* (Cloudflare-fronted)
  - Backend serves cached data: latest_yields, hl_vaults, insider_buys,
    sec8k_today, macro_tape, etc.
  - Free tier: read-only access to last-24h aggregated cached data
  - Paid tier ($19/mo): real-time + extended history + filters
  - Alternative: point any MCP client directly at https://mcp.falsifylab.com/mcp
    for the hosted MCP transport (no pypi install required).

Install (end user):
  pip install falsifylab-alpha-mcp
  # Claude Code mcp config:
  # claude mcp add falsifylab-alpha --env FL_API_KEY=<your-key>
  # or in .mcp.json:
  # {"mcpServers": {"falsifylab-alpha": {
  #     "command": "python", "args": ["-m", "falsifylab_alpha_mcp"],
  #     "env": {"FL_API_KEY": "fl_xxx"}
  # }}}
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
from typing import Any

VERSION = "0.3.3"
API_BASE = os.environ.get("FL_API_BASE", "https://falsifylab.com")
API_KEY = os.environ.get("FL_API_KEY", "")
USER_AGENT = f"falsifylab-alpha-mcp/{VERSION}"

# Telemetry POST endpoint — sends Pro-wall-hit events to the FL Worker so
# they land in /var/log/fl_mcp.jsonl alongside direct /api/* hits. Without
# this, MCP-stdio path is invisible to operator telemetry. Best-effort:
# silent on any failure, never blocks a tool call.
TELEM_URL = os.environ.get("FL_TELEM_URL", f"{API_BASE}/api/_telem")
TELEM_ENABLED = os.environ.get("FL_TELEM_DISABLE", "").lower() not in ("1", "true", "yes")


def _emit_telem(event: str, tool: str = "?", has_key: bool = False) -> None:
    """Fire-and-forget POST to FL Worker /api/_telem. Never raises."""
    if not TELEM_ENABLED:
        return
    try:
        key_hash = ""
        if API_KEY:
            key_hash = hashlib.sha256(API_KEY.encode()).hexdigest()[:12]
        body = json.dumps({
            "event": event,
            "tool": tool,
            "has_key": has_key,
            "key_hash": key_hash,
            "mcp_version": VERSION,
        }).encode()
        req = urllib.request.Request(
            TELEM_URL, data=body, method="POST",
            headers={"Content-Type": "application/json",
                      "User-Agent": USER_AGENT})
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass

# Free-tier gating (v0.3.2 — banked from 2026-05-20 conversion-funnel diagnosis):
# 1,229 weekly PyPI installs + 0 paid conversions. Free tier had no upgrade
# pressure. Now: 3 free tools, rest are Pro-only with explicit upgrade stub.
FREE_ALLOWED_TOOLS = {"top_yield_farms", "hl_vault_leaderboard", "macro_tape"}
FREE_RESULT_CAP = 5  # was 10 — narrow further to surface Pro value sooner
TOOL_CALL_LOG_PATH = Path(
    os.environ.get("FL_MCP_TOOL_CALL_LOG", "/var/log/falsifylab/mcp_tool_calls.jsonl")
)

# Free-tier upgrade nudge — surfaces in every free-tier response so agents
# can relay the upgrade path to the human. Pro $19/mo unlocks real-time +
# 100 results + 90-day history; Pro Plus $49/mo adds webhook events.
UPGRADE_NUDGE_FREE = (
    "free tier (24h cached, 5 results/query, 3 of 13 tools). "
    "Pro $19/mo: real-time + 100 results + all 13 tools + 90-day history. "
    "Pro Plus $49/mo: real-time + webhooks. "
    "upgrade → https://falsifylab.com/pro?ref=tool-nudge"
)
UPGRADE_NUDGE_TRUNCATED = (
    "results truncated to 5 (free-tier limit). "
    "Pro $19/mo returns up to 100. → https://falsifylab.com/pro?ref=tool-trunc"
)
PRO_FEATURE_STUB_BUILDER = lambda tool_name: {
    "error": "pro_feature",
    "message": (
        f"'{tool_name}' is a Pro feature. "
        f"Free tier exposes: {sorted(FREE_ALLOWED_TOOLS)}. "
        f"Upgrade $19/mo to unlock all 13 tools including {tool_name}. "
        f"https://falsifylab.com/pro?ref=tool-gate"
    ),
    "upgrade_url": "https://falsifylab.com/pro?ref=tool-gate",
    "free_tools": sorted(FREE_ALLOWED_TOOLS),
    "_pro_only_tool": tool_name,
}


# ===== MCP protocol scaffold (JSON-RPC over stdio) =====

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _recv() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _api_get(path: str, params: dict | None = None) -> dict:
    if params:
        from urllib.parse import urlencode
        path = f"{path}?{urlencode(params)}"
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            **({"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:400]
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)[:200]}


def _log_tool_call(name: str, args: dict | None, api_key: str) -> None:
    if os.environ.get("FL_DISABLE_TELEMETRY"):
        return
    try:
        TOOL_CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "tool": name,
            "args_keys": sorted((args or {}).keys())[:5],
            "has_api_key": bool(api_key),
            "key_hash": (
                hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
                if api_key
                else None
            ),
            "version": VERSION,
        }
        with TOOL_CALL_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception:
        # Telemetry must never break tool calls.
        pass


# ===== Tool definitions =====

TOOLS = [
    {
        "name": "top_yield_farms",
        "description": "Latest 24h top DeFi yield farm picks with realistic "
                       "APY (emissions stripped), risk notes, TVL, protocol. "
                       "Sourced from FalsifyLab daily aggregator.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10,
                           "description": "max results (1-50)"},
                "min_apy": {"type": "number", "default": 0,
                             "description": "filter floor in pct"},
                "asset": {"type": "string",
                           "description": "filter by asset symbol (BTC, ETH, SOL, etc.)"},
            },
        },
    },
    {
        "name": "hl_vault_leaderboard",
        "description": "Hyperliquid vault leaderboard with NAV, 30d return, "
                       "max drawdown, follower count, composite score. "
                       "Real-time scrape of HL info API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
                "sort_by": {"type": "string",
                              "enum": ["score", "tvl", "return_30d", "followers"],
                              "default": "score"},
            },
        },
    },
    {
        "name": "insider_buy_clusters",
        "description": "Form 4 insider buy clusters (3+ insiders bought same "
                       "ticker in 24-48h). Bullish signal. Filtered to "
                       "open-market purchases (P code), excluding awards/gifts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_hours": {"type": "integer", "default": 24},
                "min_insiders": {"type": "integer", "default": 3},
            },
        },
    },
    {
        "name": "sec8k_material_today",
        "description": "Material SEC 8-K filings today filtered by item code: "
                       "2.02 (earnings), 5.02 (officer change), 2.01 (M&A), "
                       "3.02 (dilution), 4.02 (restatement), 3.01 (delisting).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"},
                            "description": "item codes (e.g. ['2.02','5.02'])"},
                "ticker": {"type": "string",
                            "description": "filter by ticker symbol"},
            },
        },
    },
    {
        "name": "macro_tape",
        "description": "Live US macro snapshot: SPX, NDX, RUT, VIX, UST 2y/10y, "
                       "DXY, GOLD, WTI, BTC, ETH. Last price + 1d/5d % change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "etf_flow_today",
        "description": "US-listed spot crypto ETF aggregate flows today. "
                       "BTC + ETH net flow, 5d streak, cumulative AUM. "
                       "Source: SoSoValue.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "active_airdrop_farms",
        "description": "Active airdrop / points-farming opportunities. "
                       "Detected from DefiLlama yield gaps (where reported "
                       "APY exceeds base+rewards = likely points program). "
                       "Includes realistic APY, TVL, capital required, "
                       "confidence score. Sourced from Suki defi_scanner.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
                "min_apy": {"type": "number", "default": 0,
                             "description": "filter floor pct (realistic APY)"},
                "min_tvl_usd": {"type": "number", "default": 0,
                                  "description": "filter pools <X TVL"},
                "chain": {"type": "string",
                            "description": "filter (ethereum, base, arbitrum, etc.)"},
            },
        },
    },
    {
        "name": "polymarket_whale_positions",
        "description": "Top Polymarket whale wallets and their current "
                       "active positions sized >$10k. Copy-trade reference.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_position_usd": {"type": "integer", "default": 10000},
            },
        },
    },
    {
        "name": "earnings_drift_radar",
        "description": "Post-earnings drift radar for US equities. Surfaces "
                       "names with outsized post-print drift or high pre-print "
                       "IV crush probability over the next sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "default": 7},
                "min_drift_pct": {"type": "number", "default": 3.0},
                "min_iv_crush_prob": {"type": "number", "default": 0.6},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "token_unlock_radar",
        "description": "Forward token unlock radar for crypto assets. Flags "
                       "near-term unlocks by date, size, and circulating-supply "
                       "impact to identify supply-overhang setups.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "default": 14},
                "min_unlock_usd": {"type": "number", "default": 1000000},
                "min_unlock_pct_circ": {"type": "number", "default": 1.0},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "fed_comm_radar",
        "description": "Fed communication radar. Tracks upcoming Fed speaker "
                       "events and historical rate-delta sensitivity to flag "
                       "macro volatility windows within the next N hours.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours_ahead": {"type": "integer", "default": 48},
                "min_rate_delta_bps": {"type": "number", "default": 5.0},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "confluence_today",
        "description": "Cross-source confluence: tickers/assets where 2+ "
                       "FalsifyLab signals align in the last 24h. Stacks "
                       "insider Form 4 clusters, material 8-K filings, ETF "
                       "flows, DeFi yields, airdrop activity, HL vault "
                       "concentration, Polymarket whale positions, earnings "
                       "drift radar, token unlock radar, and Fed comm radar. "
                       "Higher signal_count = more conviction. The Pro-tier "
                       "differentiator: nobody else stacks these in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_signals": {"type": "integer", "default": 2,
                                  "description": "min # of signals that must agree per asset"},
                "kind": {"type": "string",
                          "enum": ["equity", "crypto", "macro", "all"],
                          "default": "all",
                          "description": "limit to equity (Form 4 + 8-K + ETF) "
                                         "crypto (yield + airdrop + HL vault + Polymarket + unlock) "
                                         "or macro (Fed comm + macro tape) signals"},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "onchain_smart_wallets",
        "description": "Top-scored on-chain wallets surfaced by FalsifyLab's "
                       "live Solana copy-trading bot. Composite score from 5 "
                       "weighted sub-scores (profitability, consistency, risk, "
                       "copyability, behavior_quality) calibrated to actual "
                       "copy-trade PnL correlations. Consistency + behavior "
                       "weighted highest (rho +0.76 and +0.755 to PnL). "
                       "Returns wallet address, status (MONITORED/CANDIDATE/"
                       "DEMOTED), provider, score breakdown, scan window. "
                       "Production data from a real copy-trading bot, not "
                       "speculative analytics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_score": {"type": "number", "default": 0.5,
                                "description": "composite score floor (0.0-1.0)"},
                "status": {"type": "string",
                            "enum": ["MONITORED", "CANDIDATE", "ACTIVE", "DEMOTED"],
                            "description": "filter by wallet status"},
                "chain": {"type": "string",
                           "description": "filter by chain (solana, ethereum, etc.)"},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
]


# ===== Tool dispatch =====

def call_tool(name: str, args: dict) -> dict:
    if name == "top_yield_farms":
        return _api_get("/api/yield/top", args)
    if name == "hl_vault_leaderboard":
        return _api_get("/api/hl_vaults", args)
    if name == "insider_buy_clusters":
        return _api_get("/api/form4/clusters", args)
    if name == "sec8k_material_today":
        return _api_get("/api/sec8k/today", args)
    if name == "macro_tape":
        return _api_get("/api/macro", args)
    if name == "etf_flow_today":
        return _api_get("/api/etf_flow", args)
    if name == "active_airdrop_farms":
        return _api_get("/api/airdrops", args)
    if name == "polymarket_whale_positions":
        return _api_get("/api/polymarket/whales", args)
    if name == "earnings_drift_radar":
        return _api_get("/api/earnings_drift", args)
    if name == "token_unlock_radar":
        return _api_get("/api/token_unlocks", args)
    if name == "fed_comm_radar":
        return _api_get("/api/fed_comm", args)
    if name == "confluence_today":
        return _api_get("/api/confluence", args)
    if name == "onchain_smart_wallets":
        return _api_get("/api/onchain/wallets", args)
    return {"error": f"unknown tool: {name}"}


# ===== MCP handlers =====

def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "falsifylab-alpha",
                                "version": VERSION},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        _log_tool_call(name, args, API_KEY)

        # Pro-only gate: free tier hits a non-free tool → return stub with
        # explicit upgrade path. Banked from 2026-05-20 funnel diagnosis.
        if not API_KEY and name not in FREE_ALLOWED_TOOLS:
            # Known tool but Pro-only
            known_tools = {t["name"] for t in TOOLS}
            if name in known_tools:
                result = PRO_FEATURE_STUB_BUILDER(name)
                # v0.3.3: emit mcp_wall_hit telem so operator can count
                # MCP-side Pro-tool wall hits. Best-effort, non-blocking.
                _emit_telem("mcp_wall_hit", tool=name, has_key=False)
            else:
                result = {"error": f"unknown tool: {name}"}
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text",
                                  "text": json.dumps(result, indent=2)[:8000]}],
                },
            }

        # Free-tier limit cap: narrow result count to FREE_RESULT_CAP regardless
        # of what user requested. Pro keys pass through.
        if not API_KEY and isinstance(args, dict):
            requested_limit = args.get("limit")
            if requested_limit is None or (
                isinstance(requested_limit, int) and requested_limit > FREE_RESULT_CAP
            ):
                args["limit"] = FREE_RESULT_CAP

        result = call_tool(name, args)

        # Inject upgrade nudge for free-tier callers (no FL_API_KEY).
        # Placed at top-of-dict so it survives MCP-client truncation.
        if isinstance(result, dict) and "error" not in result and not API_KEY:
            count = result.get("count")
            if isinstance(count, int) and count >= FREE_RESULT_CAP:
                upgrade = UPGRADE_NUDGE_TRUNCATED
            else:
                upgrade = UPGRADE_NUDGE_FREE
            result = {"_upgrade": upgrade, **result}
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "content": [{"type": "text",
                              "text": json.dumps(result, indent=2)[:8000]}],
            },
        }

    if method == "notifications/initialized":
        return None  # no response for notifications

    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    }


def main() -> int:
    while True:
        req = _recv()
        if req is None:
            break
        resp = handle(req)
        if resp is not None:
            _send(resp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
