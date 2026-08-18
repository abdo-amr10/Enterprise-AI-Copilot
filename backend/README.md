# Enterprise AI Copilot — Backend

## On-Premise Natural Language-to-SQL Assistant

The backend is the secure orchestration layer between the **React frontend**, **Local AI / LLM pipeline**, and **SQL Server enterprise database**.

Its primary responsibility is to ensure that AI-generated database operations are handled through a controlled, authenticated, authorized, and secure backend pipeline.

---

# 👥 Backend Team

The Backend Engineering team consists of:

| # | Member              | Role             |
| - | ------------------- | ---------------- |
| 1 | **Abdelrahman Amr** | Backend Engineer |
| 2 | **Ahmed Hossam**    | Backend Engineer |

Both developers are responsible for designing, implementing, testing, and maintaining the backend services and their integration with the AI and database layers.

---

#  Backend Mission

The backend is responsible for acting as the **strict gateway between the AI layer and SQL Server**.

```text
                    ┌─────────────────────┐
                    │     React Frontend  │
                    │      AI Chat UI     │
                    └──────────┬──────────┘
                               │
                               │ HTTP / HTTPS
                               ▼
              ┌─────────────────────────────────┐
              │          .NET Backend            │
              │                                 │
              │       Secure Orchestrator       │
              │                                 │
              │ Authentication                  │
              │ Authorization                   │
              │ Request Validation              │
              │ AI Orchestration                │
              │ SQL Validation                  │
              │ Row-Level Security              │
              │ Query Execution                 │
              │ Error Handling                  │
              │ Self-Correction                 │
              └───────────────┬─────────────────┘
                              │
                              │ Secure DB Access
                              ▼
                  ┌────────────────────────┐
                  │      SQL Server       │
                  │ Enterprise Database   │
                  └────────────────────────┘
```

The proposal explicitly defines the .NET backend as the gateway responsible for authentication, Row-Level Security, query execution, JSON retrieval, and SQL self-correction.

---
#  Backend Layers

## 1. Domain Layer

The Domain layer contains the core business concepts of the system.

It should not depend on:

* ASP.NET Core
* Entity Framework Core
* SQL Server
* AI providers
* External infrastructure

Example responsibilities:

```text
Domain
│
├── Entities
├── Enums
├── Value Objects
├── Domain Rules
└── Common Abstractions
```
# 2. Application Layer

The Application layer contains the system's use cases and application business logic.

It coordinates operations without knowing the concrete infrastructure implementation.

Examples:

```text
Application
│
├── Authentication
├── Chat
├── AI
├── Query Generation
├── Query Validation
├── Query Execution
├── Reporting
└── Authorization
```
# 3. Infrastructure Layer

Infrastructure contains implementations that communicate with external systems.

Main responsibilities include:

* SQL Server
* Entity Framework Core
* ASP.NET Identity
* Authentication infrastructure
* AI/LLM integration
* Database access
* Security services
* External infrastructure dependencies
---
# 4. API Layer

The API layer exposes the backend functionality to the frontend and other authorized clients.

Responsibilities:

* HTTP endpoints
* Request validation
* Authentication
* Authorization
* DTO mapping
* Exception handling
* Middleware
* API response formatting
---
# Core Backend Flow

The most important backend workflow is the AI-to-database pipeline.

```text
User
 │
 │ Natural Language Question
 ▼
React Frontend
 │
 ▼
.NET API
 │
 ├── Authentication
 │
 ├── Authorization
 │
 └── Request Validation
 │
 ▼
AI / Text-to-SQL Service
 │
 ▼
Generated SQL
 │
 ▼
SQL Validation
 │
 ▼
Security / RLS
 │
 ▼
SQL Server
 │
 ▼
Raw JSON Result
 │
 ▼
AI Reporting / Summarization
 │
 ▼
.NET API
 │
 ▼
React Frontend
```

This reflects the project proposal's intended architecture: natural-language input is translated into SQL, the .NET backend controls execution and security, and the retrieved records can then be converted into a human-readable report.

---

#  Authentication

Authentication establishes the identity of the user making the request.

The backend must know:

```text
Who is the user?
        │
        ▼
What role does the user have?
        │
        ▼
What data is the user allowed to access?
```

Authentication should be performed before protected operations are executed.

Example conceptual request:

```http
Authorization: Bearer <JWT>
```

The authenticated user's identity should then be available to the application through the current-user abstraction.
---

# Authorization

Authentication answers:

> "Who are you?"

Authorization answers:

> "What are you allowed to do?"

The backend should enforce authorization before allowing access to protected resources.

Authorization may depend on:

* User identity
* User role
* Permissions
* Requested resource
* Data ownership
* Row-Level Security policies
---
