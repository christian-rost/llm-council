# CLAUDE.md - Technical Notes for XQT5AIs

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Current State

- **Branch**: `version1` (aktive Entwicklung)
- **Produktname**: XQT5AIs (umbenannt von "LLM Council")
- **Deployment**: Coolify auf VPS
  - Frontend: https://5ais.xqtfive.com
  - Backend: Separate Instanz
- **Datenbank**: Supabase (ersetzt JSON-Dateien seit version1)

## Project Overview

XQT5AIs is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Contains `COUNCIL_MODELS` and `CHAIRMAN_MODEL` as fallback defaults
- Uses environment variables: `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
- Backend runs on **port 8001**
- JWT configuration: `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRATION_HOURS`
- Admin credentials: `admin_user`, `admin_pw` (environment variables)
- RuntimeError if `JWT_SECRET`, `SUPABASE_URL`, or `SUPABASE_KEY` are missing

**`database.py`**
- Supabase client singleton: `create_client(SUPABASE_URL, SUPABASE_KEY)`
- Imported by all modules that need DB access

**`settings.py`**
- App settings stored in `app_settings` table (key-value, JSONB)
- `get_setting(key, default)` / `set_setting(key, value)` (upsert)
- `get_chairman_model()` / `get_council_models()` with config.py fallbacks

**`user_storage.py`**
- **Supabase-based** user storage in `users` table
- **Bcrypt password hashing** via passlib (NOT SHA-256)
- User CRUD operations with error handling
- Functions: `create_user()`, `get_user()`, `get_user_by_username()`, `get_user_by_email()`, `verify_password()`, `list_all_users()`, `delete_user()`, `reset_user_password()`

**`auth.py`**
- JWT token creation and validation
- `get_current_user()`: Dependency for protected routes
- `get_current_admin()`: Dependency for admin-only routes
- `is_admin_user()`: Check if user is admin

**`openrouter.py`**
- `query_model()`: Single async model query with logging
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- Returns dict with 'content' and optional 'reasoning_details'
- Graceful degradation: returns None on failure, continues with successful responses

**`council.py`** - The Core Logic
- `stage1_collect_responses()`: Parallel queries to all council models → returns `(results, failed_models)`
- `stage2_collect_rankings()`: Anonymized peer rankings → returns `(results, label_to_model, failed_models)`
- `stage3_synthesize_final()`: Chairman synthesizes final answer
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section
- `calculate_aggregate_rankings()`: Computes average rank position
- `run_full_council()`: Orchestrates all 3 stages, includes `stage1_failed` + `stage2_failed` in metadata
- **Dynamic models**: Uses `settings.get_council_models()` and `settings.get_chairman_model()` instead of hardcoded config
- **Failed model tracking**: Models that fail (timeout, API error, invalid ID) are tracked and returned separately instead of being silently dropped

**`api_keys.py`**
- API Key management for the public REST API
- `generate_api_key()`: Creates `xqt5-` + 48 hex chars key
- `create_api_key(name, rate_limit)`: Stores bcrypt hash in DB, returns plaintext once
- `verify_api_key(api_key)`: Prefix-lookup + bcrypt verify, updates `last_used_at` + `usage_count`
- `list_api_keys()`: All keys without hash
- `delete_api_key(key_id)`: Soft-delete (is_active=False)

**`storage.py`**
- **Supabase-based** conversation storage in `conversations` + `messages` tables
- Messages stored separately with foreign key to conversation (CASCADE delete)
- User isolation: Users can only see their own conversations

**`main.py`**
- FastAPI app with CORS middleware
- **CORS origins configurable via `CORS_ORIGINS` environment variable**
- Authentication endpoints: `/api/auth/register`, `/api/auth/login`, `/api/auth/me`
- Admin endpoints: `/api/admin/users`, `/api/admin/users/{id}`, etc.
- **Admin settings endpoints**: `/api/admin/settings` (GET/PUT)
- **Admin API key endpoints**: `/api/admin/api-keys` (POST/GET/DELETE)
- **Public REST API**: `/api/v1/council` (POST) — stateless council deliberation via API key
- Input validation on registration (username 3-32 chars, EmailStr, password min 8 chars)
- Internal errors not exposed to clients
- **Rate-Limiting** via slowapi:
  - `/api/auth/login`: 5 Requests/Minute
  - `/api/auth/register`: 3 Requests/Minute
  - `/api/conversations/{id}/message`: 10 Requests/Minute
  - `/api/conversations/{id}/message/stream`: 10 Requests/Minute
  - `/api/v1/council`: 5 Requests/Minute (per API key)

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Main orchestration: manages conversations list and current conversation
- Handles authentication state
- PDF upload support
- **View toggle**: `chat` / `admin` (admin-only)
- Admin button in sidebar for `is_admin` users
- **Failed models UI**: `failedModels` state tracks Stage 1/2 failures; renders warning banners + greyed-out tabs

**`auth.jsx`**
- Authentication context provider
- Token management in localStorage
- Login/logout/register functions

**`api.js`**
- API client with auth headers
- `sendMessageStream()`: SSE streaming with callbacks — `onStage1(data, failedModels)`, `onStage2(data, metadata)`
- Admin methods: `getAdminSettings()`, `updateAdminSettings()`, `getAdminUsers()`, `deleteAdminUser()`

**`components/Login.jsx`**
- Login and registration forms
- Tab-based UI for switching between login/register

**`components/AdminDashboard.jsx`**
- **Model Configuration**: Chairman/Moderator input, Council models list with add/remove
- **User Management**: User table with delete functionality
- Tab-based section switching

**Styling (`*.css`)**
- **XQT5 Corporate Design**:
  - Primary color: `#ee7f00` (Orange)
  - Dark color: `#213452` (Navy-Blau)
  - White: `#ffffff`
