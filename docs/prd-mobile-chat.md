# PRD: Remote Mobile Chat Access

**Status:** Draft v2 — pending user review
**Author:** Claude (Coordinator), reviewed by Gemini & Codex
**Last updated:** 2026-02-27

---

## Problem

The agentchattr chat is currently only accessible on the local machine where the server runs. There is no way to monitor or message the agents from a mobile device or when away from the workstation.

## Goal

Enable the user to access the agentchattr chat from a mobile device (iPhone) and send messages to agents remotely.

## Non-Goals

- Native iOS/Android app
- Multi-user / multi-tenant support
- High-traffic scalability (low-volume personal use only)
- Real-time video/audio

---

## User Stories

1. **As the user**, I want to see the live agent chat on my iPhone, so I can monitor what the agents are doing without being at my desk.
2. **As the user**, I want to send messages and @mention agents from my phone, so I can give direction or unblock them remotely.
3. **As the user**, I want access to be protected so that only I can trigger agent actions.

---

## Architecture Note (Critical)

The agents (Claude, Codex, Gemini) read local queue files (`./data/*_queue.jsonl`) to know when to act. Any solution where the chat server moves off the local machine must account for this — otherwise agents won't receive remote messages.

---

## Options

### Option A — ngrok or Tailscale (Recommended to start)

Expose the locally-running server to the internet via a tunnel.

**How it works:**
- Run `ngrok http 8300` (or Tailscale) on your Mac
- Get a public HTTPS URL (e.g. `https://abc123.ngrok.io`)
- Access it from any device

**Pros:**
- Zero code changes
- Works today with one command
- Agents work exactly as now (queue files are still local)
- HTTPS included

**Cons:**
- Requires your Mac to be on and ngrok running
- ngrok free tier has a changing URL on each restart (paid plan or Tailscale gives a stable URL)

**Scope:** None (setup only) — optionally add auth token to `app.py` (~20 lines)

---

### Option B — Slack Integration

A bridge script relays messages between a Slack channel and agentchattr.

**How it works:**
- Create a Slack app with a bot token
- Small Python bridge (~150 lines) listens to Slack via Events API or Socket Mode
- Messages from Slack → forwarded to agentchattr queue files (agents respond normally)
- Agent responses → posted back to Slack channel

**Pros:**
- Use the Slack mobile app you already have
- Full message history via Slack's native history
- No public URL needed (Socket Mode works without inbound firewall rules)
- Works on any device with Slack

**Cons:**
- Requires a Slack workspace
- ~150-line bridge script to write and maintain
- Slack API rate limits (generous for low volume)

**Scope:** Medium — new `slack_bridge.py`, Slack app config, `config.toml` entry

---

### Option C — Railway Deployment (Requires architecture rewrite)

Host the chat server on Railway; rewrite agents to poll Railway via HTTP.

**How it works:**
- Railway hosts `run.py` (chat server)
- `wrapper.py` rewritten to poll Railway API instead of reading local files
- Full remote server, Mac doesn't need to be on

**Pros:**
- Fully cloud-hosted, Mac can be off
- Stable URL

**Cons:**
- Major rewrite of `wrapper.py` (agents currently use local file queues)
- Ongoing Railway hosting cost
- Significantly more complex

**Scope:** Large — estimated 2-4 days MVP, 1-2 weeks production-grade

---

## Recommendation

**Start with Option A (ngrok)** to get mobile access immediately with zero code. If you want persistent, always-on access without your Mac, **Option B (Slack)** is the next step — it avoids the architecture rewrite of Option C.

---

## Open Questions for User

1. **Which option?** A (ngrok now), B (Slack integration), C (Railway), or start with A and plan B?
2. **Auth:** If Option A, do you want a secret URL token to protect access?
3. **Slack workspace:** If Option B, do you have a workspace to use?
4. **Always-on requirement:** Does your Mac stay on when you want remote access, or do you need the server to run independently?
