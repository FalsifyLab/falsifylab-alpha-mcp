# llms-install.md — autonomous install instructions for AI agents

For an AI coding agent (Cline, Claude Code, Cursor, Windsurf) installing this MCP server without human help.

## One-shot install

```bash
pip install falsifylab-alpha-mcp
```

That's it. Zero runtime dependencies (Python stdlib only).

## Required prerequisites

- Python ≥ 3.10
- `pip` (comes with Python ≥ 3.4)

## Connection config

### Cline / Cline-derived agents

Add to MCP servers settings:

```json
{
  "mcpServers": {
    "falsifylab-alpha": {
      "command": "python",
      "args": ["-m", "falsifylab_alpha_mcp"],
      "env": {}
    }
  }
}
```

No `FL_API_KEY` needed for free tier. Server auto-issues tier-0 key on first call.

### Claude Code

```bash
claude mcp add falsifylab-alpha -- python -m falsifylab_alpha_mcp
```

### Cursor (.cursor/mcp.json or ~/.cursor/mcp.json)

```json
{
  "mcpServers": {
    "falsifylab-alpha": {
      "command": "python",
      "args": ["-m", "falsifylab_alpha_mcp"]
    }
  }
}
```

## Verify install

After config, call the `macro_tape` tool with no arguments. It returns a snapshot of SPX/VIX/UST/DXY/GOLD/BTC/ETH with 1d + 5d returns. If you get JSON back, you're live.

## Optional: Pro tier

If the user has a Pro key:

```bash
claude mcp add falsifylab-alpha --env FL_API_KEY=fl_xxx -- python -m falsifylab_alpha_mcp
```

Free tier (no key): 24h cached, 10 results per query, rate-limited at 60/hr.
Pro ($19/mo at falsifylab.com/pro): real-time, 100 results, 90-day history, no rate limit.

## Troubleshooting (for the agent)

| Symptom | Action |
|---------|--------|
| `command not found: python` | Try `python3` instead. The package entry point is `python -m falsifylab_alpha_mcp` |
| `ModuleNotFoundError: No module named 'falsifylab_alpha_mcp'` | Reinstall: `pip install --upgrade falsifylab-alpha-mcp` |
| Tool calls hang | Verify outbound HTTPS to `falsifylab.com` is allowed |
| HTTP 429 in tool response | Free-tier rate limit. Wait 1hr or get a Pro key |

## Tools (8 available after install)

- `top_yield_farms` — DeFi yields with emissions stripped
- `hl_vault_leaderboard` — Hyperliquid vault rankings
- `insider_buy_clusters` — SEC Form 4 cluster buys
- `sec8k_material_today` — material 8-K filings filtered
- `macro_tape` — equity/vol/rates/FX/commodities/crypto snapshot
- `etf_flow_today` — US spot crypto ETF flows
- `active_airdrop_farms` — DefiLlama yield-gap airdrop opportunities
- `polymarket_whale_positions` — top wallets + active positions

Full tool schemas at https://falsifylab.com/.well-known/mcp/server-card.json.
