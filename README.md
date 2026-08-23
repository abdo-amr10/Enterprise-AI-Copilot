# Enterprise AI Copilot

> **On-Premise Natural Language-to-SQL Assistant**

Enterprise AI Copilot is an intelligent, privacy-first enterprise assistant that allows users to ask questions about enterprise data using **natural language** and receive accurate, human-readable insights without directly writing SQL queries.

The system is designed to operate **entirely within the organization's local environment**, ensuring that sensitive corporate data does not leave the organization's infrastructure.

---

## 📌 Overview

In complex enterprise systems, employees and clients often need to navigate complicated interfaces or depend on technical teams to retrieve specific information from databases.

Enterprise AI Copilot addresses this problem by providing a conversational interface where users can ask questions naturally.

For example:

> "Show me the latest updates for this client."

The system understands the user's intent, translates the request into a secure SQL query, executes it against the authorized enterprise data, and converts the results into a clear human-readable response.

The proposed solution combines:

* Local Large Language Models (LLMs)
* Natural Language Processing
* Secure Text-to-SQL generation
* .NET backend orchestration
* SQL Server
* Row-Level Security (RLS)
* React conversational interface

---

## 🎯 Project Goals

The main goals of Enterprise AI Copilot are:

* Enable users to query enterprise data using natural language.
* Eliminate the need for users to manually write SQL queries.
* Keep sensitive enterprise data inside the organization's infrastructure.
* Generate secure, read-only SQL queries.
* Enforce authentication and Row-Level Security.
* Automatically detect and correct SQL syntax errors.
* Convert raw database results into understandable reports.
* Provide a seamless AI chat experience inside the enterprise system.

---

## 🔐 Privacy & Security

Security and privacy are core principles of the system.

Unlike cloud-based AI solutions, the proposed Copilot operates completely **on-premises**.

This means sensitive enterprise data remains within the local environment and does not need to be sent to external cloud AI services.

The backend acts as a strict security gateway between the AI layer and SQL Server.

It is responsible for:

* Authentication
* Authorization
* Row-Level Security
* SQL validation and execution
* Controlled database access
* Read-only query execution

The project proposal specifically defines Row-Level Security to ensure that users can access only the data they are authorized to access.

---

# 🏗️ System Architecture

The system is organized around three main modules:

```text
┌─────────────────────────────────────────────┐
│              Enterprise Portal              │
│                                             │
│             React AI Chat UI                │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│              .NET Backend                   │
│           Secure Data Orchestrator          │
│                                             │
│  Authentication                             │
│  Authorization                               │
│  Row-Level Security                         │
│  SQL Validation                             │
│  Query Execution                            │
│  Self-Correction                            │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│             AI / Text-to-SQL Engine         │
│                                             │
│                Local LLM                    │
│                     │                       │
│              Semantic View Layer            │
│                     │                       │
│             Natural Language                │
│                     ↓                       │
│               Secure SQL                    │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│                SQL Server                   │
│                                             │
│        Enterprise Database                  │
└─────────────────────────────────────────────┘
```

The architecture described in the proposal places the local LLM behind a semantic view layer, while the .NET backend controls access to SQL Server and applies security policies before executing generated queries.

---

# 🧩 Core Modules

## Module A — Intent & Text-to-SQL Engine

The analytical core of the system.

This module:

1. Receives the user's natural-language question.
2. Understands the user's intent.
3. Uses a simplified representation of the database schema through the **Semantic View Layer**.
4. Generates a secure, read-only SQL query.
5. Passes the generated query to the backend for validation and execution.

Example:

```text
User:
"Show me the latest updates for this client."

                ↓

Natural Language Understanding

                ↓

Semantic View Layer

                ↓

Text-to-SQL

                ↓

Read-Only SQL Query
```

The proposal defines this module around a locally deployed LLM and a customized simplified schema representation.

---

## Module B — Secure Data Orchestrator

The backend gateway between the AI engine and SQL Server.

Built using **.NET**, this module is responsible for controlling database access.

