#!/bin/bash
# <swiftbar.title>Claude Watcher</swiftbar.title>
# <swiftbar.desc>Menu bar status for Claude sessions + the Night Shift relay on the mini.</swiftbar.desc>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
#
# Reads the public status.json (regenerated every 60s on the mini), so this same
# plugin file works on ANY Mac — just install SwiftBar and drop this in its
# plugin folder. Filename suffix ".60s" = SwiftBar refresh cadence.

# Local file (default) or remote URL — set CW_URL to watch another machine.
LOCAL="${CW_OUT:-$HOME/.claude-watcher}/status.json"
URL="${CW_URL:-}"

{ if [ -n "$URL" ]; then /usr/bin/curl -fsS --max-time 8 "$URL?cb=$RANDOM" 2>/dev/null; else /bin/cat "$LOCAL" 2>/dev/null; fi; } | /usr/bin/python3 -c '
import sys, json, time

import os
PAGE = os.environ.get("CW_URL", "file://" + os.path.expanduser("~/.claude-watcher/index.html"))
try:
    d = json.load(sys.stdin)
except Exception:
    print("⚫️ Claude")
    print("---")
    print("status.json unreachable | color=red")
    print("Open Claude Watcher | href=" + PAGE)
    raise SystemExit

def clean(t):
    return " ".join(str(t).replace("|", "/").split())

def ago(s):
    if s < 90: return f"{s}s"
    if s < 5400: return f"{s//60}m"
    return f"{s//3600}h"

now = time.time()
stale = now - d.get("generated_at", 0) > 300
ss = d.get("sessions", [])
working = [s for s in ss if s["state"] == "working"]
quiet = [s for s in ss if s["state"] == "quiet"]
r = d.get("relay", {})
paused = r.get("paused_stop") or r.get("halt")

# ---- menu bar glyph ----
if stale:
    title = "\U0001f534 Claude?"
elif working:
    title = f"\U0001f7e2 {len(working)}"
else:
    title = "\U0001f7e1" if quiet else "⚪️"
if paused and not stale:
    title += " ⏸"
print(title)
print("---")

if stale:
    mins = int((now - d.get("generated_at", 0)) / 60)
    print(f"⚠️ status.json is {mins}m old - generator may be off | color=red")
    print("---")

shown = 0
for s in ss:
    if s["state"] == "idle" and shown >= 10:
        continue
    dot = {"working": "\U0001f7e2", "quiet": "\U0001f7e1", "idle": "⚪️"}[s["state"]]
    nsub = s.get("subagents") or 0
    sub = " · %d sub" % nsub if nsub else ""
    model = s.get("model", "").replace("claude-", "")
    t = clean(s.get("title", "?"))
    a = ago(s.get("age_s", 0))
    print(f"{dot} {t} — {a} · {model}{sub} | href={PAGE}")
    dg = clean(s.get("doing") or "")[:120]
    if dg:
        print(f"--{dg} | size=11")
    for a in s.get("subagent_list") or []:
        rt = a.get("runtime_s")
        rtxt = "?" if rt is None else (str(rt) + "s" if rt < 90 else (str(rt // 60) + "m" if rt < 5400 else str(rt // 3600) + "h"))
        mark = "\U0001f7e2" if a.get("active") else "✓"
        label = a.get("role") or clean(a.get("task") or "")[:24]
        tk = a.get("tok") or 0
        ttxt = "" if not tk else (" · %dk tok" % (tk // 1000) if tk >= 1000 else " · %d tok" % tk)
        body = clean(label + (" — " + (a.get("doing") or a.get("task") or "")))[:100] + ttxt
        print(f"--{mark} {rtxt} · {body} | size=11")
    shown += 1

print("---")
print(("⏸ Relay: PAUSED" if paused else "▶️ Relay: autonomous") + f" | href={PAGE}")
ll = clean(r.get("log_last") or "")[:120]
if ll:
    print(f"--{ll} | size=11")
ul = clean(d.get("usage_last") or "")[:120]
if ul:
    print(f"--budget: {ul} | size=11")
print(f"Open Claude Watcher | href={PAGE}")
'
