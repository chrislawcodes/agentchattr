# TODO

See [WORKFLOW.md](WORKFLOW.md) for the full process.

## Task Template
```
### [Task Title]
- **Owner:** Pending / In Progress - [Agent] / Review - [Agent] / Done
- **Scope:** What exactly is being changed
- **Acceptance criteria:** What "done" looks like
- **Test plan:** How to verify it works
- **Branch:** feature/[slug]
```

---

## Backlog

### Merge PR #1 — fix/gemini-input-stacking
- **Owner:** Done
- **Scope:** Merge the existing PR with Escape fix, configurable cooldowns, tests, and CI
- **Acceptance criteria:** CI green, branch merged to main
- **Test plan:** CI runs automatically on merge

---

### Session resume on restart
- **Owner:** Done
- **Scope:** `wrapper.py` — use each agent's `resume_flag` from config to resume the previous session on restart instead of starting cold
- **Acceptance criteria:** Restarting `start_gemini.sh` resumes the last Gemini session; same for Claude and Codex
- **Test plan:** Unit test that `run_agent` constructs the correct resume command; manual smoke test
- **Branch:** feature/session-resume

---

### Stale queue file cleanup on startup
- **Owner:** Done
- **Scope:** `wrapper.py` — flush (truncate) the agent's queue `.jsonl` file at startup to prevent leftover entries from a previous crashed session firing unexpectedly
- **Acceptance criteria:** Starting a wrapper with a non-empty queue file does not trigger spurious injections
- **Test plan:** Unit test with a pre-populated queue file; verify it is cleared before the watcher starts
- **Branch:** feature/queue-flush-on-start

---

### Windows wrapper parity (Escape-before-inject)
- **Owner:** Done
- **Scope:** `wrapper_windows.py` — add the same Escape keystroke before injection that was added to `wrapper_unix.py` in PR #1
- **Acceptance criteria:** Windows inject function sends Escape → text → Enter, matching unix behavior; existing windows tests (if any) pass
- **Test plan:** Unit test mirroring `test_inject_sends_escape_before_text` for the windows inject path
- **Branch:** fix/windows-wrapper-parity

---

### "Working" indicator in chat UI
- **Owner:** Done
- **Scope:** Show a `…` or "active" status next to an agent's name in the chat UI while they are processing a task
- **Acceptance criteria:** Agent status pill shows activity when processing; returns to normal when idle
- **Test plan:** Manual UI test; unit test for backend status endpoint if applicable
- **Branch:** feature/working-indicator

---

### ngrok secret token auth
- **Owner:** Done
- **Scope:** `app.py` — read `ACCESS_TOKEN` env var; reject requests missing `?token=<value>` when set; no change to local-only usage
- **Acceptance criteria:** Setting `ACCESS_TOKEN=xyz ngrok http 8300` and opening `https://xxx.ngrok.io?token=xyz` works; without token param returns 403
- **Test plan:** Unit test middleware; manual test via ngrok URL
- **Branch:** feature/ngrok-auth

---

### ngrok setup docs
- **Owner:** Done
- **Scope:** `README.md` — add ngrok installation, startup command, and `ACCESS_TOKEN` usage instructions
- **Acceptance criteria:** A new user can follow README to get mobile access in < 5 min
- **Test plan:** Walkthrough review
- **Branch:** docs/ngrok-setup

---

### Kanban task sidebar
- **Owner:** Done
- **Scope:** Backend `/api/tasks` endpoint parses `TODO.md` → returns tasks as JSON; frontend collapsible sidebar in `static/` shows kanban columns (Pending / In Progress / Review / Done) with auto-refresh every 30s
- **Acceptance criteria:** Sidebar visible in chat UI; cards update when TODO.md changes; works on mobile viewport
- **Test plan:** Unit test TODO.md parser; manual UI test
- **Branch:** feature/kanban-sidebar-full

---

### @user mentions filter
- **Owner:** Done
- **Scope:** `static/` — add a filter button/tab to the chat UI showing only messages that @mention the user, with an unread badge count
- **Acceptance criteria:** Clicking the filter shows only @user messages; badge shows count of unseen @mentions; clicking a mention scrolls to it
- **Test plan:** Manual UI test; works on mobile viewport
- **Branch:** feature/user-mentions-filter

---

### `/status` command — agent health check
- **Owner:** Done
- **Scope:** Add a `/status` slash command (or equivalent API endpoint) that reports each agent's online status, last-seen time, and queue depth
- **Acceptance criteria:** Typing `/status` in the chat UI returns a health summary for all configured agents
- **Test plan:** Unit test the status logic; integration test via the API endpoint
- **Branch:** feature/status-command

---

### `/history` command — cross-session message history
- **Owner:** Done
- **Scope:** Add a `/history [n]` command that returns the last N messages from the persistent store, including messages from previous sessions
- **Acceptance criteria:** `/history 20` returns the 20 most recent messages regardless of when the server started
- **Test plan:** Unit test store retrieval; manual test across a server restart
- **Branch:** feature/history-command

---

### Automated stale tmux session cleanup
- **Owner:** Done
- **Scope:** Add logic to detect and kill tmux sessions for agents that have been offline for > N minutes (configurable)
- **Acceptance criteria:** Dead sessions are cleaned up automatically; active sessions are untouched
- **Test plan:** Unit test session detection logic with mocked tmux output
- **Branch:** feature/tmux-session-cleanup

