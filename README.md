# falsifylab-alpha-mcp

MCP server surfacing FalsifyLab daily alpha to Claude Code / Cursor / any MCP-compatible client.

## Tools

- `top_yield_farms` — last 24h DeFi yield picks with realistic APY (emissions stripped)
- `hl_vault_leaderboard` — Hyperliquid vault leaderboard (NAV, 30d return, max DD, score)
- `insider_buy_clusters` — Form 4 cluster buys (3+ insiders bought same ticker)
- `sec8k_material_today` — material 8-K filings filtered by item code
- `macro_tape` — SPX/NDX/VIX/UST yields/DXY/GOLD/WTI/BTC/ETH live snapshot
- `etf_flow_today` — US spot BTC + ETH ETF net flows
- `polymarket_whale_positions` — top whale wallets + active positions

## Install

```bash
pip install falsifylab-alpha-mcp
```

## Claude Code config

```bash
claude mcp add falsifylab-alpha \
  --env FL_API_KEY=<your-key-from-falsifylab.com> \
  -- python -m falsifylab_alpha_mcp
```

Or in `.mcp.json`:

```json
{
  "mcpServers": {
    "falsifylab-alpha": {
      "command": "python",
      "args": ["-m", "falsifylab_alpha_mcp"],
      "env": {"FL_API_KEY": "fl_xxx"}
    }
  }
}
```

## Pricing

- **Free** (no API key): last-24h cached data, rate-limited
- **Pro $19/mo** (API key): real-time, 90-day history, all filters, no rate limit

Get a key at [falsifylab.com/pro](https://falsifylab.com/pro).

## License

MIT
