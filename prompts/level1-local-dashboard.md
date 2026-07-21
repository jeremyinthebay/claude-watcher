# level1 local dashboard

Paste this into a Claude (Cowork / Claude Code) session:

```
Build me a local "Claude Watcher" — a dashboard that shows whether my Claude
sessions are actually working, with NO web server. It's a single HTML file I
bookmark, regenerated every minute by launchd. Everything stays local.

HOW SESSIONS LEAVE TRACKS (verify these paths on my machine before coding):
- Cowork sessions live under ~/Library/Application Support/Claude/
  local-agent-mode-sessions/*/*/ — each session is a directory local_<uuid>/
  with a sibling metadata file local_<uuid>.json containing sessionId, title,
  model, isArchived, lastActivityAt.
- A WORKING session constantly writes files inside its directory; a stalled
  one doesn't. Freshest file mtime = last real activity. Skip node_modules/
  and outputs/ subdirs when scanning, and cap the walk (~8k files) for speed.
- Active subagents show up as recently-modified .jsonl files under the
  session's .claude/projects/*/*/subagents/ — count ones touched <3 min ago.
- Claude Code sessions (if I use the CLI) leave transcripts at
  ~/.claude/projects/<project-dir>/<uuid>.jsonl — same mtime trick.

BUILD (three pieces):
1. ~/claude-watcher/watch-status.py — scans the paths above; for every
   non-archived session with activity in the last 48h, compute age of newest
   file and state: working (<150s) / quiet (<30min) / idle. Then write
   ~/claude-watcher/index.html as a COMPLETE self-contained page with the
   data inlined (no fetch — file:// pages can't fetch) and
   <meta http-equiv="refresh" content="30"> so it reloads itself. Dark theme,
   one card per session: green/amber/gray dot, title, model, "Xs ago", the
   session id in small mono, and an "N subagents" badge when active. Footer
   shows generated-at time — if that goes stale, the generator itself died,
   which is also worth knowing. Atomic write (tmp file + os.replace) so the
   browser never catches a half-written page.
2. Also scan my GuideFlow repo and add a card: newest commit (hash, age,
   subject — local git only, no network fetch) and mtimes of ROADMAP.md /
   PROGRESS.md / HANDOFF.md, so I can see the last time a session actually
   saved state.
3. ~/Library/LaunchAgents/com.guideflow.watch-status.plist — runs the script
   every 60s (StartInterval 60, RunAtLoad true), stderr to a log file in
   ~/claude-watcher/. Load it with launchctl load.

VERIFY (don't tell me it works — show me):
- Run the script once, print the sessions it found with their states, and
  confirm THIS session shows as "working" (it must — you're writing files
  right now).
- Open file:///Users/<me>/claude-watcher/index.html via `open`, and paste the
  launchctl list line proving the job is loaded.
- Wait ~90 seconds and confirm the generated-at stamp advanced on its own.

RULES: nothing public, no server, no network calls, no tokens spent at
runtime — the watcher is a shell script's view of the disk, not an AI. Don't
make sessions self-report status anywhere: a hung session can't report, and
that's precisely the moment the watcher exists for.
```
