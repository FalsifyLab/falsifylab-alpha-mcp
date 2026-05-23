# Security policy

## Reporting a vulnerability

If you find a security issue in falsifylab-alpha-mcp or the hosted MCP transport at mcp.falsifylab.com, report it privately:

**email**: security@falsifylab.com

Please do NOT open a public GitHub issue. We acknowledge within 48 hours.

## What we treat as security-relevant

- API key leakage paths
- Auth bypass on Pro / Pro Plus / Teams tiers
- Rate-limit bypass that could exhaust our quota or expose other users' usage
- Unsafe deserialization in the MCP tool response paths
- Path traversal or remote code execution in any CLI or server entry point
- PII exposure from any logging or telemetry

## What is not in scope

- Bugs in upstream data sources (SEC EDGAR, DefiLlama, Hyperliquid public API, Polymarket public API, Yahoo Finance)
- Issues in third-party MCP clients (Cursor, Cline, Windsurf, etc.)
- Cloudflare Worker DDoS at the infrastructure layer (CF handles)
- Bugs in the `falsifylab.com` web property unrelated to the MCP product

## Coordinated disclosure window

90 days from initial report. We aim to ship a fix in under 14 days for high-severity issues.

## What you get

- Public credit in the changelog (with permission)
- Free Pro Plus key for 12 months
- Early access to internal beta releases (if you want)
- A clean handoff (no NDAs, no legal threats)

## Encryption

If sensitive, encrypt with our PGP key at https://falsifylab.com/security.asc

```
Algorithm:   Ed25519 (primary) + cv25519 (encryption subkey)
Generated:   2026-05-23
Expires:     2028-05-22
Fingerprint: 232B 6912 383F 3C0D F516  BE9A 89DD 9D18 1624 71FD
User ID:     FalsifyLab Security <security@falsifylab.com>
```

Import:
```bash
curl https://falsifylab.com/security.asc | gpg --import
```

## Past disclosures

None yet (project launched 2026-05-13).
