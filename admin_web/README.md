# Gas Billing System — Admin Web

A Streamlit admin dashboard for the [backend](../backend/README.md). Calls the FastAPI backend over `httpx` only — no business logic lives here, matching the approved design's "no separate backend for admins" rule.

## Pages

Overview · Residents · Meter Readings · Billing · Payments · Late Payments · Notifications · Import Data · Billing Configuration · System Settings — one page per admin workflow from the approved design, each a thin wrapper over the corresponding `/api/v1/admin/...` endpoints.

## Structure

```
config.py       Backend URL (ADMIN_WEB_BACKEND_URL env var, defaults to http://localhost:8000)
auth.py         Session-state-backed admin login/logout, require_login() guard
api_client.py   httpx wrapper — one function per backend endpoint, handles JWT
                headers, 401-triggered token refresh, and unwraps the backend's
                uniform {"detail", "error_type", "status_code"} error envelope
Home.py         Entry point / login screen
pages/          One file per admin page (Streamlit's file-based multipage routing)
```

Shared modules (`config.py`, `auth.py`, `api_client.py`) are imported as flat siblings (`import auth`, not `import admin_web.auth`) — Streamlit adds the entry script's own directory to `sys.path`, and both `Home.py` and every `pages/*.py` file resolve imports from there.

## Running

```bash
.venv/bin/streamlit run admin_web/Home.py --server.port 8502
```

The backend's `CORS_ORIGINS` must include `http://localhost:8502` (already set in `.env.example`). Log in with an existing `AdminUser`'s email/password — there's no admin signup flow; admins are created directly in the database (or will be, once an admin-invite flow is built).

## Known limitations

Every mutating page (Residents, Billing, Payments, Import Data, System Settings) calls its endpoint directly with no optimistic UI or undo — this mirrors how thin the layer is meant to be. Errors surface via `st.error(...)` using the backend's `detail` message verbatim.
