#!/usr/bin/env python3
"""falsifylab-alpha-mcp — MCP server for Claude/Cursor surfacing
FalsifyLab daily alpha (yield farms, HL vaults, insider trades, SEC 8-Ks).

Architecture:
  - MCP server (this file) runs LOCALLY on user's machine via stdio
  - Server calls backend at https://api.falsifylab.com (Cloudflare Worker)
  - Backend serves cached data: latest_yields, hl_vaults, insider_buys,
    sec8k_today, macro_tape, etc.
  - Free tier: read-only access to last-24h aggregated cached data
  - Paid tier ($19/mo): real-time + extended history + filters

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
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

VERSION = "0.1.1"
API_BASE = os.environ.get("FL_API_BASE", "https://api.falsifylab.com")
API_KEY = os.environ.get("FL_API_KEY", "")
USER_AGENT = f"falsifylab-alpha-mcp/{VERSION}"


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
        "name": "confluence_today",
        "description": "Cross-source confluence: tickers/assets where 2+ "
                       "FalsifyLab signals align in the last 24h. Stacks "
                       "insider Form 4 clusters, material 8-K filings, ETF "
                       "flows, DeFi yields, airdrop activity, HL vault "
                       "concentration, and Polymarket whale positions. "
                       "Higher signal_count = more conviction. The Pro-tier "
                       "differentiator: nobody else stacks these in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_signals": {"type": "integer", "default": 2,
                                  "description": "min # of signals that must agree per asset"},
                "kind": {"type": "string",
                          "enum": ["equity", "crypto", "all"],
                          "default": "all",
                          "description": "limit to equity (Form 4 + 8-K + ETF) "
                                         "or crypto (yield + airdrop + HL vault + Polymarket) signals"},
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
    if name == "confluence_today":
        return _api_get("/api/confluence", args)
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
        result = call_tool(name, args)
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
