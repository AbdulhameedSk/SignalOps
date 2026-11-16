# static/ — the dashboard

## No build step

Three files: `index.html`, `style.css`, `app.js`. Vanilla JS — no React,
no bundler, no `node_modules`. For an ops dashboard (lists, buttons, a
live feed), plain JS is enough and means the whole app is one deployable.

## How it works

- **REST for state**: `fetch()` hits `/api/incidents`, `/api/actions`.
  Called on load and every 3s (refresh cycle).
- **SSE for liveness**: `new EventSource('/api/incidents/{id}/stream')`
  pushes events as they happen — the feed updates in real time.
- **Two render paths**: `renderEvent()` appends to the feed on each SSE
  message; `loadActions()` redraws the action cards after approve/reject.

## The flow for a user

1. Click **+ Simulate incident** → `POST /api/demo` → sidebar updates.
2. Click an incident → SSE connects → feed starts scrolling.
3. Agent proposes an action → action card appears with Approve/Reject.
4. Click Approve → `POST /api/actions/{id}/decide` → card updates, feed
   shows "approved and executed (simulated)", incident resolves.
