# XQT5AIs - Architekturdiagramme

## 1. System-Architektur

```mermaid
flowchart TB
    subgraph Client["Client (Browser)"]
        FE["Frontend<br/>React + Vite"]
    end

    subgraph Server["VPS (Coolify)"]
        BE["Backend<br/>FastAPI :8001"]

        subgraph Storage["JSON Storage"]
            US["data/users/"]
            CS["data/conversations/"]
        end
    end

    subgraph External["Externe Services"]
        OR["OpenRouter API"]
        subgraph LLMs["LLM Models"]
            M1["GPT-4o"]
            M2["Claude 3.5"]
            M3["Gemini Pro"]
            M4["...weitere"]
        end
    end

    FE <-->|"REST API<br/>JWT Auth"| BE
    BE -->|"Parallel Queries"| OR
    OR --> LLMs
    BE <--> Storage
```

## 2. 3-Stufen-Deliberation-Prozess

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant OR as OpenRouter
    participant LLMs as Council Models
    participant CH as Chairman Model

    U->>FE: Frage stellen
    FE->>BE: POST /conversations/{id}/message

    rect rgb(240, 248, 255)
        Note over BE,LLMs: Stage 1: Individuelle Antworten sammeln
        BE->>+OR: Parallele Anfragen
        OR->>LLMs: Query an alle Models
        LLMs-->>OR: Individuelle Responses
        OR-->>-BE: Responses Array
    end

    rect rgb(255, 248, 240)
        Note over BE,LLMs: Stage 2: Anonymisierte Peer-Bewertung
        BE->>BE: Anonymisieren (Response A, B, C...)
        BE->>+OR: Parallele Ranking-Anfragen
        OR->>LLMs: "Bewerte Response A, B, C..."
        LLMs-->>OR: Rankings + Begründungen
        OR-->>-BE: Evaluations Array
        BE->>BE: parse_ranking_from_text()
        BE->>BE: calculate_aggregate_rankings()
    end

    rect rgb(240, 255, 240)
        Note over BE,CH: Stage 3: Chairman-Synthese
        BE->>+OR: Synthese-Anfrage
        OR->>CH: Kontext + Rankings
        CH-->>OR: Finale Antwort
        OR-->>-BE: Synthese
    end

    BE-->>FE: {stage1, stage2, stage3, metadata}
    FE-->>U: Tabs mit allen Stufen anzeigen
```

## 3. Authentifizierungs-Flow

```mermaid
flowchart TD
    subgraph Registration["Registrierung"]
        R1["/api/auth/register"] --> R2{"Input<br/>Validation"}
        R2 -->|"Invalid"| R3["400 Error"]
        R2 -->|"Valid"| R4["Bcrypt Hash"]
        R4 --> R5["User speichern<br/>(UUID generieren)"]
        R5 --> R6["JWT Token erstellen"]
        R6 --> R7["Token zurückgeben"]
    end

    subgraph Login["Login"]
        L1["/api/auth/login"] --> L2{"Rate Limit<br/>5/min"}
        L2 -->|"Exceeded"| L3["429 Too Many<br/>Requests"]
        L2 -->|"OK"| L4["User laden"]
        L4 --> L5{"Bcrypt<br/>verify"}
        L5 -->|"Invalid"| L6["401 Unauthorized"]
        L5 -->|"Valid"| L7["JWT Token erstellen"]
        L7 --> L8["Token zurückgeben"]
    end

    subgraph Protected["Geschützte Routen"]
        P1["Request mit<br/>Bearer Token"] --> P2["get_current_user()"]
        P2 --> P3{"Token<br/>valid?"}
        P3 -->|"No"| P4["401 Unauthorized"]
        P3 -->|"Yes"| P5{"Admin<br/>Route?"}
        P5 -->|"Yes"| P6["is_admin_user()"]
        P5 -->|"No"| P7["Request verarbeiten"]
        P6 -->|"Not Admin"| P8["403 Forbidden"]
        P6 -->|"Admin"| P7
    end
```

## 4. Backend-Modulstruktur

```mermaid
classDiagram
    direction LR

    class main {
        +FastAPI app
        +CORS middleware
        +auth_routes()
        +admin_routes()
        +conversation_routes()
    }

    class config {
        +COUNCIL_MODELS: list
        +CHAIRMAN_MODEL: str
        +JWT_SECRET: str
        +JWT_ALGORITHM: str
        +admin_user: str
        +admin_pw: str
    }

    class auth {
        +create_access_token()
        +get_current_user()
        +get_current_admin()
        +is_admin_user()
    }

    class council {
        +stage1_collect_responses()
        +stage2_collect_rankings()
        +stage3_synthesize_final()
        +parse_ranking_from_text()
        +calculate_aggregate_rankings()
    }

    class openrouter {
        +query_model()
        +query_models_parallel()
    }

    class storage {
        +save_conversation()
        +load_conversation()
        +list_conversations()
        +delete_conversation()
    }

    class user_storage {
        +create_user()
        +get_user_by_username()
        +get_user_by_email()
        +verify_password()
    }

    main --> config : uses
    main --> auth : uses
    main --> council : uses
    main --> storage : uses
    main --> user_storage : uses
    auth --> config : reads JWT config
    auth --> user_storage : verifies users
    council --> openrouter : queries LLMs
    openrouter --> config : reads API key
