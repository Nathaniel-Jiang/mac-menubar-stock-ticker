# Security Policy

## Reporting a vulnerability

If you've found a security issue — anything where reporting it publicly would
put users at risk — please **do not open a public issue.**

Instead, one of these:

1. **GitHub Security Advisories** (preferred):
   [Open a private advisory](../../security/advisories/new) directly on this repo
2. **Email**: Use GitHub's "Email this user" link on
   [@nathanieljiang's profile](https://github.com/nathanieljiang),
   subject line `[security] menubar-stock-ticker`

I'll respond within a few days. Once a fix is shipped, you'll be credited
in the release notes (unless you'd rather stay anonymous).

## What counts as a security issue

- API key disclosure (e.g. logs that print secrets)
- Path traversal / arbitrary file read in config or cache paths
- Command injection via xbar's `shell=` parameter
- Anything that could let a malicious config file execute arbitrary code

## What doesn't

- "Yahoo Finance can be rate-limited" — yes, by design, fallbacks exist
- "User-Agent strings can be detected" — yes, this is best-effort scraping
- "Config file is plain text" — `chmod 600` is the protection; if your
  attacker has filesystem access they have already won

## Hall of fame

Once we get a first report, it'll be linked here. Be the first!
