#!/bin/zsh
# usage-probe.sh — read the REAL usage meters (same endpoint `claude /usage` uses).
# v2 (2026-07-24): self-heals an expired OAuth access token via the stored refresh
#   token, persisting the refreshed credential back to the login keychain IN PLACE
#   (same service+account) after a timestamped backup. Never prints/logs any token.
#   Also writes a structured ~/.claude-watcher/meters.json for the dashboard.
# Usage:  usage-probe.sh          -> one parseable summary line
#         usage-probe.sh --json   -> full raw JSON of the usage payload
# Exit:   0 ok, 2 no token, 3 network, 4 API error even after refresh (needs `claude login`).
set -uo pipefail
export CW_MODE="${1:-summary}"
exec /usr/bin/python3 - <<'PY'
import os, sys, json, time, subprocess, urllib.request, urllib.error

SVC   = "Claude Code-credentials"
ACCT  = "jeremysmith"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
BETA      = "oauth-2025-04-20"
CWDIR = os.path.expanduser("~/.claude-watcher")
MODE  = os.environ.get("CW_MODE", "summary")
os.makedirs(CWDIR, exist_ok=True)
try: os.chmod(CWDIR, 0o700)
except OSError: pass

def die(msg, code):
    print(msg); sys.exit(code)

def read_cred():
    try:
        raw = subprocess.run(["security","find-generic-password","-s",SVC,"-a",ACCT,"-w"],
                             capture_output=True, text=True, timeout=15)
    except Exception:
        die("ERROR keychain-read-failed", 2)
    if raw.returncode != 0 or not raw.stdout.strip():
        die("ERROR no-oauth-token-in-keychain", 2)
    try:
        return json.loads(raw.stdout)
    except Exception:
        die("ERROR keychain-json-unparseable", 2)

def http_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": BETA,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read().decode("utf-8", "replace")

def try_usage(token):
    """Return parsed payload dict on success, None on auth failure, raise on network."""
    try:
        status, body = http_get(USAGE_URL, token)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None
        raise
    if '"five_hour"' not in body:
        return None
    return json.loads(body)

