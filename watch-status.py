#!/usr/bin/env python3
"""Claude Watcher — generator.

Observes every Claude session on this Mac FROM OUTSIDE (file mtimes and
transcript tails — never self-reporting, zero tokens at runtime) and writes:
  - status.json           machine-readable feed (menu bar plugin reads this)
  - index.html            self-contained dashboard (data inlined; just open it)

Run every 60s via launchd (see install.sh). Config below or via env vars."""
import json, os, time, glob, re

HOME = os.path.expanduser("~")
OUT_DIR = os.environ.get("CW_OUT", os.path.join(HOME, ".claude-watcher"))
OUT = os.path.join(OUT_DIR, "status.json")
BASE = os.path.join(HOME, "Library/Application Support/Claude/local-agent-mode-sessions")
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


def subagent_details(files, limit=8, max_age=1800):
    """Per-subagent rows: role, task, last action, start time, runtime, and
    token spend (sum of output_tokens across its assistant turns). Reads the
    whole transcript (capped 8 MB) — subagent files are short-lived and small.
    Works for Cowork sessions and Claude Code CLI runs alike: same layout."""
    import datetime
    out = []
    files = sorted(files, key=lambda p: os.path.getmtime(p), reverse=True)
    for p in files[:limit]:
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        age = int(now - mt)
        if age > max_age:
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
    info["spark"] = spark_from(data)
    return info


def spark_from(data):
    """12 buckets x 5 min of transcript-event density for the last hour."""
    import datetime
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
    return buckets


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
        doing, model, start_ts, spark = "", "", None, []
        sl = subagent_details(glob.glob(p[:-6] + "/subagents/*.jsonl")) if state in ("working", "quiet") else []
        if state in ("working", "quiet"):
            try:
                tail = open(p, "rb").read()[-2000000:].decode("utf-8", "replace")
                doing = extract_last_action(tail[-200000:])
                spark = spark_from(tail)
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
            "subagents": len([a for a in sl if a["active"]]),
            "doing": doing,
            "spark": spark,
            "subagent_list": sl,
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
        "subagent_list": subagent_details(glob.glob(os.path.join(sdir, ".claude/projects/*/*/subagents/*.jsonl"))) if state in ("working", "quiet") else [],
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

CWDIR = os.path.expanduser("~/.claude-watcher")

def _ccusage_daily():
    """Full-history daily usage from ccusage (local logs, zero auth). Cached 10 min so
    the 60s generator never re-parses. Prefers a global `ccusage`, falls back to npx."""
    import subprocess
    cache = os.path.join(CWDIR, "ccusage-cache.json")
    try:
        if os.path.getmtime(cache) > now - 600:
            return json.load(open(cache))
    except Exception:
        pass
    # Count Claude Code CLI/relay usage (global ~/.claude) AND desktop/agent
    # sessions (each keeps its own nested .claude/projects). ccusage takes a
    # comma-separated CLAUDE_CONFIG_DIR; cap + sort-by-recency bounds the env size.
    import glob
    cfg = [os.path.expanduser("~/.claude")]
    try:
        base = os.path.expanduser("~/Library/Application Support/Claude/local-agent-mode-sessions")
        cw = [os.path.dirname(p) for p in glob.glob(os.path.join(base, "*/*/*/.claude/projects"))]
        cw.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        cfg += cw[:2000]
    except Exception:
        pass
    env = {**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
           "CLAUDE_CONFIG_DIR": ",".join(cfg)}
    cmds = [["/opt/homebrew/bin/ccusage", "daily", "--since", "20250101", "--json"],
            ["ccusage", "daily", "--since", "20250101", "--json"],
            ["npx", "-y", "ccusage@latest", "daily", "--since", "20250101", "--json"]]
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
            daily = json.loads(out.stdout).get("daily", [])
            if daily:
                os.makedirs(CWDIR, exist_ok=True)
                tmp = cache + ".tmp"; json.dump(daily, open(tmp, "w")); os.replace(tmp, cache)
                return daily
        except Exception:
            continue
    try: return json.load(open(cache))
    except Exception: return []