Its responsibilities include:

* Receiving generated SQL.
* Authenticating the user.
* Applying authorization rules.
* Enforcing Row-Level Security.
* Executing the query.
* Returning raw JSON data.
* Detecting SQL syntax errors.
* Attempting automatic SQL correction.

```text
AI Generated SQL
       │
       ▼
┌──────────────────────┐
│ Secure Orchestrator  │
├──────────────────────┤
│ Authentication       │
│ Authorization        │
│ RLS                  │
│ SQL Validation       │
│ Execution            │
│ Self-Correction      │
└──────────┬───────────┘
           │
           ▼
       SQL Server
```

The backend is explicitly designed as the strict gateway between the AI and SQL Server.

---

## Module C — Dynamic Reporting Workspace

This module transforms raw database results into useful information for the user.

The workflow is:

```text
SQL Server
    │
    ▼
Raw Database Records
    │
    ▼
.NET Backend
    │
    ▼
Local LLM
    │
    ▼
Human-Readable Summary
    │
    ▼
React Interface
```

Instead of displaying raw database rows directly, the system sends the retrieved data back to the LLM with strict instructions to generate a clean and understandable summary.

The React frontend then displays the final report inside the enterprise portal.

---

# 🔄 End-to-End Workflow

A typical request follows this pipeline:

```text
User Question
      │
      ▼
React Chat Interface
      │
      ▼
.NET Backend
      │
      ▼
Intent Understanding
      │
      ▼
Semantic View Layer
      │
      ▼
Local LLM
      │
      ▼
Generated SQL
      │
      ▼
Security & Validation
      │
      ▼
Row-Level Security
      │
      ▼
SQL Server
      │
      ▼
Query Results
      │
      ▼
Local LLM
      │
      ▼
Human-Readable Response
      │
      ▼
React Chat Interface
```

---

# 🛠️ Technology Stack

| Layer        | Technology                          |
| ------------ | ----------------------------------- |
| AI / ML      | Local LLM                           |
| AI Pipeline  | Text-to-SQL                         |
| Backend      | .NET                                |
| Database     | SQL Server                          |
| Security     | Authentication + Row-Level Security |
| Frontend     | React                               |
| Architecture | On-Premise Enterprise Architecture  |

The project proposal identifies .NET for backend orchestration and SQL Server integration, React for the embedded interface, and local LLM infrastructure for the AI layer.

---

# 👥 Team Structure

The proposed squad consists of six students distributed across different engineering responsibilities:

### AI & Machine Learning — 2 Students

Responsible for:

* Local LLM configuration
* Prompting
* Text-to-SQL pipeline
* Semantic understanding
* AI operation without external cloud dependencies

### Backend Engineering — 2 Students

Responsible for:

* .NET backend
* API orchestration
* SQL Server integration
* Authentication
* Row-Level Security

### Frontend Development — 1 Student

Responsible for:

* React interface
* AI chat experience
* Enterprise portal integration

### Project Lead / QA — 1 Student

Responsible for:

* Scrum coordination
* System testing
* Edge-case handling
* SQL error scenarios
* Business requirements alignment

The team structure and responsibilities are defined in the project proposal.

---

# 🗺️ Project Roadmap

The project follows an agile delivery lifecycle across a full academic semester.

| Phase                                |    Duration | Main Objectives                                                              |
| ------------------------------------ | ----------: | ---------------------------------------------------------------------------- |
| Requirements & Architecture Setup    |   Weeks 1–3 | Define scope, design database views, setup local LLM and .NET infrastructure |
| Core Integration & AI Pipeline Build |   Weeks 4–8 | Develop Text-to-SQL, implement RLS, connect React interface                  |
| Testing & Self-Correction Refinement |  Weeks 9–11 | Test database edge cases, improve prompts, handle query errors               |
| Final Polish & Demo Day              | Weeks 12–14 | Documentation, bug fixing, and final demonstration                           |

This roadmap is specified in the project proposal on page 3.

---

# 🧪 Testing & Reliability

