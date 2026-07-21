#!/usr/bin/env python3
"""Claude Watcher — generator.

Observes every Claude session on this Mac FROM OUTSIDE (file mtimes and
transcript tails — never self-reporting, zero tokens at runtime) and writes:
  - status.json           machine-readable feed (menu bar plugin reads this)
  - index.html            self-contained dashboard (data inlined; just open it)

Run every 60s via launchd (see install.sh). Config below or via env vars."""
import json, os, time, glob, re

HOME = os.path.expanduser("~")
# Where output lands. Point a web server at it, or just open index.html.
OUT_DIR = os.environ.get("CW_OUT", os.path.join(HOME, ".claude-watcher"))
OUT = os.path.join(OUT_DIR, "status.json")
# Cowork (Claude desktop agent) session store — same path on every Mac.
BASE = os.path.join(HOME, "Library/Application Support/Claude/local-agent-mode-sessions")
# Optional: a relay/automation dir with .stop/.halt kill-switch files and logs.
RELAY = os.environ.get("CW_RELAY_DIR", "")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
now = time.time()


def newest_mtime(root, cap=8000):
    latest, n = 0, 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", "outputs")]
        for f in filenames:
            n += 1
            if n > cap: return latest
            try: latest = max(latest, os.path.getmtime(os.path.join(dirpath, f)))
            except OSError: pass
    return latest

def active_subagents(root):
    count = 0
    for p in glob.glob(os.path.join(root, ".claude/projects/*/*/subagents/*.jsonl")):
        try:
            if now - os.path.getmtime(p) < 180: count += 1
        except OSError: pass
    return count


