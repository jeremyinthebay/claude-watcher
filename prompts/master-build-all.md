# master build — the one-paste version

Runs Levels 1→3 as gated phases in a single session. Level 4 (the multi-agent
driver mode) is intentionally NOT included — it changes how your session
operates, not what the watcher is; adopt it separately.

Paste this into a Claude (Cowork / Claude Code) session:

```
Build me the complete Claude Watcher in THREE PHASES, in order. The phase
specs are canonical — fetch each one and execute it exactly:

  Phase 1: https://raw.githubusercontent.com/jeremyinthebay/claude-watcher/main/prompts/level1-local-dashboard.md
  Phase 2: https://raw.githubusercontent.com/jeremyinthebay/claude-watcher/main/prompts/level2-menubar-and-doing.md
  Phase 3: https://raw.githubusercontent.com/jeremyinthebay/claude-watcher/main/prompts/level3-mission-control.md

(If you cannot fetch URLs, stop and ask me to paste the three specs instead.
Do not reconstruct them from memory — the specs contain hard-won traps whose
exact wording is the point.)

THE GATE RULE — this is not optional:
Each phase ends with a VERIFY block. You may not start the next phase until
the current phase's VERIFY passes with pasted, real evidence — command
output, not summaries. If a phase fails its own verification twice, STOP
ENTIRELY and report what you observed. Do not build phase N+1 on an
unverified phase N: a dashboard on a broken generator is worse than no
dashboard, because it will be confidently wrong.

Working style:
- Announce each phase transition in one line ("Phase 1 verified — starting
  Phase 2") so I can skim progress.
- Every file you create gets shown to me as a diff or full listing.
- Nothing public, no servers, no network calls at runtime, zero tokens spent
  by the watcher itself. The final state must include: the launchd job
  loaded, the dashboard open and showing THIS session as working, and the
  menu bar glyph visible.

When all three phases are verified, finish with a five-line summary: what
runs, where, on what schedule, and the one command that tears it all down.
```

**Or skip the prompts entirely:** `git clone` this repo and run `./install.sh` —
same result in two minutes. The prompts are the learn-by-building path.