Testing focuses on making the AI pipeline reliable when interacting with enterprise databases.

Important testing areas include:

* SQL syntax errors
* Database edge cases
* Incorrect generated queries
* Prompt refinement
* Hallucination prevention
* Self-correction behavior
* Security and authorization
* Row-Level Security enforcement

The project roadmap dedicates Weeks 9–11 specifically to testing, self-correction refinement, prompt engineering, and query-error handling.

---

# 💡 Example Interaction

### User

```text
Show me the latest updates for this client.
```

### AI Pipeline

```text
Natural Language
       ↓
Intent Detection
       ↓
Semantic Schema
       ↓
Text-to-SQL
       ↓
Security Validation
       ↓
RLS Filtering
       ↓
SQL Server
       ↓
Query Results
       ↓
AI Summary
```

### Final Response

The user receives a clean conversational response instead of raw SQL/database output.

---

# 🚀 Why Enterprise AI Copilot?

Enterprise AI adoption introduces an important challenge:

> How can organizations use AI while keeping sensitive business data private?

Enterprise AI Copilot approaches this challenge through an **on-premise AI architecture**.

The system combines:

* AI-powered natural language interaction
* Enterprise database integration
* Secure backend orchestration
* Local LLM infrastructure
* Row-Level Security
* Conversational reporting

This creates an architecture focused not only on AI capabilities, but also on **enterprise privacy and controlled data access**.

---

# 🎓 Project Value

The project is designed to provide practical experience in:

* Full-stack development
* Enterprise backend architecture
* AI integration
* Local LLM deployment
* Natural Language-to-SQL
* Database security
* Row-Level Security
* React development
* SQL Server integration
* AI testing and prompt engineering

According to the proposal, the resulting architecture is intended to address real enterprise privacy concerns around AI adoption while providing a strong portfolio project demonstrating enterprise-grade AI and full-stack engineering.

---

# 📄 Project Documentation

This repository is intended to contain the technical documentation required to understand, develop, test, and deploy Enterprise AI Copilot.

Suggested documentation structure:

```text
documentation/
│
├── Architecture/
│   ├── System Architecture
│   ├── Component Diagram
│   ├── Sequence Diagrams
│   └── Data Flow
│
├── AI/
│   ├── Text-to-SQL
│   ├── Semantic View Layer
│   ├── Prompt Engineering
│   └── Self-Correction
│
├── Backend/
│   ├── API Documentation
│   ├── Authentication
│   ├── Authorization
│   └── Row-Level Security
│
├── Database/
│   ├── Database Design
│   ├── Semantic Views
│   └── SQL Server
│
├── Frontend/
│   └── React Interface
│
└── Testing/
    ├── Test Strategy
    ├── Test Cases
    └── Edge Cases
```

> The exact implementation structure should reflect the actual repository as development progresses.

---

# 🔒 Security Principles

The system follows several important principles:

* **On-Premise First**
* **Least Privilege**
* **Read-Only Database Access**
* **Authentication Before Data Access**
* **Row-Level Security**
* **Controlled AI-to-Database Communication**
* **Validation of AI-Generated SQL**
* **No unnecessary external cloud dependencies**

---

# 📈 Future Opportunities

The architecture can serve as a foundation for further enterprise AI capabilities.

Potential future directions include:

* More advanced enterprise analytics
* Additional database sources
* More sophisticated semantic models
* Expanded reporting capabilities
* Improved SQL self-correction
* More advanced authorization policies
* Additional enterprise workflows

---

# 👨‍💻 Project Status

**Development Status:** In Development 🚧

The project follows the academic-semester roadmap defined in the proposal, progressing from requirements and architecture through AI integration, testing, refinement, and final demonstration.

---

# 📜 License

License information will be added according to the project's final distribution and ownership requirements.

---

## Enterprise AI Copilot

**On-Premise Natural Language-to-SQL Assistant**

> Ask questions naturally.
> Query enterprise data securely.
> Keep sensitive data on-premise.