def extract_last_action(data):
    """Most recent assistant event in a decoded transcript tail: a tool call
    rendered as 'ToolName: <hint>', or the latest text block."""
    desc = ""
    for l in data.splitlines():
        l = l.strip()
        if not l:
            continue
        try:
            j = json.loads(l)
        except Exception:
            continue
        if j.get("type") != "assistant":
            continue
        c = (j.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get("type") == "text" and (b.get("text") or "").strip():
                desc = b["text"].strip()
            elif b.get("type") == "tool_use":
                inp = b.get("input") or {}
                hint = ""
                for k in ("command", "file_path", "path", "description", "subject", "pattern", "url"):
                    v = inp.get(k)
                    if isinstance(v, str) and v.strip():
                        hint = v.strip().splitlines()[0]
                        break
                desc = (b.get("name", "") + (": " + hint if hint else "")).strip()
    desc = " ".join(desc.split())
    for ch in "*`|#":
        desc = desc.replace(ch, "")
    return desc[:160]


def _clean(t, cap=110):
    t = " ".join(str(t).split())
    for ch in "*`|#":
        t = t.replace(ch, "")
    return t[:cap]


def _role(task):
    """'You are a Sonnet BUILDER on Points & Prompts...' -> 'Sonnet BUILDER'."""
    m = re.match(r"(?:you are|you're) (?:an\s+|a\s+|the\s+)?([A-Za-z0-9+&/. -]{3,40}?)(?:\s+agent)?(?=\s+(?:on|for|in|performing|doing)\b|[.,:(]|$)", task or "", re.I)
    if m:
        r = " ".join(m.group(1).split())
        if 2 < len(r) <= 34:
            return r
    return ""


def subagent_details(sdir, limit=8):
    """Per-subagent rows: role, task, last action, start time, runtime, and
    token spend (sum of output_tokens across its assistant turns). Reads the
    whole transcript (capped 8 MB) — subagent files are short-lived and small."""
    import datetime
    out = []
    files = glob.glob(os.path.join(sdir, ".claude/projects/*/*/subagents/*.jsonl"))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for p in files[:limit]:
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        age = int(now - mt)
        if age > 1800:
            continue
        start_ts, task, doing, tok = None, "", "", 0
        try:
            data = open(p, "rb").read(8 * 1024 * 1024).decode("utf-8", "replace")
        except Exception:
            continue
        for l in data.splitlines():
            l = l.strip()
            if not l:
                continue
            try:
                j = json.loads(l)
            except Exception:
                continue
            ts = j.get("timestamp")
            if start_ts is None and ts:
                try:
                    start_ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass
            m = j.get("message") or {}
            if not task and j.get("type") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    task = _clean(c, 80)
                elif isinstance(c, list):
                    for b in c:
                        if b.get("type") == "text":
                            task = _clean(b.get("text", ""), 80)
                            break
            if j.get("type") == "assistant":
                u = m.get("usage") or {}
                tok += (u.get("output_tokens") or 0)
                c = m.get("content")
                if isinstance(c, list):
                    for b in c:
                        if b.get("type") == "text" and (b.get("text") or "").strip():
                            doing = b["text"].strip()
                        elif b.get("type") == "tool_use":
                            inp = b.get("input") or {}
                            hint = ""
                            for k in ("command", "file_path", "path", "description", "subject", "pattern", "url"):
                                v = inp.get(k)
                                if isinstance(v, str) and v.strip():
                                    hint = v.strip().splitlines()[0]
                                    break
                            doing = (b.get("name", "") + (": " + hint if hint else "")).strip()
        out.append({
            "role": _role(task),
            "active": age < 180,
            "age_s": age,
            "runtime_s": int(now - start_ts) if start_ts else None,
            "tok": tok,
            "task": task,
            "doing": _clean(doing, 160),
        })
    return out


def session_tail_info(sdir):
    """Doing line + a 12-bucket (5 min each) activity sparkline for the last
    hour, both from the tail of the newest main transcript."""
    import datetime
    info = {"doing": "", "spark": []}
    files = glob.glob(os.path.join(sdir, ".claude/projects/*/*.jsonl"))
    if not files:
        return info
    p = max(files, key=lambda x: os.path.getmtime(x))
    try:
        data = open(p, "rb").read()[-2000000:].decode("utf-8", "replace")
    except Exception:
        return info
    info["doing"] = extract_last_action(data[-400000:])
    buckets = [0] * 12
    for l in data.splitlines():
        i = l.find('"timestamp":"')
        if i < 0:
            continue
        q = l.find('"', i + 13)
        ts = l[i + 13:q] if q > 0 else ""
        try:
            t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        mins = (now - t) / 60.0
        if 0 <= mins < 60:
            buckets[11 - int(mins // 5)] += 1
    info["spark"] = buckets
    return info


def cli_sessions(limit=8):
    """Claude Code CLI runs (the relay executor, ad-hoc claude -p) from
    ~/.claude/projects — same outside-observer treatment."""
    import datetime
    out = []
    files = [p for p in glob.glob(os.path.join(HOME, ".claude/projects/*/*.jsonl"))
             if "subagents" not in p]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for p in files:
        if len(out) >= limit:
            break
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        age = int(now - mt)
        if age > 48 * 3600:
            break
        d = os.path.basename(os.path.dirname(p))
        name = d.split("-Projects-")[-1] if "-Projects-" in d else d.strip("-")[-30:]
        if len(name) < 3:
            name = "home"
        state = "working" if age < 150 else ("quiet" if age < 1800 else "idle")
        doing, model, start_ts = "", "", None
        if state in ("working", "quiet"):
            try:
                tail = open(p, "rb").read()[-200000:].decode("utf-8", "replace")
                doing = extract_last_action(tail)
                for l in reversed(tail.splitlines()):
                    try:
                        j = json.loads(l)
                    except Exception:
                        continue
                    m = (j.get("message") or {}).get("model")
                    if m:
                        model = m.replace("claude-", "")
                        break
            except Exception:
                pass
        try:
            head = open(p, "rb").read(32768).decode("utf-8", "replace")
            for l in head.splitlines():
                try:
                    ts = json.loads(l).get("timestamp")
                    if ts:
                        start_ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        break
                except Exception:
                    continue
        except Exception:
            pass
        out.append({
            "kind": "cli",
            "created_s": int(now - start_ts) if start_ts else None,
            "id": os.path.basename(p)[:-6],
            "title": name,
            "model": model or "cli",
            "age_s": age,
            "state": state,
            "subagents": 0,
            "doing": doing,
            "spark": [],
            "subagent_list": [],
        })
    return out


sessions = []
for meta_path in glob.glob(os.path.join(BASE, "*/*/local_*.json")):
    try: meta = json.load(open(meta_path))
    except Exception: continue
    if meta.get("isArchived"): continue
    sdir = meta_path[:-5]
    if not os.path.isdir(sdir): continue
    last = newest_mtime(sdir)
    # Belt and braces: the app itself stamps lastActivityAt (ms) in the metadata.
    # Trust whichever signal is fresher — a capped/unlucky file walk can miss the
    # hot file and report a working session as a day old (observed 2026-07-19).
    laa = (meta.get("lastActivityAt") or 0) / 1000.0
    last = max(last, laa if laa < now + 60 else 0)
    if not last or now - last > 48 * 3600: continue  # only sessions active in last 48h
    age = int(now - last)
    state = "working" if age < 150 else ("quiet" if age < 1800 else "idle")
    created = meta.get("createdAt")
    ti = session_tail_info(sdir) if state in ("working", "quiet") else {"doing": "", "spark": []}
    sessions.append({
        "created_s": int(now - created / 1000) if created else None,
        "id": meta.get("sessionId", os.path.basename(sdir)),
        "title": meta.get("title", "?"),
        "model": meta.get("model", "?"),
        "age_s": age,
        "state": state,
        "subagents": active_subagents(sdir) if state == "working" else 0,
        "kind": "cowork",
        "doing": ti["doing"],
        "spark": ti["spark"],
        "subagent_list": subagent_details(sdir) if state in ("working", "quiet") else [],
    })
sessions.extend(cli_sessions())
sessions.sort(key=lambda s: s["age_s"])

def tail_line(path):
    try:
        with open(path, "rb") as f:
            f.seek(max(-4000, -os.path.getsize(path)), 2)
            lines = [l for l in f.read().decode("utf-8", "replace").splitlines() if l.strip()]
            return lines[-1][:300] if lines else ""
    except Exception: return ""

relay = None
if RELAY and os.path.isdir(RELAY):
    relay_log = os.path.join(RELAY, "relay.log")
    relay = {
        "paused_stop": os.path.exists(os.path.join(RELAY, ".stop")),
        "halt": os.path.exists(os.path.join(RELAY, ".halt")),
        "log_age_s": int(now - os.path.getmtime(relay_log)) if os.path.exists(relay_log) else None,
        "log_last": tail_line(relay_log),
    }

status = {
    "generated_at": int(now),
    "sessions": sessions,
    "relay": relay,
    "usage_last": tail_line(os.path.join(RELAY, ".usage-log"))[:400] if RELAY and os.path.isdir(RELAY) else "",
}
os.makedirs(OUT_DIR, exist_ok=True)
tmp = OUT + ".tmp"
json.dump(status, open(tmp, "w"), indent=1)
os.replace(tmp, OUT)

# Render the self-contained dashboard: inject the data into the template so
# the page works from file:// with zero servers. (It also still fetches
# status.json when hosted, so either deployment mode works.)
try:
    t = open(TEMPLATE, encoding="utf-8").read()
    page = t.replace("var INLINE=null;", "var INLINE=" + json.dumps(status) + ";", 1)
    ptmp = os.path.join(OUT_DIR, "index.html.tmp")
    open(ptmp, "w", encoding="utf-8").write(page)
    os.replace(ptmp, os.path.join(OUT_DIR, "index.html"))
except FileNotFoundError:
    pass
