# Synthetic Banking Semantic Layer — Clean Architecture

This project contains the semantic-layer artifacts and the application/infrastructure code developed for the Synthetic Banking Text-to-SQL system.

## Current Progress

The project currently covers:

* Schema loading and normalization
* Schema relationships
* Semantic-layer artifact preparation
* Initial semantic draft generation
* Runtime semantic configuration
* LLM integration
* Clean Architecture separation between application and infrastructure

The semantic retrieval, vector-index construction, and final query-time integration are planned as the next stage.

---

# Architecture

```text
Dataset
   |
   v
SchemaLoader
   |
   v
Normalized Schema
   |
   +--------------------+
   |                    |
   v                    v
Relationships      Semantic Artifacts
                         |
                         v
                  initial_draft.json
                         |
                         v
                 Semantic Layer
                    (in progress)

User Question
      |
      v
Application Layer
      |
      v
LLM Integration
      |
      v
Local LLM
```

---

# Clean Architecture

The project follows Clean Architecture principles.

The main layers are:

```text
src/
├── domain/
├── application/
├── infrastructure/
└── config/
```

## Domain Layer

Contains the core semantic-layer concepts and domain-level abstractions.

The domain layer does not depend on infrastructure implementations.

---

## Application Layer

Contains application use cases and services.

Application components depend on abstractions/interfaces rather than directly depending on infrastructure implementations.

Examples include:

* Semantic-layer application services
* LLM generation request/response handling
* Application DTOs
* Repository ports/interfaces

---

## Infrastructure Layer

Contains implementations that interact with external systems and files.

Examples include:

* Schema loading
* Semantic-layer file loading
* LLM/Ollama integration
* Embedding-related infrastructure
* File-based persistence

Infrastructure implementations are kept separate from application business logic.

---

# Semantic Layer

The semantic layer is designed to provide the LLM with meaningful information about the database instead of exposing the entire raw database schema directly at query time.

It can contain information such as:

* Tables
* Columns
* Data types
* Relationships
* Documentation
* Business meanings
* Business glossary
* Semantic metadata

The semantic artifacts are treated as data rather than hard-coded business logic.

---

# Schema Loading

The schema-loading phase is responsible for reading the database schema and converting it into a normalized representation.

The `SchemaLoader` is responsible for:

1. Loading the schema artifact.
2. Validating the expected structure.
3. Normalizing the schema representation.
4. Making the normalized schema available to the semantic-layer preparation process.

Raw schema access belongs to the semantic-layer preparation/build phase and is not intended to be part of the query-time retrieval path.

---

# Schema Relationships

Database relationships are represented separately so that the semantic layer can understand how entities are connected.

Relationships can be used to identify:

* Foreign-key relationships
* Parent/child relationships
* Join paths
* Connected entities

This information is important for Text-to-SQL generation because the LLM needs to understand which tables can be joined and how they are related.

---

# Semantic Artifacts

The semantic-layer preparation process produces structured artifacts containing the information required to describe the database semantically.

The current workflow reaches the initial semantic draft:

```text
Raw Schema
    |
    v
Schema Loading
    |
    v
Schema Normalization
    |
    v
Relationships
    |
    v
Semantic Artifact Preparation
    |
    v
initial_draft.json
```

`initial_draft.json` represents the current prepared semantic draft before the remaining semantic-layer build and retrieval stages.

---

# Semantic Settings

Runtime configuration for semantic retrieval and indexing is kept outside the application business logic.

Example:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticSettings:
    default_top_k: int = 8
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_index_filename: str = "semantic_index.npz"
```

The configuration defines values such as:

* Default number of retrieved semantic results
* Embedding model
* Vector-index filename

Keeping these values in configuration prevents infrastructure/runtime settings from being hard-coded into application logic.

---

# LLM Integration

The local LLM is integrated as a separate infrastructure component.

The integration is responsible for communicating with the local model runtime and generating responses from application requests.

The LLM integration includes:

* LLM client abstraction
* Local Ollama implementation
* Generation request DTO
* Generation response DTO
* Runtime configuration
* Unit tests

The LLM integration is intentionally kept separate from semantic retrieval.

The architecture therefore allows the application to prepare semantic context first and then pass that context to the LLM/Text-to-SQL component.

---

# Current LLM Flow

The current integration can be represented as:

```text
Application
    |
    v
