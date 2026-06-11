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

VERSION = "0.3.5"
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
        "description": (
            "Rank DeFi liquidity-pool yield farms by realistic APY with token "
            "emissions stripped out (so a 200% headline that is 95% inflationary "
            "rewards is demoted, not surfaced). "
            "Use when an agent needs current places to deploy stablecoin or "
            "blue-chip capital for yield, or to sanity-check a farm a user "
            "mentions. Pair with active_airdrop_farms for points-program upside. "
            "Returns an array of pools: protocol, chain, symbol, tvl_usd, "
            "real_apy (emissions-adjusted), base_apy, reward_apy, il_risk note, "
            "and oracle-exposure flag. Sorted by real_apy descending. "
            "Refreshed every 24h from the FalsifyLab aggregator over DefiLlama. "
            "Free tier returns cached data, top 5; Pro returns real-time, up to 100."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10,
                           "description": "Max pools to return. Range 1-50 (free tier capped at 5). Default 10."},
                "min_apy": {"type": "number", "default": 0,
                             "description": "Floor on emissions-adjusted real_apy, in percent (e.g. 8 = 8%). Default 0 (no floor)."},
                "asset": {"type": "string",
                           "description": "Optional. Restrict to pools for one asset symbol, e.g. 'USDC', 'ETH', 'SOL'. Omit for all assets."},
            },
        },
    },
    {
        "name": "hl_vault_leaderboard",
        "description": (
            "Rank Hyperliquid copy-trading vaults by a composite quality score "
            "(blends 30d return, max drawdown, and follower count) so an agent "
            "can find vaults worth following rather than just the highest raw "
            "return. "
            "Use when a user asks which Hyperliquid vaults to copy/follow, or to "
            "look up a vault's risk profile before allocating. "
            "Returns an array of vaults: name, address, nav_usd, return_30d (pct), "
            "max_drawdown (pct), follower_count, and composite score (0-1). "
            "Real-time from the Hyperliquid info API at call time. "
            "Free tier returns top 5; Pro returns up to 100. Reference data only, "
            "not allocation advice — verify on-chain before copying."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10,
                           "description": "Max vaults to return. Range 1-100 (free tier capped at 5). Default 10."},
                "sort_by": {"type": "string",
                              "enum": ["score", "tvl", "return_30d", "followers"],
                              "default": "score",
                              "description": "Ranking key: 'score' (composite quality, default), 'tvl' (vault size), 'return_30d' (raw 30-day return), or 'followers' (popularity)."},
            },
        },
    },
    {
        "name": "insider_buy_clusters",
        "description": (
            "Detect SEC Form 4 insider-buy clusters: tickers where 3+ distinct "
            "insiders made open-market purchases within a short window — a "
            "stronger bullish tell than any single buy. Filtered to transaction "
            "code 'P' (open-market buys); awards, grants, gifts, and option "
            "exercises are excluded. "
            "Use when scanning for bottom-up bullish equity signals or "
            "corroborating conviction on a specific name. Pair with "
            "sec8k_material_today and confluence_today. "
            "Returns clusters: ticker, insider_count, total_usd bought, list of "
            "(insider name, role, shares, price), and the filing window. "
            "Sourced from EDGAR Form 4 feeds. Free tier cached/limited; Pro "
            "real-time with full history."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_hours": {"type": "integer", "default": 24,
                                   "description": "Look-back window for grouping buys into a cluster, in hours. Typical 24-48. Default 24."},
                "min_insiders": {"type": "integer", "default": 3,
                                   "description": "Minimum distinct insiders buying the same ticker to qualify as a cluster. Default 3."},
            },
        },
    },
    {
        "name": "sec8k_material_today",
        "description": (
            "Surface today's material SEC 8-K filings, filtered to the item "
            "codes that actually move price, so an agent skips routine noise. "
            "Use when monitoring for fresh corporate catalysts (earnings, "
            "M&A, executive departures, dilution, restatements, delisting) "
            "across the market or for one ticker. "
            "Returns filings: ticker, company, item_codes, filed_at (UTC), "
            "headline summary, and EDGAR link. Item codes covered: 2.02 "
            "(results/earnings), 5.02 (officer/director change), 2.01 "
            "(completion of acquisition), 3.02 (unregistered equity/dilution), "
            "4.02 (non-reliance/restatement), 3.01 (delisting/listing-rule). "
            "Polls EDGAR through the trading day. Free tier cached; Pro real-time."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"},
                            "description": "Optional. Restrict to these 8-K item codes as strings, e.g. ['2.02','5.02']. Omit for all covered material items."},
                "ticker": {"type": "string",
                            "description": "Optional. Restrict to one ticker symbol, e.g. 'NVDA'. Omit for the whole market."},
            },
        },
    },
    {
        "name": "macro_tape",
        "description": (
            "One-call snapshot of the US macro tape across equities, rates, FX, "
            "commodities, and crypto — the cross-asset context an agent needs "
            "before reasoning about any single market. "
            "Use at the start of a market-analysis task, or when a user asks "
            "'how are markets today'. "
            "Returns a row per instrument: symbol, last price, change_1d (pct), "
            "change_5d (pct). Default universe: SPX, NDX, RUT, VIX, UST 2y, "
            "UST 10y, DXY, GOLD, WTI, BTC, ETH. "
            "Quotes are near-real-time at call. Free tier available without a key."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"},
                              "description": "Optional. Subset of the universe to return, e.g. ['SPX','VIX','BTC']. Omit to get the full default tape."},
            },
        },
    },
    {
        "name": "etf_flow_today",
        "description": (
            "Today's aggregate net flows into US-listed spot crypto ETFs — a "
            "proxy for institutional demand. "
            "Use when gauging institutional bid/offer behind BTC or ETH, or to "
            "confirm a move is flow-driven. "
            "Returns: btc_net_flow_usd, eth_net_flow_usd, flow_streak_days "
            "(consecutive same-sign days), and cumulative_aum_usd. Takes no "
            "parameters — always the latest cross-issuer aggregate. "
            "Source: SoSoValue, updated each US session. Free tier cached; Pro "
            "real-time."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "active_airdrop_farms",
        "description": (
            "Detect likely active airdrop / points-farming programs by flagging "
            "DefiLlama pools whose reported APY exceeds base+reward APY — the "
            "gap implies an unpriced incentive (points) program. "
            "Use when a user wants airdrop-farming opportunities or to assess "
            "the capital and chain needed to farm one. Pair with "
            "top_yield_farms for pure yield. "
            "Returns pools: protocol, chain, symbol, real_apy, yield_gap, "
            "tvl_usd, est_capital_required_usd, and a confidence score (0-1) that "
            "the gap is a points program. Sourced from the Suki defi_scanner. "
            "Free tier cached/limited; Pro real-time, up to 100. Speculative by "
            "nature — no airdrop is guaranteed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10,
                           "description": "Max opportunities to return. Range 1-100 (free tier capped at 5). Default 10."},
                "min_apy": {"type": "number", "default": 0,
                             "description": "Floor on emissions-adjusted real_apy, in percent. Default 0 (no floor)."},
                "min_tvl_usd": {"type": "number", "default": 0,
                                  "description": "Exclude pools with TVL below this many USD (filters thin/risky pools). Default 0 (no floor)."},
                "chain": {"type": "string",
                            "description": "Optional. Restrict to one chain, e.g. 'ethereum', 'base', 'arbitrum', 'solana'. Omit for all chains."},
            },
        },
    },
    {
        "name": "polymarket_whale_positions",
        "description": (
            "Surface the largest active Polymarket positions held by tracked "
            "whale wallets — a sentiment/conviction read on prediction markets. "
            "Use when a user asks what smart money is betting on Polymarket, or "
            "for a copy-trade reference on a specific event. "
            "Returns positions: wallet, market question, outcome side, "
            "position_size_usd, avg_entry_price, and current price. Only "
            "positions above min_position_usd are included. "
            "Near-real-time from Polymarket data APIs. Pro tier (paid) — not "
            "trading advice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_position_usd": {"type": "integer", "default": 10000,
                                       "description": "Minimum position size to include, in USD. Default 10000 (only positions >$10k)."},
            },
        },
    },
    {
        "name": "earnings_drift_radar",
        "description": (
            "Radar for post-earnings-announcement drift (PEAD) and pre-print "
            "IV-crush setups in US equities. "
            "Use when planning around an earnings calendar — either to find "
            "names likely to drift after a print, or high IV-crush-probability "
            "names to avoid being long premium into. "
            "Returns candidates: ticker, report_date, expected_drift_pct, "
            "iv_crush_prob (0-1), surprise history, and direction. Forward-looking "
            "over the configured horizon. Pro tier (paid). Probabilistic — "
            "backtest before acting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "default": 7,
                                 "description": "Forward window of earnings dates to scan, in calendar days. Default 7."},
                "min_drift_pct": {"type": "number", "default": 3.0,
                                    "description": "Only return names whose expected post-print drift magnitude is at least this percent. Default 3.0."},
                "min_iv_crush_prob": {"type": "number", "default": 0.6,
                                        "description": "Only return names with modeled IV-crush probability at or above this (0.0-1.0). Default 0.6."},
                "limit": {"type": "integer", "default": 10,
                           "description": "Max candidates to return. Range 1-100. Default 10."},
            },
        },
    },
    {
        "name": "token_unlock_radar",
        "description": (
            "Forward radar for crypto token unlocks (vesting cliffs) that create "
            "supply overhang — useful for spotting potential sell-pressure setups. "
            "Use when assessing the supply side of a token's near-term outlook, "
            "or screening for unlock-driven short/avoid setups. "
            "Returns upcoming unlocks: token, unlock_date, unlock_usd, "
            "unlock_pct_of_circulating, and recipient category (team/investor/"
            "ecosystem). Sorted by date. Forward-looking over the configured "
            "horizon. Pro tier (paid)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "default": 14,
                                 "description": "Forward window of unlock dates to scan, in calendar days. Default 14."},
                "min_unlock_usd": {"type": "number", "default": 1000000,
                                     "description": "Only return unlocks worth at least this many USD at current price. Default 1000000 ($1M)."},
                "min_unlock_pct_circ": {"type": "number", "default": 1.0,
                                          "description": "Only return unlocks that are at least this percent of circulating supply (impact filter). Default 1.0 (1%)."},
                "limit": {"type": "integer", "default": 10,
                           "description": "Max unlocks to return. Range 1-100. Default 10."},
            },
        },
    },
    {
        "name": "fed_comm_radar",
        "description": (
            "Radar for upcoming Federal Reserve speaker events, scored by each "
            "speaker's historical rate-expectation sensitivity, to flag macro "
            "volatility windows before they hit. "
            "Use when timing macro risk — e.g. before sizing into a rate-sensitive "
            "position, or to know if a vol-inducing Fed event is imminent. "
            "Returns events: speaker, role, event_time (UTC), hist_rate_delta_bps "
            "(typical post-event move in fed-funds expectations), and a volatility "
            "flag. Forward-looking over the configured window. Pro tier (paid)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours_ahead": {"type": "integer", "default": 48,
                                  "description": "Forward window of Fed events to scan, in hours. Default 48."},
                "min_rate_delta_bps": {"type": "number", "default": 5.0,
                                         "description": "Only return speakers whose historical post-event move in rate expectations is at least this many basis points. Default 5.0."},
                "limit": {"type": "integer", "default": 10,
                           "description": "Max events to return. Range 1-100. Default 10."},
            },
        },
    },
    {
        "name": "confluence_today",
        "description": (
            "The flagship cross-source tool: returns tickers/assets where 2+ "
            "independent FalsifyLab signals align in the last 24h, so an agent "
            "gets pre-correlated conviction instead of one isolated signal. "
            "Stacks insider Form 4 clusters, material 8-K filings, ETF flows, "
            "DeFi yields, airdrop activity, Hyperliquid vault concentration, "
            "Polymarket whale positions, earnings drift, token unlocks, and Fed "
            "comm events. "
            "Use this FIRST when a user asks 'what looks interesting today' — it "
            "is the highest-level scan; drill into the underlying single-signal "
            "tools for detail. "
            "Returns: asset/ticker, signal_count, which signals fired, and a "
            "per-asset detail list. Higher signal_count = more corroboration. "
            "Pro tier (paid) — this stacking is the differentiator."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_signals": {"type": "integer", "default": 2,
                                  "description": "Minimum number of distinct signals that must agree on one asset to include it. Higher = stricter/more conviction. Default 2."},
                "kind": {"type": "string",
                          "enum": ["equity", "crypto", "macro", "all"],
                          "default": "all",
                          "description": "Signal universe to scan: 'equity' (Form 4 + 8-K + ETF), 'crypto' (yield + airdrop + HL vault + Polymarket + unlock), 'macro' (Fed comm + macro tape), or 'all' (default)."},
                "limit": {"type": "integer", "default": 10,
                           "description": "Max confluent assets to return. Range 1-100. Default 10."},
            },
        },
    },
    {
        "name": "onchain_smart_wallets",
        "description": (
            "Top-scored on-chain wallets from FalsifyLab's live Solana "
            "copy-trading bot — production wallet scores, not speculative "
            "analytics. Each wallet's composite score blends 5 weighted "
            "sub-scores (profitability, consistency, risk, copyability, "
            "behavior_quality), calibrated against realized copy-trade PnL; "
            "consistency and behavior_quality are weighted highest (rho +0.76 "
            "and +0.755 to PnL). "
            "Use when a user wants smart-money wallets to copy or watch on-chain, "
            "or to vet a wallet's quality before following. "
            "Returns wallets: address, status (MONITORED/CANDIDATE/ACTIVE/"
            "DEMOTED), provider, the 5 sub-scores + composite, and scan window. "
            "Pro tier (paid). Reference only — verify before copying."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_score": {"type": "number", "default": 0.5,
                                "description": "Composite-score floor, 0.0-1.0. Higher returns only higher-quality wallets. Default 0.5."},
                "status": {"type": "string",
                            "enum": ["MONITORED", "CANDIDATE", "ACTIVE", "DEMOTED"],
                            "description": "Optional. Filter by wallet lifecycle status: ACTIVE/MONITORED (currently tracked), CANDIDATE (under evaluation), DEMOTED (dropped). Omit for all."},
                "chain": {"type": "string",
                           "description": "Optional. Filter by chain, e.g. 'solana' (primary), 'ethereum'. Omit for all chains."},
                "limit": {"type": "integer", "default": 10,
                           "description": "Max wallets to return. Range 1-100. Default 10."},
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
        # 2026-06-07: worker serves at /api/earnings_drift_radar not /api/earnings_drift
        return _api_get("/api/earnings_drift_radar", args)
    if name == "token_unlock_radar":
        return _api_get("/api/token_unlock_radar", args)
    if name == "fed_comm_radar":
        return _api_get("/api/fed_comm_radar", args)
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