- CSS Variables in `index.css` for consistent theming
- Light mode theme

## Database Schema (Supabase)

```sql
-- Users table
users (id UUID PK, username, email, password_hash, is_active, is_admin, created_at)

-- Conversations table
conversations (id UUID PK, user_id FK→users, title, created_at)

-- Messages table (user + assistant messages)
messages (id UUID PK, conversation_id FK→conversations, role, content, stage1 JSONB, stage2 JSONB, stage3 JSONB, metadata JSONB, created_at)

-- App Settings (key-value)
app_settings (key VARCHAR PK, value JSONB, updated_at)

-- API Keys (public REST API)
api_keys (id UUID PK, name, key_hash, key_prefix, is_active, rate_limit, usage_count, created_at, last_used_at)
```

Schema file: `backend/schema.sql` (run in Supabase SQL Editor)

## Environment Variables

### Backend

| Variable | Beschreibung | Pflicht |
|----------|--------------|---------|
| `OPENROUTER_API_KEY` | API-Key for OpenRouter | Ja |
| `JWT_SECRET` | Secret for JWT tokens (min. 32 chars recommended) | **Ja** |
| `SUPABASE_URL` | Supabase project URL | **Ja** |
| `SUPABASE_KEY` | Supabase service_role key | **Ja** |
| `admin_user` | Admin username | Ja |
| `admin_pw` | Admin password | Ja |
| `CORS_ORIGINS` | Allowed origins (comma-separated) | Nein (Default: localhost) |

**Important**: `JWT_SECRET`, `SUPABASE_URL`, and `SUPABASE_KEY` are **required**. Backend will not start without them (RuntimeError).

### Frontend

| Variable | Beschreibung | Pflicht |
|----------|--------------|---------|
| `VITE_API_BASE` | Backend-URL | Ja (Production) |

## Security Features

1. **Bcrypt Password Hashing**: via passlib
2. **Input Validation**: Pydantic validators for registration
3. **CORS Restriction**: Only specific methods/headers allowed
4. **Error Handling**: Internal errors not exposed to clients
5. **Logging**: Proper logging instead of print statements
6. **User Isolation**: Users can only see their own conversations
7. **JWT Secret Required**: RuntimeError if `JWT_SECRET` not set
8. **Secure Admin Check**: `is_admin` flag instead of username comparison
9. **UUID User-IDs**: No timestamp collisions
10. **Rate-Limiting**: slowapi for brute-force and DoS protection
11. **Supabase RLS**: Database-level security (configurable in Supabase dashboard)
12. **API Key Authentication**: Bcrypt-hashed keys with prefix-lookup for the public REST API

## Key Design Decisions