Generation Request
    |
    v
LLM Abstraction
    |
    v
Ollama
    |
    v
Local LLM
    |
    v
Generation Response
```

The LLM integration is complete as an infrastructure capability.

However, the complete Semantic Retrieval → Prompt Assembly → Text-to-SQL flow is not considered complete yet.

---

# Clean Architecture Decisions

The following architectural decisions are currently applied:

* Application code depends on ports/abstractions rather than infrastructure implementations.
* Infrastructure-specific dependencies are isolated from application logic.
* Raw schema access belongs to the semantic-layer preparation/build phase.
* Semantic artifacts are treated as data, not hard-coded business rules.
* Runtime configuration is kept under `src/config`.
* LLM integration is isolated from semantic-layer orchestration.
* Semantic retrieval is intended to be handled independently from LLM generation.
* Query-time logic should consume the persisted semantic layer rather than regenerate semantic information.

---

# Current Status

## Completed

```text
Schema Loading                 ✅
Schema Normalization           ✅
Schema Relationships           ✅ / prepared
Semantic Artifact Preparation  ✅
initial_draft.json             ✅
Semantic Settings              ✅
Clean Architecture             ✅
LLM Integration                ✅
LLM Integration Tests          ✅
```

## Not Completed Yet

```text
Final Semantic Layer Build     ⏳
SemanticLayerBuildService      ⏳
SemanticLayerLoader            ⏳
Persisted Active Snapshot      ⏳
Embedding Generation           ⏳
Vector Index                   ⏳
SemanticRepository             ⏳
ContextRetrievalService        ⏳
Keyword Fallback               ⏳
Prompt Assembly                ⏳
Full Text-to-SQL Integration   ⏳
```

---

# Next Development Stage

The next stage starts from the current semantic artifacts.

The planned flow is:

```text
Prepared Semantic Artifacts
          |
          v
SemanticLayerBuildService
          |
          v
Final Semantic Layer
          |
          v
Persisted Active Snapshot
          |
          v
Embedding / Vector Index
          |
          v
SemanticRepository
          |
          v
ContextRetrievalService
          |
          v
Relevant Semantic Context
          |
          v
Prompt Assembly
          |
          v
LLM / Text-to-SQL
```

The important architectural rule is that the query-time path should not call:

```text
SchemaRepository
SchemaLoader
Semantic Generation
```

Instead, the query-time path should retrieve information from the already-built and persisted semantic layer.

---

# Semantic Layer Replacement Lifecycle

When a new database/schema is loaded, the intended lifecycle is:

```text
New Dataset
    |
    v
Load & Validate Schema
    |
    v
Prepare Semantic Artifacts
    |
    v
Build New Semantic Snapshot
    |
    v
Build New Vector Index
    |
    v
Replace Active Semantic Layer
```

The old semantic snapshot is removed/replaced when the new semantic layer becomes active.

This ensures that subsequent user questions operate against the semantic representation of the currently active dataset.

---

# Human Review

Human review is required before treating the semantic layer as production-ready.

Business documentation and the business glossary are considered authoritative sources for business meanings and business rules.

The LLM is not treated as the authority for defining or approving business semantics.

The LLM should consume the approved semantic information rather than inventing business definitions.

---

# Current Milestone

The current milestone is:

> **Semantic Layer Preparation + LLM Integration**

At this point, the project has successfully prepared the initial semantic artifacts and established the local LLM integration.

The next milestone is to complete the persisted semantic layer and its retrieval mechanism, then connect the retrieved semantic context to the Text-to-SQL generation pipeline.
