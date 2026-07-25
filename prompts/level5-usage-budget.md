# level5 usage & budget

An upgrade for a watcher that already exists (Levels 1–4 + your own custom work),
not a rebuild. Adds token-burn cards, a model-mix bar, and real rate-limit gauges
fed by a self-healing OAuth probe. Paste this into a Claude (Cowork / Claude Code)
session on the Mac that runs the watcher:

```
Upgrade my existing Claude Watcher with a "Usage & Budget" panel. READ THIS FIRST:
I already built Levels 1-4 and have my own custom work on top. Do NOT rebuild the
watcher. Open my current ~/claude-watcher/watch-status.py, my status.json, and my
dashboard HTML, learn their shapes, then ADD the budget layer on top — preserving
every card, chip, filter and customization I already have. Still 100% local; the
token/cost half spends zero tokens at runtime.

WHAT IT ADDS
- Four hero cards up top: TODAY / THIS WEEK / THIS MONTH / ALL TIME token totals,
  each with cost and a period-over-period delta (today vs yesterday, week vs last
  week, month vs last month).
- A 14-day trend bar chart and a model-mix bar (how much Sonnet vs Opus vs Haiku).
- Three rate-limit gauges — Session %, Weekly %, Extra-usage $ — the REAL account
  meters, so you see how close you are to a limit, not just token volume.

DATA SOURCE 1 — ccusage (zero auth, nothing to expire)
Token/cost history comes from ccusage (npm i -g ccusage), which parses Claude's
local JSONL logs offline — no API token, so this half can never "expire." In
watch-status.py add a cached helper (cache ~10 min so your 60s generator doesn't
re-parse every tick) that runs:  ccusage daily --since 20250101 --json  and from the
daily rows computes today/yesterday, this-week/last-week (ISO week), this-month/
last-month, all-time, a 14-day sparkline, and a 30-day model mix. Put it all in
status.json under a "budget" key, wrapped in try/except so a ccusage hiccup never
blanks the rest of the feed.

TRAP — ccusage only sees the CLI by default, so DESKTOP usage reads as ZERO.
Out of the box ccusage scans ~/.claude/projects — Claude Code CLI only. Cowork/
desktop sessions keep their OWN nested .claude inside each session dir, so on a day
you only used the desktop app the "today" card shows 0 while the weekly gauge climbs.
Fix: build a comma-separated CLAUDE_CONFIG_DIR from ~/.claude PLUS every desktop
session's nested .claude — glob
~/Library/Application Support/Claude/local-agent-mode-sessions/*/*/local_*/.claude —
and pass it as an env var to ccusage. It dedupes by message id, so overlaps are safe.
Sort those dirs by mtime and cap the list (~2000) so the env string can't grow
without bound as sessions pile up.

TRAP — `ccusage daily` is trustworthy; `ccusage session` is not.
If you drill from "today cost $X" into "which session did it", note that
`session --since` selects which sessions APPEAR by activity date and then reports each
one's FULL LIFETIME cost. It overstated one day for me by 2.52x. Level 6 covers the
fix; for now, build the budget cards on `daily` only.

DATA SOURCE 2 — the real %-meters (a SELF-HEALING OAuth probe)
The Session/Weekly/Extra gauges come from the same endpoint the CLI's /usage screen
uses: GET https://api.anthropic.com/api/oauth/usage with your Claude Code OAuth token
(header  anthropic-beta: oauth-2025-04-20 ). Write a small usage-probe.sh (zsh
wrapping python) that:
- reads the token from the login keychain:
  security find-generic-password -s "Claude Code-credentials" -a <your-mac-username> -w
  (detect the account from the item's own attributes — it's your macOS user);
- if the access token is expired, REFRESHES it with the stored refresh token and
  writes the new credential back into the keychain IN PLACE. This is what makes it
  self-healing — a read-only probe dies the moment the token expires and stays dead
  until you run `claude login`; this one never does;
- writes ~/claude-watcher/meters.json: session_pct, session_resets, weekly_pct,
  weekly_resets, any model-scoped weekly %, extra-usage $used/$cap, and a one-line
  summary. Your generator reads meters.json into status.json's budget.meters.

TRAPS on the probe (each cost a debugging round):
- The token endpoint MOVED. console.anthropic.com/v1/oauth/token now 404s. The live
  one is  https://platform.claude.com/v1/oauth/token  — I found it (plus client_id
  9d1c250a-e61b-44d9-88ed-5944d1962f5e, the public Claude Code OAuth client) in the
  strings of the Claude Code binary. POST {grant_type:"refresh_token", refresh_token,
  client_id}.
- Cloudflare 1010-blocks a bare User-Agent. Python urllib's default UA gets an HTTP
  403 "error code: 1010" before it reaches the origin — set ANY real User-Agent
  header and it goes through.
- NEVER print or log the token. Refresh safely: a FAILED refresh request does not
  consume the refresh token, so attempts are harmless; before writing, back up the
  current credential to a file and validate the new JSON, then update the SAME
  keychain service+account in place (security add-generic-password -U) so you never
  create a duplicate item, and read it back to confirm before trusting it.
- Guard freshness checks: "value or DEFAULT" is a bug when the value can be 0 —
  meters written this same second have age 0, and `age or BIG` treats 0 as missing.
  Use explicit None checks.

KEEP IT FRESH (this is what stops "it worked, then broke overnight")
Add a launchd job — com.guideflow.usage-probe, StartInterval 1200 (every 20 min),
RunAtLoad — that runs usage-probe.sh. Access tokens last ~8h; polling every 20 min
keeps the token warm and meters.json current, so a token never silently expires
between runs again. VERIFY IT FROM THE LAUNCHD CONTEXT specifically — that's where
keychain access is the thing in doubt: delete meters.json, let the job tick, and
confirm it's rewritten with an empty error log.

THE DASHBOARD (layer on, don't replace)
Add a budget section ABOVE your existing session cards, in your current dark theme,
reusing your CSS variables:
- Four hero cards. Format tokens like "265.0M" (÷1e6, one decimal; "k" under a
  million). Delta line: a colored triangle + "+113.5% vs 124.1M". SPEND SEMANTICS —
  an increase is red/attention (▲), a decrease is green/good (▼), a null delta is a
  muted dash; ALL TIME shows "all time" instead of a delta. Small cost chip ($) per
  card.
- 14-day trend bars with today highlighted; a stacked model-mix bar + legend (Sonnet
  in your gold/green, Opus in a warmer red so an Opus-heavy day reads hotter, cost
  per model on hover); three gauges (Session / Weekly / Extra) colored amber at
  >=60% and red at >=80%, each with its reset label.
- ADDITIVELY: keep your session list, filters, sparklines, role chips and any custom
  cards exactly as they are. WRAP your existing render() instead of rewriting it, and
  don't rename any element ids your current code reads. Feed your SwiftBar menu bar
  the weekly % too (and a ⚠ when a limit is close) so it's glanceable without opening
  the page.

ONE HONEST NOTE on the model mix once desktop is included: the bar will probably go
Opus-heavy, because the desktop app defaults to Opus while a well-run CLI/relay
executor runs Sonnet. That's the true total picture. If you also want the "is my
automation staying on Sonnet?" signal, keep THAT as a separate CLI-only readout —
it's your executor's own logs, not this blended view.

VERIFY (show me, don't tell me):
- Run the generator; paste status.json's budget block — four cards with nonzero
  tokens (run something in the desktop app first so "today" isn't a real zero), a
  meters object with session/weekly %, and a model_mix array.
- Prove the desktop-inclusion fix: show "today" is 0 with plain ccusage, then nonzero
  once CLAUDE_CONFIG_DIR includes the session dirs.
- Run usage-probe.sh once and paste the summary line (session=..% weekly=..%); confirm
  a second run takes the fast path (no re-refresh) and the keychain still has exactly
  ONE credential item.
- Delete meters.json, let the launchd probe tick, confirm it reappears — that proves
  it works from launchd, not just your shell.
- Screenshot the dashboard at 1440px and at 390px; confirm the hero cards wrap 2x2 on
  phone and your existing panels below are untouched.

RULES unchanged: local only, no server, the burn cards spend zero tokens at runtime,
and never publish meters.json or status.json anywhere public without deciding on
purpose — meters.json reflects your account's real usage and limits.
```

**Prerequisite:** Levels 1–3 (the generator, `status.json`, and the dashboard) must
exist. Like Level 4, this is a standalone upgrade — it is intentionally *not* part of
`master-build-all.md`, because it layers onto a watcher you already run.
