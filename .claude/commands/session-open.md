# session-open

Mid-session state refresh. (At session start this briefing is auto-injected by the
SessionStart hook — only invoke this command to re-check state after long work or
when the injected briefing has gone stale.)

Run:

```bash
bash /home/tjenkins/Documents/losslessbob/.claude/hooks/session_brief.sh
```

Treat the output as the current project state: branch + uncommitted count, last
commit, latest CHANGELOG entry, top open TODOs, tapematch calibration tail, and the
standing spec-pack pointer. Do not re-derive these with separate git/grep calls.
If `uncommitted files` is large (>30), remind the user to commit before major work.
