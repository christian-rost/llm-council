# XQT5 5AIs - Entwicklungsstand

## Version 0.2.0 (Branch: version02)

### Sicherheits-Fixes

- ✅ **JWT Secret Pflicht**: Wirft RuntimeError wenn `JWT_SECRET` nicht gesetzt
- ✅ **Admin-Check verbessert**: Verwendet `is_admin`-Flag statt Username-Vergleich
- ✅ **UUID für User-IDs**: `uuid.uuid4()` statt Timestamp (verhindert Kollisionen)
- ✅ **Rate-Limiting**: slowapi integriert
  - Login: 5 Versuche/Minute
  - Register: 3 Versuche/Minute
  - Message: 10 Anfragen/Minute
- ✅ **Health-Endpoint bereinigt**: Keine Admin-Config-Info mehr exponiert
- ✅ **datetime.utcnow() ersetzt**: Verwendet `datetime.now(timezone.utc)` (nicht mehr deprecated)

### Abhängigkeiten

- Neu: `slowapi>=0.1.9`

---

## Version 0.1.0 (Branch: version01)

### Überblick

XQT5 5AIs ist ein 3-stufiges KI-Beratungssystem, bei dem mehrere LLMs gemeinsam Fragen beantworten. Die Innovation liegt in der anonymisierten Peer-Review in Stage 2, um Voreingenommenheit zu vermeiden.

### Architektur

- **Backend**: Python/FastAPI (Port 8001)
- **Frontend**: React/Vite
- **API**: OpenRouter für LLM-Anfragen
- **Authentifizierung**: JWT-basiert
- **Speicherung**: JSON-Dateien

### Aktuelle Features

#### Authentifizierung
- Benutzerregistrierung mit Validierung (Username 3-32 Zeichen, E-Mail, Passwort min. 8 Zeichen)
- Login für registrierte Benutzer und Admin
- JWT-Token-basierte Authentifizierung
- Admin-Bereich für Benutzerverwaltung

#### 3-Stufen-Prozess
1. **Stage 1**: Parallele Anfragen an alle Council-Modelle
2. **Stage 2**: Anonymisierte Peer-Rankings
3. **Stage 3**: Chairman synthetisiert finale Antwort

#### PDF-Unterstützung
- PDF-Upload und -Analyse durch OpenRouter
- Native PDF-Verarbeitung

### Sicherheitsverbesserungen (version01)

- ✅ Bcrypt-Passwort-Hashing (ersetzt SHA-256)
- ✅ Input-Validierung bei Registrierung
- ✅ CORS auf spezifische Methoden/Header beschränkt
- ✅ CORS-Origins über Umgebungsvariable konfigurierbar
- ✅ Fehlerbehandlung bei Dateioperationen
- ✅ Logging statt print-Statements
- ✅ Interne Fehlerdetails nicht an Client exponiert
- ✅ Duplicate main.py entfernt

### Design

- Farbschema basierend auf XQT5 Corporate Design
- **Primärfarbe**: #ee7f00 (Orange)
- **Dunkel**: #213452 (Navy-Blau)
- **Hell**: #ffffff (Weiß)

### Konfiguration

#### Backend Umgebungsvariablen

| Variable | Beschreibung | Beispiel |
|----------|--------------|----------|
| `OPENROUTER_API_KEY` | API-Key für OpenRouter | `sk-or-...` |
| `JWT_SECRET` | Secret für JWT-Token | `your-secret-key` |
| `admin_user` | Admin-Benutzername | `admin` |
| `admin_pw` | Admin-Passwort | `secure-password` |
| `CORS_ORIGINS` | Erlaubte Origins (kommasepariert) | `https://5ais.xqtfive.com` |

#### Frontend Umgebungsvariablen

| Variable | Beschreibung | Beispiel |
|----------|--------------|----------|
| `VITE_API_BASE` | Backend-URL | `https://api.example.com` |

### Council-Modelle (Standard)

- OpenAI GPT-5.1
- Google Gemini 3 Pro Preview
- Anthropic Claude Sonnet 4.5
- xAI Grok 4

**Chairman**: Google Gemini 3 Pro Preview

### Deployment

Das Projekt wird über Coolify auf einem VPS deployed:
- Frontend: https://5ais.xqtfive.com
- Backend: Separate Coolify-Instanz

### Bekannte Einschränkungen

- Keine Rate-Limiting-Implementierung
- Keine Passwort-Zurücksetzen-Funktion für Benutzer (nur Admin)
- Metadaten werden nicht persistent gespeichert
- Kein automatisches Token-Refresh

### Nächste Schritte

- [ ] Rate Limiting implementieren
- [ ] Passwort-Zurücksetzen per E-Mail
- [ ] Token-Refresh-Mechanismus
- [ ] Unit Tests hinzufügen
- [ ] Datenbank statt JSON-Dateien
