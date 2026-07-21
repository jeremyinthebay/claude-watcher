# level2 menubar and doing

Paste this into a Claude (Cowork / Claude Code) session:

```
Extend my local Claude Watcher (built from the prompt above — build that
first if it doesn't exist) with two upgrades: a macOS MENU BAR app via
SwiftBar, and a live "what is it actually doing" line per session. Still
100% local: no server, no network calls, no tokens spent at runtime.

UPGRADE 1 — the "doing" line (what is each session working on?)

Extend ~/claude-watcher/watch-status.py so that, in addition to the HTML
dashboard, it atomically writes ~/claude-watcher/status.json:
  { "generated_at": <unix>, "sessions": [ { "title", "model", "age_s",
    "state", "subagents", "doing" } ] }

"doing" is a one-line best-effort of the session's latest action, extracted
from its transcript — sessions log every step as JSONL:
- Cowork: the session dir's newest .claude/projects/*/*.jsonl (files directly
  in that dir — do NOT match the subagents/ subdirs).
- Claude Code CLI: ~/.claude/projects/<project>/<uuid>.jsonl, same format.
Read only the LAST ~400 KB of the file. Parse each line as JSON, keep only
type == "assistant" entries, and walk message.content blocks IN ORDER so the
final value is the most recent event:
- a "tool_use" block  -> 'ToolName: <hint>' where hint is the first line of
  input.command / .file_path / .path / .description / .subject / .pattern /
  .url (first that exists);
- a "text" block      -> the text itself.
Then collapse all whitespace, strip * ` | # characters, cap at 160 chars.
Compute it only for working/quiet sessions (skip idle — saves IO).
Show the line on the HTML dashboard too, small and muted, under each active
session's card.

UPGRADE 2 — the menu bar app (SwiftBar)

1. brew install --cask swiftbar   (install Homebrew first if missing).
2. Write ~/claude-watcher/swiftbar/claude-watcher.60s.sh — the ".60s" suffix
   IS the refresh cadence, SwiftBar parses it from the filename. The script
   cats the LOCAL ~/claude-watcher/status.json into python3 for formatting
   (no curl — everything is on this machine).
   Menu bar glyph: "(green)N" when N sessions are working, "(yellow)" when
   only quiet ones, "(white)" all idle, "(red) Claude?" if generated_at is
   older than 5 minutes (the generator died — that is its own alert).
   Dropdown: one line per session — state dot, title, age, model, subagent
   count — with its "doing" line as an indented "--" submenu row (size=11),
   then "Open dashboard | href=file:///Users/<me>/claude-watcher/index.html".
3. defaults write com.ameba.SwiftBar PluginDirectory "$HOME/claude-watcher/swiftbar"
   then: open -a SwiftBar

THREE TRAPS (each one cost a real debugging round — do not rediscover them):
- The python code rides inside a single-quoted bash string. Use ONLY double
  quotes in the python source, including dict keys. One stray s['key']
  terminates the shell string and you get a NameError that looks impossible.
- macOS system python3 is too old for same-quote nesting inside f-strings.
  Never index a dict inside an f-string — assign to a plain variable first,
  then interpolate the variable.
- "|" is SwiftBar's parameter separator. Strip or replace it in every piece
  of dynamic text (titles, doing lines, log lines) before printing.

VERIFY (show me, don't tell me):
- Run watch-status.py once; paste the sessions with their "doing" values and
  confirm THIS session appears as working — its doing line should show the
  very command you just ran. If a watcher can't see the session that is
  building it, it can't see anything.
- Run the plugin script directly in the terminal; paste its full output.
- Confirm the icon is in the menu bar, then wait ~90s and confirm the
  dropdown's data advanced without you touching anything.

PRIVACY RULE: "doing" lines contain shell commands and file paths. That is
fine in a local file — but never publish status.json anywhere public without
deciding, on purpose, that you are okay with that.
```
