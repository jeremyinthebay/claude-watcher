# level3 mission control

Paste this into a Claude (Cowork / Claude Code) session:

```
Upgrade my local Claude Watcher (Levels 1 + 2 above are prerequisites) into
the "mission control" version. Still 100% local, still zero tokens at
runtime, still observing from outside — nothing below asks a session to
report on itself.

UPGRADE 1 — make the layout survive real data (this is what fixes "messy")

Rebuild the dashboard HTML with these specific patterns:
- A summary strip of chips at the top: N working / N quiet / N idle, plus a
  red "feed stale" chip if generated_at is older than 5 minutes.
- One card per session: status dot, title, model chip, active-subagent count
  badge, and right-aligned meta: last activity + "up 4h" (from the metadata
  createdAt) + the session id in small mono.
- EVERY dynamic line renders as ONE line with CSS ellipsis
  (white-space:nowrap; overflow:hidden; text-overflow:ellipsis) and the full
  text in a title= attribute for hover. Wrapping raw prompts is what made
  the old layout unreadable.
- Finished subagents collapse into a <details> ("N finished in the last
  30 min") instead of stacking under the live ones.
- Prettify tool names for display: strip the "mcp__" prefix, render "__" as
  " · ". Tool calls get a wrench icon, prose gets a speech icon.

UPGRADE 2 — role chips per subagent

Subagent prompts start like "You are a Sonnet BUILDER on ..." — extract that
role into a small amber chip instead of showing the raw prompt:
  match: ^(?:you are|you're) (?:an\s+|a\s+|the\s+)?(ROLE)(?: agent)? followed
  by " on|for|in" or punctuation, case-insensitive, capped ~34 chars.
TRAP: order the article alternatives an|a|the and require trailing \s+ —
with plain (a|an|the)? the "a" alternative wins and "an Opus SPEC" extracts
as "n Opus SPEC".

UPGRADE 3 — per-subagent runtime and token spend

For each subagent transcript (cap the read at 8 MB — they're short-lived):
- start time = the first line's "timestamp" field; runtime = now − start.
- token spend = sum of message.usage.output_tokens over every
  type=="assistant" line. Show it in the row ("51.5k tok") and in the menu
  bar submenu. This is the "which agent is expensive" signal.

UPGRADE 4 — activity sparkline per session

From the last ~2 MB of the session's main transcript, bucket every line's
"timestamp" into 12 buckets of 5 minutes (the last hour) and render tiny
bars under the card — steady grind and burst-then-stall look completely
different, and you learn to read it instantly.
TRAP: don't slice the timestamp at a fixed width — fractional seconds make
fromisoformat fail SILENTLY and you get an all-zero sparkline that looks
plausible. Find the closing quote instead. (Cost a debugging round.)

UPGRADE 5 — Claude Code CLI runs on the same board

Also scan ~/.claude/projects/*/*.jsonl (exclude paths containing
"subagents"). Each file is one CLI run: project name from the directory
(split on "-Projects-"; fall back to a cleaned suffix, and if the result is
shorter than 3 chars call it "home"), state from mtime, "doing" via the same
last-action parser, model from the newest assistant line's message.model.
Give these cards a distinct "CLI" chip. If you use claude CLI at all — or
run any unattended loop with it — these are the sessions you most want
watched.

UPGRADE 6 — trust the app's own clock too

Session age = max(newest file mtime, metadata lastActivityAt). A capped
directory walk can miss the one hot file and report a working session as a
day old. Two independent signals, take the fresher.

VERIFY (show me, don't tell me):
- Run the generator; paste one session's JSON showing role, tok, runtime_s,
  and a spark array with at least one nonzero bucket.
- THIS session must appear working, with the very command you just ran as
  its doing line.
- Screenshot the dashboard in a real browser; confirm zero horizontal
  overflow at 390px width; confirm the finished-subagents toggle opens.
- Menu bar: paste the plugin's terminal output showing role chips and token
  counts on the submenu rows.

RULES unchanged: local only, no server, no network, no runtime tokens, and
never publish the output file anywhere public without deciding on purpose.
```
