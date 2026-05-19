# Contributing

Thanks for your interest! A few things to know before sending a PR.

## Project shape

This is a single-file Python plugin for xbar/SwiftBar. Everything lives in
`xbar_stock_ticker.py`. Why one file?

- xbar treats one Python file as one plugin. Splitting into modules would
  require either an installer (friction) or `sys.path` hacks (fragile).
- The codebase is ~2000 lines — large but navigable. Function/class headers
  use `─── Section ───` banners for fast scanning.

So: **all code stays in `xbar_stock_ticker.py`**.

## Running locally

```bash
# Sanity check
python3 -m py_compile xbar_stock_ticker.py

# Live trial — simulates one xbar invocation. The output is what xbar reads.
python3 xbar_stock_ticker.py | head -50
```

## Style

- 4-space indent
- Type hints on public functions
- Docstrings that explain WHY, not just WHAT (the function name says what)
- Comments at branch points where the choice would surprise a reader
- Never `except Exception: pass` — always log and pick a specific exception

Existing code mostly follows this. PRs that significantly drift from the
style will get gentle redirection.

## What to send

**Welcome:**
- New treasury sources (the cascade in `_TREASURY_SOURCES` is easy to extend)
- New quote providers (e.g. IEX Cloud, Polygon) as alternates to Alpaca/Yahoo
- Performance work (the script is hot — every cycle counts at 8s refresh)
- Bug fixes with a clear "before / after" log excerpt or screenshot
- Improvements to the validator (`validate_config`) — better diagnostics save users hours

**Discuss first (open an issue):**
- Major UX changes (menu bar layout, dropdown order)
- New persisted state files (we already have several; consolidating > adding)
- Removing config fields — users have ~20 settings, breaking changes hurt

**No:**
- Trading execution / order placement. This is a viewer, intentionally.
- External Python dependencies — stdlib only.

## Security

- **Never commit `.xbar_stock_config.json` or any file matching the patterns
  in `.gitignore`.** It contains API keys and personal P&L data.
- If a PR includes a real API key by accident, that key is presumed
  compromised; the PR will be closed and the contributor asked to rotate
  the key before resubmitting.
- The plugin auto-chmod's the config to 600 on every load — but if you
  back it up elsewhere, mind the permissions.

## Testing

There's no formal test suite (single-file constraint). For changes touching
the alert engine, fetcher dispatcher, or cache layer, please write a small
inline test script and paste its output in your PR description. Pattern:

```python
import xbar_stock_ticker as m
from unittest.mock import patch
# ... exercise the function you changed
```

The conversation history (commit log) has dozens of these — copy the style.

## License

By submitting a PR you agree your contribution is licensed under MIT.

## Like the project?

If contributing code isn't your thing, a coffee works too:
<https://buymeacoffee.com/nathanieljiang>
