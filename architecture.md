# Architecture

High-level system design for the AI-guided learning platform. This document captures services, data flow, and key application flows.

## Services (logical)

| Service | Responsibility |
|---------|----------------|
| **Web client** | Learner UI — test taking, score view, error analysis, recommendations |
| **Admin dashboard** | Internal UI — manage questions, tags, users, content |
| **API / backend** | Core REST/GraphQL service — auth, attempts, scoring, persistence |
| **Tagging service** | Maintains question tag taxonomy; serves tag-based queries |
| **AI analysis service** | Consumes attempt + error data, produces explanations and recommendations |
| **Database** | Stores users, questions, tags, attempts, answers, error logs |
| **Object storage** | Stores large artifacts (e.g. raw error logs, generated reports) |

## High-level system diagram

```mermaid
flowchart LR
    Learner([Learner])
    Admin([Admin])

    subgraph Frontend
        WebUI[Web Client]
        AdminUI[Admin Dashboard]
    end

    subgraph Backend
        API[API Service]
        Tagging[Tagging Service]
        AIAnalysis[AI Analysis Service]
    end

    subgraph Data
        DB[(Database)]
        Blob[(Object Storage)]
    end

    LLM[(LLM Provider)]

    Learner --> WebUI
    Admin --> AdminUI
    WebUI --> API
    AdminUI --> API
    API --> DB
    API --> Tagging
    API --> AIAnalysis
    Tagging --> DB
    AIAnalysis --> DB
    AIAnalysis --> Blob
    AIAnalysis --> LLM
```

## Data model (core entities)

```mermaid
erDiagram
    USER ||--o{ ATTEMPT : takes
    TEST ||--o{ ATTEMPT : "is taken in"
    TEST ||--o{ QUESTION : contains
    QUESTION ||--o{ ANSWER : "is answered by"
    ATTEMPT ||--o{ ANSWER : produces
    ANSWER ||--o| ERROR_LOG : "may produce"
    QUESTION }o--o{ TAG : "tagged with"
    ATTEMPT ||--o| ANALYSIS : "has"

    USER {
        id string
        role enum
    }
    TEST {
        id string
        title string
    }
    QUESTION {
        id string
        body text
        correct_answer string
    }
    TAG {
        id string
        name string
        category string
    }
    ATTEMPT {
        id string
        user_id string
        test_id string
        score number
        completed_at timestamp
    }
    ANSWER {
        id string
        attempt_id string
        question_id string
        chosen string
        is_correct bool
    }
    ERROR_LOG {
        id string
        answer_id string
        category string
        notes text
    }
    ANALYSIS {
        id string
        attempt_id string
        summary text
        recommendations json
    }
```

## Application flow — Learner taking a test

```mermaid
sequenceDiagram
    actor L as Learner
    participant W as Web Client
    participant A as API
    participant DB as Database
    participant AI as AI Analysis
    participant LLM

    L->>W: Start test
    W->>A: GET /tests/:id
    A->>DB: Load test + questions
    DB-->>A: Test payload
    A-->>W: Test
    L->>W: Submit answers
    W->>A: POST /attempts
    A->>DB: Persist attempt + answers
    A->>A: Score attempt
    A->>DB: Write error logs (wrong answers)
    A->>AI: Trigger analysis(attempt_id)
    AI->>DB: Load attempt, errors, tags
    AI->>LLM: Generate explanations + recommendations
    LLM-->>AI: Analysis text
    AI->>DB: Persist analysis
    A-->>W: Score + attempt id
    W->>A: GET /attempts/:id/analysis
    A->>DB: Load analysis
    A-->>W: Analysis + recommendations
    W-->>L: Show results, error breakdown, study plan
```

## Application flow — Admin managing questions and tags

```mermaid
sequenceDiagram
    actor Adm as Admin
    participant U as Admin Dashboard
    participant A as API
    participant T as Tagging Service
    participant DB as Database

    Adm->>U: Open question editor
    U->>A: GET /admin/questions
    A->>DB: List questions
    DB-->>A: Questions
    A-->>U: Render list
    Adm->>U: Edit question + assign tags
    U->>A: PUT /admin/questions/:id
    A->>DB: Update question
    A->>T: Sync tag assignments
    T->>DB: Upsert question_tags
    T-->>A: OK
    A-->>U: Updated
```

## Cross-cutting concerns
- **Auth** — role-based (learner vs admin) on all API routes.
- **Async work** — AI analysis runs out of band so submission feels instant; client polls or subscribes for results.
- **Observability** — structured logs and metrics on attempts, AI latency, tagging coverage.
- **Idempotency** — attempt submission and analysis triggers must be idempotent on retry.

## Open architecture questions
- Sync vs async analysis trigger (queue vs direct call).
- Single backend service vs separate AI service from day one.
- Tag taxonomy: free-form tags vs curated controlled vocabulary.
- LLM provider choice and prompt-cache strategy for cost control.