---

### Agent task monitor
- **Owner:** Done
- **Scope:** `wrapper.py` — add background thread to auto-reinject `chat - use mcp` if queue is non-empty but agent is idle for >5 min
- **Acceptance criteria:** Agents that get stuck on a prompt are automatically reminded to check the chat
- **Test plan:** Unit test monitor logic; manual verification
- **Branch:** feature/agent-task-monitor

---

### Agent mention autocomplete
- **Owner:** Done
- **Scope:** In `static/chat.js`, show a dropdown of available agents when the user types `@`. Selecting one autocompletes the mention.
- **Acceptance criteria:** Dropdown shows matching agents; keyboard navigation works; selecting inserts `@name ` and hides menu.
- **Test plan:** Manual UI test
- **Branch:** feature/agent-mention-autocomplete

---

### Projects — multi-context workspaces
- **Owner:** Review - claude (implemented by gemini-cli)
- **Scope:** Add a "Projects" concept so agents and the user can switch between separate working contexts (e.g., "agentchattr", "Valuerank coding", "Valuerank vignette analysis"). Each project has its own chat history, task list, and agent assignments.
- **Acceptance criteria:** User can create/switch projects from the UI; chat history and tasks are scoped per project; agents know which project context they are in
- **Test plan:** Manual UI test across at least 2 projects; verify history isolation; unit test project switching logic
- **Branch:** feature/projects
- **Note:** Implementation complete: project-scoped data dirs, switcher UI, and MCP project support.

---

## Stability Plan

### Background

The system has been accumulating reactive "fix by restarting" logic that makes things *less* stable — each new restart mechanism can fire on false positives and interrupt active agent sessions mid-task. The root principle guiding all fixes below: **"Don't interrupt active work" > "Recover from failures"**.

### What's already been fixed (this session)

**Fix A — Stability logging** (`wrapper.py`, `wrapper_unix.py`, `watchdog.sh`)
- `wrapper.py` now calls `logging.basicConfig()` — previously `log.info()`/`log.debug()` were silently dropped in the wrapper process (no handler was configured)
- Per-agent stability log: `data/{agent}_stability.log` — timestamped record of every `[health]`, `[inject]`, `[session]`, and `[kill]` event
- All stability events now carry a tagged prefix so you can grep for patterns
- `watchdog.sh` now uses `tee` to log to `data/watchdog.log` with full timestamps

**Fix B — Health watcher kill thresholds** (`wrapper.py` `_watch_mcp_health`)
- **Before:** SSE kills on **1** failure; HTTP kills after **3** failures × 30s = ~90s
- **After:** SSE kills after **5 consecutive** failures (~2.5 min); HTTP kills after **10 consecutive** failures (~50 min)
- Separate counters for SSE and HTTP so a recovery on one doesn't mask failures on the other
- A single transient blip now logs a warning but never triggers a kill

**Fix C — Smarter watchdog** (`macos-linux/watchdog.sh`)
- **Before:** If wrapper process died, always restart it (which kills the old tmux session)
- **After:** If wrapper process died but tmux session is still alive, log `SKIP` and do nothing — the agent is still running

---

### Remaining fixes (for review)

#### Fix D — Chat notifications for stability events
- **Owner:** Done - Gemini
- **Scope:** `wrapper.py` — when `_kill_tmux_session` fires (from health watcher or server restart watcher), make an MCP `chat_send` call posting a system-style message to the chat before killing. This makes session kills visible in the UI without requiring anyone to tail log files.
- **Approach:** Pass `mcp_url` and `agent_name` into the kill callers; call `_call_mcp_tool(mcp_url, "chat_send", {"sender": "system", "message": "..."})` before `_kill_tmux_session`. Best-effort only — don't block or retry on failure.
- **Acceptance criteria:** When a session is killed by the health watcher or server restart watcher, a message like `"[stability] Killing agentchattr-gemini — 5 consecutive SSE failures"` appears in the chat UI. Session kills via Ctrl+C or normal exit do NOT post messages.
- **Test plan:** Unit test that the notification helper calls `_call_mcp_tool` with the right args; mock the tool call to avoid needing a live server.
- **Branch:** `fix/stability-chat-notifications`

---

#### Fix E — Increase task monitor timeout
- **Owner:** Done - Gemini
- **Scope:** `config.toml` — raise `agent_task_timeout_minutes` from `5.0` to `15.0`. An agent running a multi-step task easily goes 5 minutes without a new MCP call; the current timeout causes spurious re-injections that interrupt long-running work.
- **Acceptance criteria:** `config.toml` has `agent_task_timeout_minutes = 15.0`; existing unit tests for the task monitor still pass.
- **Test plan:** Check `tests/` for task monitor tests; update expected value if hardcoded.
- **Branch:** `fix/task-monitor-timeout` (or just a direct commit to main)

---

#### Fix F — Make health thresholds configurable
- **Owner:** Done - Gemini
- **Scope:** `config.toml` + `wrapper.py` — expose `[mcp] sse_kill_threshold` and `http_kill_threshold` so thresholds can be tuned without code changes. Default to current hardcoded values (5 and 10).
- **Acceptance criteria:** Setting `sse_kill_threshold = 3` in config.toml is respected by `_watch_mcp_health`; existing behavior unchanged when keys are absent.
- **Test plan:** Unit test that custom values from config are passed through correctly.
- **Branch:** `fix/configurable-health-thresholds`
