# Contributing to falsifylab-alpha-mcp

Thanks for stopping by. Quick rules so contributions land smoothly.

## What we accept

- Bug reports with reproduction steps
- Documentation fixes (typos, clarity, missing detail)
- New MCP tool implementations that target public market data (must be free or pay-per-call, no scraping behind login walls)
- Test coverage improvements
- Performance fixes

## What we do not accept

- Trading-signal generators or copy-trading helpers (out of scope, FL is research data infrastructure, not advisory)
- Tools requiring proprietary or paywalled data sources
- Tools that mutate state on third-party services (we are read-only)
- AI-generated PRs without disclosure (we accept AI-assisted, just be honest about it)

## Workflow

1. Open an issue first describing what you want to change (avoid wasted work)
2. Fork the repo, branch from `main`
3. Implement, add tests, run `python -m py_compile falsifylab_alpha_mcp.py`
4. Open PR against `main` with: what changed, why, smoke-test output
5. Maintainer reviews within 48h on weekdays

## Voice + style

- Lowercase prose in user-facing docs (matches FL brand voice)
- No em-dashes (we lint for this)
- Test names: snake_case, descriptive
- Imports sorted, stdlib first, then 3rd-party, then local

## Reporting security issues

See SECURITY.md for the responsible disclosure path. Do NOT open public issues for security bugs.

## Bug reports

Use the bug_report template. Include:
- Package version (`pip show falsifylab-alpha-mcp | grep Version`)
- Python version
- Exact command + arguments
- Full traceback
- Operating system + MCP client

## License

By contributing, you agree your contributions are licensed under MIT (see LICENSE).