def refresh(cred):
    """Use the refresh token to mint a new access token. Returns new cred dict or None.
    A failed request does NOT consume the refresh token, so this is safe to attempt."""
    oauth = cred.get("claudeAiOauth", {})
    rt = oauth.get("refreshToken")
    if not rt:
        return None
    payload = json.dumps({"grant_type": "refresh_token",
                          "refresh_token": rt, "client_id": CLIENT_ID}).encode()
    req = urllib.request.Request(TOKEN_URL, data=payload,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "claude-cli/1.0 (external, cli)"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            tok = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try: detail = e.read().decode("utf-8","replace")[:120]
        except Exception: detail = ""
        print(f"ERROR refresh-http-{e.code} {detail}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR refresh-network {type(e).__name__}", file=sys.stderr)
        return None
    at = tok.get("access_token")
    if not at:
        return None
    new = dict(cred)
    o = dict(oauth)
    o["accessToken"] = at
    if tok.get("refresh_token"):
        o["refreshToken"] = tok["refresh_token"]
    exp_in = int(tok.get("expires_in") or 0)
    if exp_in:
        o["expiresAt"] = int(time.time() * 1000) + exp_in * 1000
    new["claudeAiOauth"] = o
    return new

def persist(new_cred):
    """Backup old cred + save new cred to files, then update the keychain in place.
    Returns True only if the keychain read-back matches. Never prints token values."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    # 1) backup current keychain value verbatim (recovery point)
    cur = read_cred()
    bkp = os.path.join(CWDIR, f"cred-backup-{ts}.json")
    with open(bkp, "w") as f: json.dump(cur, f)
    os.chmod(bkp, 0o600)
    # 2) stash the new cred too, so a failed keychain write is still recoverable
    newf = os.path.join(CWDIR, f"cred-new-{ts}.json")
    with open(newf, "w") as f: json.dump(new_cred, f)
    os.chmod(newf, 0o600)
    blob = json.dumps(new_cred)
    # 3) in-place update: same service + account => updates, never duplicates
    r = subprocess.run(["security","add-generic-password","-U","-s",SVC,"-a",ACCT,"-w",blob],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        print(f"ERROR keychain-write-rc{r.returncode} (new cred saved at {newf})", file=sys.stderr)
        return False
    # 4) verify read-back matches
    back = read_cred()
    ok = back.get("claudeAiOauth",{}).get("accessToken") == new_cred["claudeAiOauth"]["accessToken"]
    if ok:
        # keep only the 5 most recent backups
        try:
            b = sorted([p for p in os.listdir(CWDIR) if p.startswith(("cred-backup-","cred-new-"))])
            for old in b[:-10]:
                os.remove(os.path.join(CWDIR, old))
        except Exception: pass
    return ok

def fmt_reset(x):
    r = (x or {}).get("resets_at")
    if not r: return "NA"
    try:
        import datetime
        return datetime.datetime.fromisoformat(r).astimezone().strftime("%a-%H:%M")
    except Exception:
        return "NA"

def pct(x):
    return "NA" if not x or x.get("utilization") is None else str(round(x["utilization"]))

def emit(payload):
    """Print the summary line (or raw json) and write structured meters.json."""
    if MODE == "--json":
        print(json.dumps(payload)); 
    fh, sd, ex = payload.get("five_hour"), payload.get("seven_day"), payload.get("extra_usage") or {}
    parts = [f"session={pct(fh)}%(resets {fmt_reset(fh)})",
             f"weekly={pct(sd)}%(resets {fmt_reset(sd)})"]
    scoped = []
    for lim in payload.get("limits") or []:
        if lim.get("kind") == "weekly_scoped" and lim.get("percent") is not None:
            name = ((lim.get("scope") or {}).get("model") or {}).get("display_name") or "scoped"
            parts.append(f"weekly_{name.lower()}={lim['percent']}%")
            scoped.append({"name": name, "pct": lim["percent"]})
    extra = None
    if ex.get("is_enabled"):
        used = (ex.get("used_credits") or 0)/100.0
        cap  = (ex.get("monthly_limit") or 0)/100.0
        util = ex.get("utilization") or 0
        parts.append(f"extra=${used:.2f}/${cap:.0f}({util:.0f}%)")
        extra = {"enabled": True, "used": round(used,2), "cap": round(cap,2), "pct": round(util)}
    meters = {
        "ok": True, "error": None, "ts": int(time.time()),
        "session_pct": (None if pct(fh)=="NA" else int(pct(fh))), "session_resets": fmt_reset(fh),
        "weekly_pct": (None if pct(sd)=="NA" else int(pct(sd))), "weekly_resets": fmt_reset(sd),
        "scoped": scoped, "extra": extra, "summary": " ".join(parts),
    }
    mf = os.path.join(CWDIR, "meters.json")
    with open(mf, "w") as f: json.dump(meters, f)
    if MODE != "--json":
        print(" ".join(parts))

def main():
    cred = read_cred()
    oauth = cred.get("claudeAiOauth", {})
    exp = int((oauth.get("expiresAt") or 0)/1000)
    at  = oauth.get("accessToken")
    fresh_enough = at and exp > time.time() + 120
    # Fast path: token still valid -> just read.
    if fresh_enough:
        try:
            p = try_usage(at)
        except Exception:
            die("ERROR curl-failed-or-empty", 3)
        if p is not None:
            emit(p); return
    # Slow path: expired or rejected -> refresh, persist, retry.
    newc = refresh(cred)
    if not newc:
        die("ERROR api-refresh-failed (needs `claude login`)", 4)
    if not persist(newc):
        die("ERROR keychain-persist-failed", 4)
    try:
        p = try_usage(newc["claudeAiOauth"]["accessToken"])
    except Exception:
        die("ERROR curl-failed-or-empty", 3)
    if p is None:
        die("ERROR api-after-refresh", 4)
    emit(p)

main()
PY
