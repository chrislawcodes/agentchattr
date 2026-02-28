# Agent Teamwork Notes

Shared lessons for Claude, Codex, and Gemini working on agentchattr.
Update this file when you solve a recurring problem or discover something useful.

---

## Git workflow

### Upstream PRs must be based off `origin/main`, not fork `main`
`origin` = bcurts/agentchattr (upstream). `fork` = chrislawcodes/agentchattr (our fork).
```bash
git fetch origin
git checkout -b fix/my-fix origin/main  # base off upstream, not fork main
```
If you base off fork `main`, the PR diff will include everything our fork added — bcurts can't review it.

### Check upstream before assuming a file exists
Our fork has files that upstream doesn't (e.g. `tmux_cleanup.py`, `projects.py`).
Before creating an upstream PR for a file, verify it exists in `origin/main`:
```bash
git show origin/main:tmux_cleanup.py  # errors if file doesn't exist upstream
```

### Codex can't push to remote
Codex runs in a network sandbox. Create branches and commit locally, then post `DONE` to chat.
Claude will push and open the PR.

### Keep upstream PRs narrow
bcurts asked for single-purpose PRs touching only the relevant files.
Don't bundle unrelated changes. One fix = one PR.

---

## tmux inject

### Always check inject return value
`wrapper_unix.inject()` returns `bool`. A dead tmux session returns `False`.
Don't call `state.record_inject()` if injection failed — it suppresses retries.

### Inject prompt length limit
Injected prompts into Codex tmux must be short (1–3 sentences + specific commands).
Long prompts cause "Conversation interrupted". Post detailed specs to chat instead,
then inject a short trigger: "Read chat for your task, then implement it."

### Inject key sequence
Always: C-u → Escape → 150ms → text (`-l` flag) → 150ms → Enter.
The `-l` flag sends literal text (no key interpretation). Required for special chars.

---

## MCP sessions

### MCP session goes stale after server restart
After `run.py` restarts, agents' cached MCP session IDs are invalid ("Session not found").
Fix: restart the agent process. The server restart watcher in `wrapper.py` does this automatically
(detects `data/server_started_at.txt` change, sends C-c after 2 confirmed 30s cycles).

### Session token survives restarts
Token is persisted to `data/session_token.txt`. Browser tabs don't get 403 after restart.
If you need to rotate the token, delete that file and restart the server.

---

## Tmux cleanup (disabled)

### Cleanup is disabled by default (`config.toml: enabled = false`)
The 10-minute idle timeout was killing all agents repeatedly because agents appear
"offline" (no MCP tool calls) whenever they're waiting for user input or thinking.
Don't re-enable without a smarter heuristic that accounts for Claude requiring manual input.

---

## Testing

### Always run tests before pushing
```bash
cd /Users/chrislaw/agentchattr
source .venv/bin/activate
python -m pytest tests/ -q
```
52 tests as of fix/stability. All must stay green.

### Test files live in `tests/`
`test_store.py`, `test_wrapper.py`, `test_cleanup.py`, `test_app.py`,
`test_config.py`, `test_monitor.py`, `test_run.py`, `test_mcp_bridge.py`

---

## Token usage

### Target: Claude <50% of total output tokens
As of 2026-02-28: Claude 64.6%, Codex 23.2%, Gemini 12.2% — Claude over budget.
Goal: shift more implementation, review, and chat volume to Gemini and Codex.

**How to measure** (run from `/Users/chrislaw/agentchattr`):
```bash
python3 - <<'EOF'
import json
from pathlib import Path

data = Path("data/agentchattr_log.jsonl")
counts, chars = {}, {}
for line in data.read_text().splitlines():
    try:
        m = json.loads(line)
        s, t = m.get("sender",""), m.get("text","")
        counts[s] = counts.get(s,0) + 1
        chars[s] = chars.get(s,0) + len(t)
    except: pass

agents = ["claude","codex","gemini"]
total = sum(chars.get(a,0) for a in agents)
print(f"{'Agent':<10} {'Msgs':>6} {'~Tokens':>8} {'Share':>7}")
for a in agents:
    c = chars.get(a,0)
    print(f"{a:<10} {counts.get(a,0):>6} {c//4:>8} {c/total*100:>6.1f}%")
EOF
```

### Role split
- **Claude**: assigns tasks, reviews diffs, APPROVE/BLOCK verdicts, merges. Does NOT implement.
- **Gemini + Codex**: implement, write tests, open PRs, post detailed progress. They carry the work.
- Claude chat messages should be short: assignments and verdicts only.
- Gemini and Codex write the substance — detailed updates every 3 min while working.

---

## PR workflow

### Review cycle
1. Implementer posts plan to chat before coding
2. Claude approves plan (or requests changes)
3. Implementer codes, posts progress every 3 min
4. Cross-agent code review: the *other* agent reviews the diff
5. Claude runs tests and does final merge decision

### bcurts review preferences
- Single-purpose PRs only
- Rebased off upstream `origin/main`
- New features need discussion before PR (open an issue first)
- Security posture changes (e.g. session token persistence) need discussion
