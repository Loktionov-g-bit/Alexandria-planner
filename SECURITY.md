# Security policy

## Reporting a vulnerability

Please do not open a public issue. Report privately through
[GitHub Security Advisories](https://github.com/Loktionov-g-bit/alexandria-planner/security/advisories/new)
or a direct message on Telegram to [@marshall033](https://t.me/marshall033).

Include the version (`/api/health` shows it), what you did, and what happened.
You will get an answer within a few days; fixes for confirmed issues are released as soon as possible.

## Supported versions

Only the latest release receives security fixes.

## Scope notes

- Alexandria Planner is self-hosted: the operator is responsible for HTTPS (a reverse proxy) and for
  keeping the PostgreSQL password and the `.env` file private.
- Telegram bot tokens and WireGuard keys are stored only on the operator's server and are never sent back
  to the browser in full.
