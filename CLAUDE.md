# CLAUDE.md - Technical Notes for XQT5 5AIs

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Current State

- **Branch**: `version02` (aktive Entwicklung)
- **Produktname**: XQT5 5AIs (umbenannt von "LLM Council")
- **Deployment**: Coolify auf VPS
  - Frontend: https://5ais.xqtfive.com
  - Backend: Separate Instanz

## Project Overview

XQT5 5AIs is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Contains `COUNCIL_MODELS` (list of OpenRouter model identifiers)
- Contains `CHAIRMAN_MODEL` (model that synthesizes final answer)
- Uses environment variable `OPENROUTER_API_KEY` from `.env`
- Backend runs on **port 8001**
- JWT configuration: `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRATION_HOURS`
- Admin credentials: `admin_user`, `admin_pw` (environment variables)

**`user_storage.py`**
- JSON-based user storage in `data/users/`
- **Bcrypt password hashing** via passlib (NOT SHA-256)
- User CRUD operations with error handling
- Functions: `create_user()`, `get_user_by_username()`, `get_user_by_email()`, `verify_password()`

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
- `stage1_collect_responses()`: Parallel queries to all council models
- `stage2_collect_rankings()`: Anonymized peer rankings
- `stage3_synthesize_final()`: Chairman synthesizes final answer
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section
- `calculate_aggregate_rankings()`: Computes average rank position

**`storage.py`**
- JSON-based conversation storage in `data/conversations/`
- Each conversation: `{id, user_id, created_at, title, messages[]}`
- User isolation: Users can only see their own conversations

**`main.py`**
- FastAPI app with CORS middleware
- **CORS origins configurable via `CORS_ORIGINS` environment variable**
- Authentication endpoints: `/api/auth/register`, `/api/auth/login`, `/api/auth/me`
- Admin endpoints: `/api/admin/users`, `/api/admin/users/{id}`, etc.
- Input validation on registration (username 3-32 chars, EmailStr, password min 8 chars)
- Internal errors not exposed to clients

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Main orchestration: manages conversations list and current conversation
- Handles authentication state
- PDF upload support

**`auth.jsx`**
- Authentication context provider
- Token management in localStorage
- Login/logout/register functions

**`components/Login.jsx`**
- Login and registration forms
- Tab-based UI for switching between login/register

**`components/ChatInterface.jsx`**
- Multiline textarea (3 rows, resizable)
- Enter to send, Shift+Enter for new line

**`components/Stage1.jsx`**, **`Stage2.jsx`**, **`Stage3.jsx`**
- Tab views for individual model responses
- ReactMarkdown rendering

**Styling (`*.css`)**
- **XQT5 Corporate Design**:
  - Primary color: `#ee7f00` (Orange)
  - Dark color: `#213452` (Navy-Blau)
  - White: `#ffffff`
- CSS Variables in `index.css` für konsistentes Theming
- Light mode theme

## Environment Variables

### Backend

| Variable | Beschreibung | Pflicht |
|----------|--------------|---------|
| `OPENROUTER_API_KEY` | API-Key für OpenRouter | Ja |
| `JWT_SECRET` | Secret für JWT-Token | Ja (Production) |
| `admin_user` | Admin-Benutzername | Ja |
| `admin_pw` | Admin-Passwort | Ja |
| `CORS_ORIGINS` | Erlaubte Origins (kommasepariert) | Nein (Default: localhost) |

### Frontend

| Variable | Beschreibung | Pflicht |
|----------|--------------|---------|
| `VITE_API_BASE` | Backend-URL | Ja (Production) |

## Security Features (version02)

1. **Bcrypt Password Hashing**: Ersetzt SHA-256, nutzt passlib
2. **Input Validation**: Pydantic validators für Registration
3. **CORS Restriction**: Nur spezifische Methods/Headers erlaubt
4. **Error Handling**: Interne Fehler nicht an Client exponiert
5. **Logging**: Proper logging statt print statements
6. **User Isolation**: Benutzer sehen nur eigene Conversations
7. **JWT Secret Pflicht**: RuntimeError wenn `JWT_SECRET` nicht gesetzt
8. **Sichere Admin-Prüfung**: `is_admin`-Flag statt Username-Vergleich
9. **UUID User-IDs**: Keine Timestamp-Kollisionen mehr möglich
10. **Rate-Limiting**: slowapi für Brute-Force- und DoS-Schutz

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

### Error Handling Philosophy
- Continue with successful responses if some models fail
- Never fail the entire request due to single model failure
- Log errors internally, show generic messages to users

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`). Run backend as `python -m backend.main` from project root.

### Dependencies
- `pydantic[email]` - Required for EmailStr validation
- `passlib[bcrypt]` - Required for password hashing

## Common Gotchas

1. **Module Import Errors**: Run `python -m backend.main` from project root
2. **CORS Issues**: Set `CORS_ORIGINS` environment variable for production
3. **Email Validation Error**: Ensure `pydantic[email]` is installed
4. **Password Hashing**: Old SHA-256 hashes are incompatible with bcrypt

## Data Flow Summary

```
User Query
    ↓
Stage 1: Parallel queries → [individual responses]
    ↓
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings]
    ↓
Aggregate Rankings Calculation → [sorted by avg position]
    ↓
Stage 3: Chairman synthesis with full context
    ↓
Return: {stage1, stage2, stage3, metadata}
    ↓
Frontend: Display with tabs + validation UI
```

## Files Overview

```
llm-council/
├── backend/
│   ├── __init__.py
│   ├── auth.py          # JWT authentication
│   ├── config.py        # Configuration & env vars
│   ├── council.py       # 3-stage logic
│   ├── main.py          # FastAPI app
│   ├── openrouter.py    # LLM API client
│   ├── storage.py       # Conversation storage
│   └── user_storage.py  # User storage (bcrypt)
├── frontend/
│   ├── src/
│   │   ├── api.js       # API client
│   │   ├── auth.jsx     # Auth context
│   │   ├── App.jsx      # Main app
│   │   ├── App.css      # Main styles
│   │   ├── index.css    # CSS variables
│   │   └── components/
│   └── index.html
├── CLAUDE.md            # Diese Datei
├── CHANGELOG.md         # Entwicklungsstand
└── pyproject.toml       # Python dependencies
```

## Nächste Schritte

- [x] Rate Limiting implementieren
- [ ] Passwort-Zurücksetzen per E-Mail
- [ ] Token-Refresh-Mechanismus
- [ ] Unit Tests
- [ ] Migration zu Datenbank