```

## 5. Datenfluss-Übersicht

```mermaid
flowchart LR
    subgraph Input
        Q["User Query"]
        PDF["PDF Upload<br/>(optional)"]
    end

    subgraph Stage1["Stage 1"]
        S1["Parallel<br/>Queries"]
        R1["Response 1"]
        R2["Response 2"]
        R3["Response 3"]
        R4["Response n"]
        S1 --> R1 & R2 & R3 & R4
    end

    subgraph Stage2["Stage 2"]
        AN["Anonymisierung<br/>A, B, C, D..."]
        EV["Peer<br/>Evaluations"]
        RK["Rankings<br/>parsen"]
        AG["Aggregierte<br/>Rankings"]
        AN --> EV --> RK --> AG
    end

    subgraph Stage3["Stage 3"]
        SY["Chairman<br/>Synthese"]
        FA["Finale<br/>Antwort"]
        SY --> FA
    end

    subgraph Output
        RS["Response<br/>Object"]
        UI["Frontend<br/>Tabs"]
    end

    Q --> S1
    PDF -.-> S1
    R1 & R2 & R3 & R4 --> AN
    AG --> SY
    FA --> RS --> UI
```

## 6. Frontend-Komponenten

```mermaid
flowchart TB
    subgraph App["App.jsx"]
        AS["Auth State"]
        CS["Conversations State"]
        CC["Current Conversation"]
    end

    subgraph Auth["Authentifizierung"]
        AC["AuthContext<br/>(auth.jsx)"]
        LO["Login.jsx"]
    end

    subgraph Chat["Chat-Bereich"]
        CI["ChatInterface.jsx"]
        ML["Message List"]
        TI["Text Input"]
        PU["PDF Upload"]
    end

    subgraph Stages["Stage-Ansichten"]
        S1["Stage1.jsx<br/>Individuelle Antworten"]
        S2["Stage2.jsx<br/>Peer Rankings"]
        S3["Stage3.jsx<br/>Chairman Synthese"]
    end

    subgraph Sidebar["Sidebar"]
        CL["Conversation List"]
        NC["New Conversation"]
        LB["Logout Button"]
    end

    App --> Auth
    App --> Chat
    App --> Sidebar
    AC --> AS
    CI --> ML & TI & PU
    ML --> S1 & S2 & S3
```

## 7. Rate-Limiting-Übersicht

```mermaid
flowchart TD
    subgraph Endpoints["Rate-Limited Endpoints"]
        E1["/api/auth/login<br/>5 req/min"]
        E2["/api/auth/register<br/>3 req/min"]
        E3["/api/conversations/{id}/message<br/>10 req/min"]
        E4["/api/conversations/{id}/message/stream<br/>10 req/min"]
    end

    subgraph slowapi["slowapi Middleware"]
        RL["RateLimiter"]
        IP["IP-basiert"]
    end

    REQ["Incoming Request"] --> RL
    RL --> IP
    IP -->|"Limit OK"| PROC["Request verarbeiten"]
    IP -->|"Limit exceeded"| ERR["429 Too Many Requests"]

    PROC --> E1 & E2 & E3 & E4
```

## 8. Deployment-Architektur

```mermaid
flowchart TB
    subgraph Internet
        USER["Benutzer"]
    end

    subgraph Coolify["Coolify VPS"]
        subgraph FrontendContainer["Frontend Container"]
            NGINX["Nginx"]
            VITE["Vite Build"]
        end

        subgraph BackendContainer["Backend Container"]
            UV["Uvicorn"]
            FAST["FastAPI"]
        end

        subgraph Data["Persistente Daten"]
            VOL1["Volume: users/"]
            VOL2["Volume: conversations/"]
        end
    end

    subgraph External["Externe APIs"]
        OPENR["OpenRouter"]
    end

    USER -->|"HTTPS"| NGINX
    NGINX -->|"Static Files"| VITE
    NGINX -->|"API Proxy"| UV
    UV --> FAST
    FAST <--> VOL1 & VOL2
    FAST -->|"HTTPS"| OPENR
```
