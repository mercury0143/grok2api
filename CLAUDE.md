# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run granian --interface asgi --host 0.0.0.0 --port 8000 --workers 1 app.main:app

# Run tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_tool_calls_live.py -v

# Docker
docker compose up -d
```

## Architecture

Grok2API is a FastAPI gateway that exposes Grok Web capabilities as OpenAI-compatible and Anthropic-compatible APIs. It manages a pool of Grok accounts with quota tracking, load balancing, and multi-protocol support.

### Layers

**Products** (`app/products/`) — API surface
- `openai/` — `/v1/chat/completions`, `/v1/images/*`, `/v1/videos/*`, `/v1/responses`
- `anthropic/` — `/v1/messages`
- `web/` — Admin UI and WebUI (account/config/cache management)

**Control** (`app/control/`) — Business logic
- `account/` — Account lifecycle, quota windows, repository backends (local/Redis/MySQL/PostgreSQL)
- `model/registry.py` — Master model list with tier/capability metadata
- `proxy/` — Cloudflare clearance scheduling

**Dataplane** (`app/dataplane/`) — Runtime execution
- `account/` — In-memory account table, sync loop, selector, lease/feedback
- `proxy/` — Proxy pool, selector, session adapters
- `reverse/` — The core reverse pipeline: `executor.py` runs 7 steps (plan → account → proxy → serialize → execute → classify → feedback)
  - `protocol/` — Grok-specific protocol handlers (chat, image, video, auth, usage)
  - `transport/` — HTTP, WebSocket, gRPC-Web, Imagine WS, LiveKit

**Platform** (`app/platform/`) — Infrastructure
- `config/` — TOML/Redis/SQL config backends with hot-reload via `snapshot.py`
- `auth/middleware.py` — API key verification
- `logging/`, `storage/`, `runtime/`, `net/`

### Key Design Decisions

**Reverse pipeline** (`app/dataplane/reverse/executor.py`): Every request flows through a fixed 7-step pipeline. Understanding this file is essential before modifying request handling.

**Account pools**: Accounts are tiered (basic/super/heavy). `app/dataplane/account/selector.py` picks accounts based on model tier and quota availability. Quota windows are per-mode (auto/fast/expert/heavy).

**Leader election**: Only one worker runs the heavy `AccountRefreshScheduler`. Uses advisory file lock (`.scheduler.lock`) — fcntl on Unix, always-leader on Windows.

**Config hierarchy**: `config.defaults.toml` → backend overrides (TOML/Redis) → `GROK_*` env vars (highest priority). Change detection uses a single `stat()` per request.

**Multi-worker sync**: All workers run a lightweight account-directory sync loop (`ACCOUNT_SYNC_INTERVAL`, default 30s). Only the leader runs quota refresh.

### Critical Files

| File | Purpose |
|------|---------|
| `app/main.py` | App factory, lifespan startup sequence, middleware |
| `app/dataplane/reverse/executor.py` | 7-step reverse pipeline |
| `app/dataplane/reverse/protocol/xai_chat.py` | Grok chat protocol + streaming |
| `app/control/account/models.py` | Account and quota data models |
| `app/control/model/registry.py` | All supported models with tier/capability |
| `app/platform/config/snapshot.py` | Immutable config view, change detection |
| `config.defaults.toml` | All default configuration values |

## Configuration

Runtime config lives in `${DATA_DIR}/config.toml` (default `./data/config.toml`). Key sections: `app`, `features`, `proxy`, `retry`, `account.refresh`, `chat`/`image`/`video` timeouts.

Environment variables (`.env`): `ACCOUNT_STORAGE` (local|redis|mysql|postgresql), `DATA_DIR`, `LOG_DIR`, `SERVER_WORKERS`.

## Known Issues & Fixes

**curl_cffi browser impersonation version mismatch** (`ImpersonateError: Impersonating chromeXXX is not supported`):
curl_cffi only supports specific Chrome versions. If the configured `user_agent` contains a Chrome version newer than what curl_cffi supports, `_resolve_browser` would build an unsupported string like `chrome147`.

Fix applied in `app/dataplane/proxy/adapters/session.py`: `_clamp_chrome()` reads supported versions from `BrowserType` at startup and clamps any unsupported version down to the highest available (e.g. Chrome/147 → `chrome146`). `headers.py` reuses the same helper. This is forward-compatible — when curl_cffi adds support for a newer version, it picks it up automatically.

If not using a `user_agent` with a newer Chrome version, you can also just set `browser = "chrome146"` in `[proxy.clearance]` config as a simpler workaround.

## Testing

Live tests require a running server and valid credentials in env. SQL backend tests (`test_sql_engine_factory.py`) are self-contained.
