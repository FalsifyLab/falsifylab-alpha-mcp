# falsifylab-alpha-mcp

<!-- mcp-name: io.github.FalsifyLab/falsifylab-alpha-mcp -->

[![smithery badge](https://smithery.ai/badge/falsifylab/falsifylab-alpha-mcp)](https://smithery.ai/servers/falsifylab/falsifylab-alpha-mcp)
[![PyPI](https://img.shields.io/pypi/v/falsifylab-alpha-mcp.svg)](https://pypi.org/project/falsifylab-alpha-mcp/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**MCP data layer for AI-assisted market research.** 10 live finance tools that drop into Claude Code, Cursor, Cline, Windsurf, or any MCP-compatible client. Free tier requires no signup.

> Not a signal service. Not investment advice. Public market data with light enrichment for AI agents. Backtest before acting.

## Two ways to use it

**Option 1: hosted MCP (zero install).** Point your agent at the hosted endpoint, no Python needed.

```json
{
  "mcpServers": {
    "falsifylab-alpha": {
      "url": "https://mcp.falsifylab.com/"
    }
  }
}
```

Free tier auto-applies. OAuth 2.1 + PKCE flow for paid plan via Whop. Streamable HTTP transport. Full OpenAPI 3.1 spec at https://docs.falsifylab.com/openapi.html.

**Option 2: stdio (this package).**

```bash
pip install falsifylab-alpha-mcp
```

Zero runtime dependencies (Python stdlib only). Then wire to your agent. see [client setup](#client-setup).

## What it does

When the user asks your AI agent things like:

- *"What insider clusters are forming today?"*
- *"Show me Hyperliquid vaults with sharp Sharpe and <10% drawdown"*
- *"Are BTC ETF flows confirming or diverging from price action?"*
- *"What's in the macro tape right now?"*
- *"Find Polymarket whales with 60%+ win rate"*

...the agent calls one of 10 tools and grounds its answer in real-time numbers from public-market data — instead of speculating from training-data knowledge.

## The 10 tools

| Tool | Returns | Use case |
|------|---------|----------|
| `top_yield_farms` | DeFi yields with emissions stripped, IL risk priced | Find real yield, not headline yield |
| `hl_vault_leaderboard` | Hyperliquid vaults by NAV / 30d / drawdown / score | Copy-trade reference |
| `insider_buy_clusters` | SEC Form 4 cluster buys (3+ insiders, 24h window) | Equity conviction signal |
| `sec8k_material_today` | 8-K filings filtered by material item codes | Earnings, M&A, officer changes |
| `macro_tape` | SPX/NDX/VIX/UST/DXY/GOLD/WTI/BTC/ETH snapshot | Regime gate for trade ideas |
| `etf_flow_today` | US spot BTC + ETH ETF aggregates | Institutional positioning |
| `active_airdrop_farms` | DefiLlama yield-gap airdrops | Farms where you're paid to wait |
| `polymarket_whale_positions` | Top wallets + active positions | Prediction-market copy-trade |
| `confluence_today` | Cross-source signal alignment | Stacks 2+ signals on same asset |
| `onchain_smart_wallets` | Live Solana copy-trade bot scores | Production wallet rankings |

All tools have full JSON schemas exposed at [/.well-known/mcp/server-card.json](https://falsifylab.com/.well-known/mcp/server-card.json).

## Client setup

### Claude Code

```bash
claude mcp add falsifylab-alpha -- python -m falsifylab_alpha_mcp
```

For Pro tier:

```bash
claude mcp add falsifylab-alpha \
  --env FL_API_KEY=fl_your_key \
  -- python -m falsifylab_alpha_mcp
```

### Cursor

Drop into `~/.cursor/mcp.json` or workspace root `.mcp.json`:

```json
{
  "mcpServers": {
    "falsifylab-alpha": {
      "command": "python",
      "args": ["-m", "falsifylab_alpha_mcp"],
      "env": {
        "FL_API_KEY": "fl_your_key_or_omit_for_free_tier"
      }
    }
  }
}
```

Restart Cursor. Tools auto-discovered.

### Cline

Settings → MCP Servers → Add Server. Paste the same JSON as Cursor above.

### Windsurf

Settings → MCP. Same JSON config. Auto-indexed from Smithery within 48h.

### Smithery

Connect via Smithery's hosted gateway — no local Python install needed. See [smithery.ai/servers/falsifylab/falsifylab-alpha-mcp](https://smithery.ai/servers/falsifylab/falsifylab-alpha-mcp).

## Verify install

In your agent, ask:

> Use macro_tape. Show me SPX, VIX, BTC, ETH with 1d and 5d returns.

If the agent returns numbers, you're live.

## Working agent prompts

Copy-paste these. They work on first run.

**Daily macro brief:**
```
Use macro_tape. Tell me the macro regime in 3 sentences. Cite specific
numbers — last price, 1d return, 5d return. Then list 2 tickers from
sec8k_material_today that might benefit from this regime.
```

**Insider + 8-K stacker:**
```
Run insider_buy_clusters (min_insiders=3) and sec8k_material_today
(items=["2.02","8.01","5.02"]). Find tickers in both within 24h. For
each match, summarize what insiders bought and what the 8-K said. End
with the bear case in one sentence.
```

**Confluence scan with bear case:**
```
Use confluence_today with min_signals=2. For each asset/ticker, explain
why these signals stacking is meaningful in 2 sentences. Skip noise
(DeFi LP pools with stablecoins). Highlight the most contrarian stack.
```

8 more recipes at [falsifylab.com/cookbook](https://falsifylab.com/cookbook).

## Pricing

| Tier | Price | What |
|------|-------|------|
| Free | $0 | 24h cached, 10 results/query, no signup, 60 req/hr |
| Pro | $19/mo | Real-time (5min), 100 results/query, 90d history, no rate limit |
| Pro Plus | $49/mo | 1-min refresh, email + Slack alerts, 365d on equity feeds, webhooks |
| Teams | $199/mo | 5 seats, 50k req/day, priority support |

Launch promo `EARLY50`: 50% off first 3 months, capped 25 redemptions. Get a key at [falsifylab.com/pro](https://falsifylab.com/pro).

## Live demo

Public agent calling these tools every 15 minutes: [falsifylab.com/demo](https://falsifylab.com/demo). Same MCP server you'd install. Real numbers, no curation.

## Why this exists

Built it because the author hand-scraped SEC EDGAR and DefiLlama at 6am every morning to feed a fleet of trading bots. The bots that survived ate from this exact pipeline. Wrapped it as an MCP server so any agent can pull the same data.

The bot fleet receipts (alive + dead, P&L, drawdown) are public at [falsifylab.com/vaults](https://falsifylab.com/vaults).

## Transparency

- **What we do**: aggregate + lightly enrich public market data, expose via MCP
- **What we don't**: trade execution, brokerage, advisory, signal selling
- **Data sources**: SEC EDGAR (Form 4, 8-K), SoSoValue (ETF flows), DefiLlama (yield), Hyperliquid public API, Polymarket public API, Yahoo Finance (macro)
- **Privacy**: free-tier key issued by hash(IP+UA), not stored long-term. Request bodies never logged.

## Architecture

```
your AI agent
    ↓ (MCP stdio)
falsifylab_alpha_mcp (Python stdlib, no deps)
    ↓ (HTTPS)
falsifylab.com/api/* (Cloudflare Workers)
    ↓ (cached 60s-1hr)
R2 (data feeds refreshed every 15min via cron)
    ↓ (every 15min)
Backend cron scripts (Form 4, 8-K, ETF, yield, polymarket, onchain, etc.)
```

Free tier hits cached data with 24h age. Pro tier hits the same endpoints with auth header, bypasses cache to fresh upstream.

## Links

- **Live demo**: [falsifylab.com/demo](https://falsifylab.com/demo)
- **Install guide**: [falsifylab.com/install](https://falsifylab.com/install)
- **Cookbook**: [falsifylab.com/cookbook](https://falsifylab.com/cookbook)
- **Pricing**: [falsifylab.com/pro](https://falsifylab.com/pro)
- **Comparison** (vs Token Terminal / Nansen / Dune): [falsifylab.com/vs](https://falsifylab.com/vs)
- **MCP server card**: [/.well-known/mcp/server-card.json](https://falsifylab.com/.well-known/mcp/server-card.json)
- **Substack**: [falsifylab.substack.com](https://falsifylab.substack.com)
- **PyPI**: [pypi.org/project/falsifylab-alpha-mcp](https://pypi.org/project/falsifylab-alpha-mcp/)
- **Smithery**: [smithery.ai/servers/falsifylab/falsifylab-alpha-mcp](https://smithery.ai/servers/falsifylab/falsifylab-alpha-mcp)
- **Agent starter repo**: [github.com/opsfalsifylab/falsifylab-agent-starter](https://github.com/opsfalsifylab/falsifylab-agent-starter)

## Support

- **Issues**: [GitHub issues](https://github.com/FalsifyLab/falsifylab-alpha-mcp/issues)
- **Email**: ops@falsifylab.com
- **Security**: report to ops@falsifylab.com with subject `[security]`. 48h response. Responsible disclosure credited in CHANGELOG.

## Contributing

PRs welcome for:
- New tool ideas (open issue first to discuss scope)
- Documentation improvements
- Bug fixes

Do not submit PRs for trading-signal generators or copy-trading helpers — out of scope for this server (we are research data infrastructure, not advisory).

## License

MIT. See [LICENSE](LICENSE).

---

*FalsifyLab Alpha v0.1.5 · Built for AI coding agents · Free tier no signup · falsifylab.com*