def budget_snapshot():
    """TODAY / WEEK / MONTH / ALL-TIME token + cost cards with period-over-period
    deltas, a 14-day sparkline, model mix, and the OAuth %-meters (from usage-probe's
    meters.json). All local; never blocks the rest of the feed."""
    import datetime
    daily = _ccusage_daily()
    by = {}
    for d in daily:
        p = d.get("period")
        if p: by[p] = {"tok": d.get("totalTokens", 0) or 0, "cost": d.get("totalCost", 0.0) or 0.0}
    today = datetime.date.today()
    ds = lambda dt: dt.strftime("%Y-%m-%d")
    def sum_days(pred):
        t = c = 0.0
        for p, v in by.items():
            try: dt = datetime.date.fromisoformat(p)
            except Exception: continue
            if pred(dt): t += v["tok"]; c += v["cost"]
        return t, c
    td = by.get(ds(today), {"tok": 0, "cost": 0})
    yd = by.get(ds(today - datetime.timedelta(days=1)), {"tok": 0, "cost": 0})
    iso = today.isocalendar(); yw = lambda dt: dt.isocalendar()[:2]
    tw = sum_days(lambda dt: yw(dt) == (iso[0], iso[1]))
    lwi = (today - datetime.timedelta(days=7)).isocalendar()
    lw = sum_days(lambda dt: yw(dt) == (lwi[0], lwi[1]))
    tm = sum_days(lambda dt: (dt.year, dt.month) == (today.year, today.month))
    pm = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    lm = sum_days(lambda dt: (dt.year, dt.month) == pm)
    at = sum_days(lambda dt: True)
    dpct = lambda cur, prev: (round((cur - prev) / prev * 100, 1) if prev else None)
    card = lambda ct, cc, pt, lab: {"tokens": int(ct), "cost": round(cc, 2),
        "prior_tokens": int(pt), "prior_label": lab, "delta_pct": dpct(ct, pt)}
    cards = {
        "today": card(td["tok"], td["cost"], yd["tok"], "vs yesterday"),
        "week":  card(tw[0], tw[1], lw[0], "vs last week"),
        "month": card(tm[0], tm[1], lm[0], "vs last month"),
        "all_time": {"tokens": int(at[0]), "cost": round(at[1], 2), "note": "all time"},
    }
    spark = []
    for i in range(13, -1, -1):
        dt = today - datetime.timedelta(days=i); v = by.get(ds(dt))
        spark.append({"date": ds(dt), "tokens": int(v["tok"]) if v else 0})
    mm = {}
    for d in daily:
        try: dt = datetime.date.fromisoformat(d.get("period"))
        except Exception: continue
        if dt > today or (today - dt).days > 30: continue
        for mb in d.get("modelBreakdowns", []):
            name = (mb.get("modelName") or "?").replace("claude-", "")
            e = mm.setdefault(name, {"tok": 0, "cost": 0.0})
            e["tok"] += (mb.get("cacheReadTokens", 0) + mb.get("cacheCreationTokens", 0)
                         + mb.get("inputTokens", 0) + mb.get("outputTokens", 0))
            e["cost"] += mb.get("cost", 0.0)
    tot = sum(v["tok"] for v in mm.values()) or 1
    model_mix = sorted([{"model": k, "tokens": int(v["tok"]), "cost": round(v["cost"], 2),
                         "pct": round(v["tok"] / tot * 100)} for k, v in mm.items()],
                        key=lambda x: -x["tokens"])[:6]
    meters = None
    try:
        mf = os.path.join(CWDIR, "meters.json")
        meters = json.load(open(mf)); meters["age_s"] = int(now - os.path.getmtime(mf))
    except Exception: pass
    try: upd = max(0, int(now - os.path.getmtime(os.path.join(CWDIR, "ccusage-cache.json"))))
    except Exception: upd = None
    return {"cards": cards, "sparkline": spark, "model_mix": model_mix,
            "meters": meters, "updated_s": upd}

try:
    budget = budget_snapshot()
except Exception as e:
    budget = {"error": str(e)[:160]}

_m = (budget or {}).get("meters") or {}
_mage = _m.get("age_s")
if _m.get("ok") and _mage is not None and _mage < 3600 and _m.get("summary"):
    usage_last = _m["summary"]
elif RELAY and os.path.isdir(RELAY):
    usage_last = tail_line(os.path.join(RELAY, ".usage-log"))[:400]
else:
    usage_last = ""

status = {
    "generated_at": int(now),
    "sessions": sessions,
    "relay": relay,
    "budget": budget,
    "usage_last": usage_last,
}
os.makedirs(OUT_DIR, exist_ok=True)
tmp = OUT + ".tmp"
json.dump(status, open(tmp, "w"), indent=1)
os.replace(tmp, OUT)

try:
    t = open(TEMPLATE, encoding="utf-8").read()
    page = t.replace("var INLINE=null;", "var INLINE=" + json.dumps(status) + ";", 1)
    ptmp = os.path.join(OUT_DIR, "index.html.tmp")
    open(ptmp, "w", encoding="utf-8").write(page)
    os.replace(ptmp, os.path.join(OUT_DIR, "index.html"))
except FileNotFoundError:
    pass