### Stage 2 Prompt Format
```
1. Evaluate each response individually first
2. Provide "FINAL RANKING:" header
3. Numbered list format: "1. Response C", "2. Response A", etc.
4. No additional text after ranking section
```

### De-anonymization Strategy
- Models receive: "Response A", "Response B", etc.
- Backend creates mapping: `{"Response A": "openai/gpt-5.1", ...}`
- Frontend displays model names for readability
- This prevents bias while maintaining transparency

### Dynamic Model Configuration
- Chairman and Council models are stored in `app_settings` table
- Configurable via Admin Dashboard UI
- Fallback to `config.py` defaults if DB settings not found
- Changes take effect immediately (no restart needed)

### Error Handling Philosophy
- Continue with successful responses if some models fail
- Never fail the entire request due to single model failure
- Log errors internally, show generic messages to users
- **Failed models are transparent**: Users see a warning banner ("X of Y models failed") and greyed-out tabs for failed models in Stage 1/2
- Failed model lists stored in `metadata.stage1_failed` / `metadata.stage2_failed` (JSONB, no schema change needed)

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`). Run backend as `python -m backend.main` from project root.

### Dependencies
- `pydantic[email]` - Required for EmailStr validation
- `passlib[bcrypt]` - Required for password hashing
- `slowapi` - Required for rate limiting
- `supabase` - Required for database access

## Common Gotchas

1. **Module Import Errors**: Run `python -m backend.main` from project root
2. **CORS Issues**: Set `CORS_ORIGINS` environment variable for production
3. **Email Validation Error**: Ensure `pydantic[email]` is installed
4. **Password Hashing**: Old SHA-256 hashes are incompatible with bcrypt
5. **JWT_SECRET missing**: Backend won't start - generate with `openssl rand -base64 32`
6. **slowapi Request-Parameter**: Rate-limited endpoints must have `request: Request` as first param, Pydantic body as `body: ModelName`
7. **Supabase env vars missing**: Backend won't start without `SUPABASE_URL` and `SUPABASE_KEY`
8. **Schema must be applied first**: Run `backend/schema.sql` in Supabase SQL Editor before first start

## Data Flow Summary

```
User Query
    ↓
Stage 1: Parallel queries → [individual responses] + [failed_models]
    ↓
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings] + [failed_models]
    ↓
Aggregate Rankings Calculation → [sorted by avg position]
    ↓
Stage 3: Chairman synthesis with full context
    ↓
Return: {stage1, stage2, stage3, metadata (incl. stage1_failed, stage2_failed)}
    ↓
Frontend: Display with tabs + warning banners for failed models
```

## Files Overview

```
llm-council/
├── backend/
│   ├── __init__.py
│   ├── api_keys.py      # API key management (public REST API)
│   ├── auth.py          # JWT authentication
│   ├── config.py        # Configuration & env vars
│   ├── council.py       # 3-stage logic (dynamic models)
│   ├── database.py      # Supabase client
│   ├── main.py          # FastAPI app + admin settings + public API endpoints
│   ├── openrouter.py    # LLM API client
│   ├── schema.sql       # Database schema (run in Supabase)
│   ├── settings.py      # App settings CRUD
│   ├── storage.py       # Conversation storage (Supabase)
│   └── user_storage.py  # User storage (Supabase + bcrypt)
├── frontend/
│   ├── src/
│   │   ├── api.js       # API client (+ admin methods)
│   │   ├── auth.jsx     # Auth context
│   │   ├── App.jsx      # Main app (+ admin view toggle)
│   │   ├── App.css      # Main styles
│   │   ├── index.css    # CSS variables
│   │   └── components/
│   │       ├── AdminDashboard.jsx  # Admin UI
│   │       ├── AdminDashboard.css  # Admin styles
│   │       └── Login.jsx           # Login/Register
│   └── index.html
├── CLAUDE.md            # This file
├── CHANGELOG.md         # Development history
└── pyproject.toml       # Python dependencies
```

## Next Steps

- [x] Rate Limiting
- [x] Migration to database (Supabase)
- [x] Admin UI for model configuration
- [x] Failed models transparency (warning banners + greyed-out tabs)
- [x] Public REST API (`/api/v1/council`) with API key authentication
- [x] Admin UI for API key management
- [ ] Password reset via email
- [ ] Token refresh mechanism
- [ ] Unit Tests
