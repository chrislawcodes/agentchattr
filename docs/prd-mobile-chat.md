# PRD: Remote Mobile Chat Access

**Status:** Draft — pending user review
**Author:** Claude (Coordinator)
**Last updated:** 2026-02-27

---

## Problem

The agentchattr chat is currently only accessible on the local machine where the server runs. There is no way to monitor or message the agents from a mobile device or when away from the workstation.

## Goal

Deploy the agentchattr server to Railway so that the chat UI is accessible remotely from any device, including mobile browsers.

## Non-Goals

- Native iOS/Android app
- Multi-user / multi-tenant support
- High-traffic scalability (low-volume personal use only)
- Real-time video/audio

---

## User Stories

1. **As the user**, I want to open a URL on my iPhone and see the live agent chat, so I can monitor what the agents are doing without being at my desk.
2. **As the user**, I want to send messages to agents from my phone, so I can give direction or unblock them remotely.
3. **As the user**, I want the chat to be protected so that only I can access it (basic auth or secret URL token), so random people can't trigger agent actions.

---

## Requirements

### Functional
- [ ] Chat UI accessible at a public HTTPS URL
- [ ] Real-time message updates work on mobile browsers (existing SSE/WebSocket mechanism)
- [ ] Can send messages and @mention agents from mobile
- [ ] Agent status indicators visible on mobile

### Security
- [ ] Access protected by at least one of:
  - HTTP Basic Auth (username + password via Railway env var)
  - Secret URL token (e.g. `?token=xxx`)
- [ ] HTTPS enforced (Railway provides this automatically)

### Infrastructure
- [ ] Deployed on Railway (user has existing account)
- [ ] Low-volume: < 10 concurrent users, < 1000 messages/day
- [ ] Server listens on `PORT` env var (Railway requirement)
- [ ] MCP server (port 8200/8201) does NOT need to be public — agents run locally, only the chat UI is remote
- [ ] Graceful handling of agent unavailability when running remotely

### Mobile UX
- [ ] Chat UI is responsive / usable on small screens
- [ ] Input field works with mobile keyboard
- [ ] No horizontal scrolling on mobile

---

## Open Questions for User Review

1. **Auth method preference:** Simple secret URL token (easiest) or HTTP Basic Auth (more standard)?
2. **Agent connectivity:** When you access chat remotely, the agents (Claude/Codex/Gemini) are still running locally. Do you want remote messages to @mention them, or is remote access read-only?
3. **Persistence:** Should messages be stored so you can see history from before you connected, or is live-only sufficient?
4. **Railway region:** Any preference, or default (US)?

---

## Proposed Implementation (to be approved before work starts)

1. Add `PORT` env var support to `run.py` (Railway injects this)
2. Add lightweight auth middleware to `app.py` (token or basic auth via env var)
3. Make chat UI responsive for mobile (CSS tweaks to `static/`)
4. Add `railway.json` or `Procfile` for Railway deployment config
5. Update `README.md` with Railway deployment instructions

**Estimated scope:** Small — 3-4 files, no major architectural changes.
