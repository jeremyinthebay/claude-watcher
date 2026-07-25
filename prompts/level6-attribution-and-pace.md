# level6 attribution & pace

Level 5 tells you *how much* you spent. This tells you **which conversation spent it**,
and warns you while a week is still going wrong instead of after. Another upgrade to a
watcher that already exists — paste into a Claude session on the Mac that runs it:

```
Upgrade my Claude Watcher with per-conversation ATTRIBUTION and PACE alerting. READ
THIS FIRST: I already run Levels 1-5 with my own custom work on top. Do NOT rebuild
anything. Read my watch-status.py, status.json, dashboard HTML and usage-probe.sh
first, learn their shapes, then layer on. Still 100% local, still zero tokens at
runtime.

WHY THIS EXISTS — the alert that proved Level 5 wasn't enough
My watchdog fired exactly once in a hot week: "weekly=82%", over the 80% line. The
week reset six hours later. So the one alert I got warned me about a budget that was
about to be forgiven, and said nothing during the three days it was actually being
spent. An absolute threshold is a tombstone. And when it did fire, the only lever it
could offer was "use it less", because nothing could name WHAT had burned it.

PART A — ATTRIBUTION: put a human name on the spend
Cowork already writes full Claude-Code-format transcripts, one `usage` block per
assistant message, under:
  ~/Library/Application Support/Claude/local-agent-mode-sessions/
      <ws>/<acct>/local_<sessionId>/.claude/projects/**/*.jsonl
And the conversation's human TITLE sits in a sidecar next to it:
  <ws>/<acct>/local_<sessionId>.json  ->  {"title": "WiFi Odds takeover", "model": ...}
Join those two and your report goes from a UUID to "WiFi Odds takeover". That join is
the whole feature. Write usage-attribute.py that walks the transcripts, aggregates
tokens per (session, model, LOCAL date), prices them, and prints a ranked table plus
--json for the alerting path.

TRAP A1 — `ccusage session --since` does NOT filter what it reports.
It selects which sessions APPEAR (by activity date) and then prints each one's FULL
LIFETIME cost. I built on it and was wrong by 2.52x: all 16 of that day's sessions
returned byte-identical costs for --since <today> and --since <January>, and the
session total ($1,037) overstated the day total ($411). Verify this on your own data
before trusting any per-session number: run `session --since` twice with far-apart
dates and diff. If the rows are identical, aggregate per-day yourself from the
transcripts. `ccusage daily` is fine — it's `session` that misleads.

TRAP A2 — the transcripts are DUPLICATED, about 2.2x.
Cowork copies them into nested session dirs, so a naive sum inflates badly and the
factor is not stable day to day, so you cannot divide it out. Dedup on the assistant
message id (I checked whether requestId was also needed: id alone and (id,requestId)
gave the identical unique count). 7,044 raw rows collapsed to 3,187 real ones.

TRAP A3 — rank by COST, not tokens. Cache reads were 97% of my tokens and are the
cheapest tier by an order of magnitude, so a token ranking ranks by context size, not
spend.

TRAP A4 — if you price tokens yourself, the cache-WRITE multiplier is 2x, not 1.25x.
Anthropic bills two cache-write tiers, 5-minute at 1.25x and 1-hour at 2x, and the
desktop app leans on the 1h tier. Assuming a flat 1.25x read ~5.6% low on EVERY single
day — a bias you cannot see without a per-day check against a second source. Better:
don't hardcode a price table at all, it goes stale silently. Calibrate from ccusage's
own per-model daily breakdowns and FIT the cache-write coefficient:
  cost ~= r*(input + 5*output + 0.1*cache_read) + s*cache_creation
Two unknowns, ~14 day-rows per model, solved by 2x2 normal equations — no numpy. Mine
fitted to clean list prices with s/r = 2.00 on every well-sampled model, which is what
confirmed the 1h-tier explanation. Then validate: re-price every day from YOUR
transcripts and compare to ccusage's daily totals. Calibrate on ccusage's token counts
and validate on your own, or the check is circular and passes no matter what.

TRAP A5 — scan BOTH roots or your validation is apples to oranges. ccusage's totals
cover ~/.claude AND the desktop session dirs. I scanned only the desktop ones and read
11% low, with the gap tracking exactly when my CLI relay was busy. They are disjoint,
so they add.

PART B — PACE: alert on the trajectory, not the tombstone
Add usage-pace.py that re-reads the probe (zero budget, meters only) and answers the
one question a threshold can't: AT THE CURRENT RATE, DO I CROSS 100% BEFORE THIS
WINDOW RESETS? That's self-normalizing — loud in a hot week, quiet in a cool one, with
no percentage to retune. Alert when the projected crossing lands inside the window.

Use two rate models, because they fail in opposite directions:
- average = used/elapsed. Stable, but blind to a late-week burst: five idle days
  dilute Friday's spike below the line.
- recent = delta between your last two logged readings. Catches bursts, noisy over
  short spans.
Project with whichever is WORSE and report which one drove it, so the alert names the
shape of the problem.

Three guards, all of which I needed:
- TRUST GATE: believe no projection until >=4% of the window has elapsed. At hour 1 of
  168 a single session reads as 40x pace.
- HYSTERESIS: after alerting once for a window, stay silent unless the projected
  crossing moves >=12h EARLIER. A twice-daily job must not nag about a known state.
- NOISE GATE: ignore a recent-rate sample under ~2h. The meters are integer percent, so
  two readings 20 minutes apart turn a 16.5->17 rounding tick into a fake 3%/h burn.
Key your state file on the window's reset timestamp so a new week starts clean.

Phone-readable output beats precision: "weekly 17%, 3.0x pace, hits 100% Mon ~1pm,
week resets Sat" then the top 3 conversations. Never send a bare percentage with no
reset date — that's what made my 82% alert useless.

WIRE IT UP
Run attribution ONLY when something already fired (a pace alert or a threshold). On a
quiet run it's wasted work, and silence should stay the default. Add a top-burners
panel to the dashboard from the same --json, and put the projected crossing next to
the weekly gauge.

VERIFY (show me, don't tell me):
- Paste the ranked table for today. The conversation you KNOW was short must be near
  the bottom — that's your dedup check. If a 10-minute session ranks top, it's wrong.
- Prove trap A1 on your own data: `session --since` for two far-apart dates, diffed.
- Run the per-day validation and paste the table: your priced days vs ccusage's, with
  the worst material-day deviation. State your residual honestly rather than tuning
  until it's zero; mine reads ~5% low and I don't fully know why, which I'd rather
  write down than hide.
- Unit-test pace with SYNTHETIC meters, not live ones: an early-window spike (must stay
  quiet), a steady cool week (quiet), a late-week burst (must alert via recent-rate),
  two readings 20min apart (must not alert on rounding), and a meter that goes
  backwards after a reset (must not produce a negative rate).
- Confirm --dry-run leaves the state file untouched, and that a real run writes it.

RULES unchanged: local only, zero tokens at runtime, never print or log the OAuth
token, and never publish the attribution output — conversation titles are as sensitive
as the numbers.
```

**Prerequisite:** Level 5 (the probe, `meters.json`, and the budget panel). Like Levels 4
and 5 this is a standalone upgrade, deliberately not part of `master-build-all.md`.

**One caveat worth passing on:** transcripts only exist for Cowork and Claude Code. Claude
in Chrome, mobile and web chat write nothing locally, so if your meter climbs while both
ccusage and the parser read flat, that's the blind spot — say so in the report rather than
blaming the largest session you *can* see.
