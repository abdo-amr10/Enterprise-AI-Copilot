# Synthetic Banking AI — Clean Architecture

This project contains the AI-side implementation of the Synthetic Banking Text-to-SQL system.

The implementation is organized into two main stages:

1. **Semantic Layer Build**
2. **Runtime Text-to-SQL Pipeline**

The Semantic Layer is prepared and validated first.
The runtime pipeline then consumes the approved Semantic Layer to retrieve relevant information and generate SQL from user questions.

The current implementation reaches the **SQL Query / LLM Response** stage.

SQL validation, correction/retry, and backend integration are the next development stages.

---

# Project Structure

```text
ai/
├── models/
│   └── embeddings/
│       └── all-MiniLM-L6-v2/
│
├── outputs/
│
├── scripts/
│   └── run_text_to_sql_pipeline.py
│
├── src/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── config/
│
├── tests/
│
├── pytest.ini
├── README.md
└── requirements.txt
```

---

# Architecture Overview

The AI implementation is divided into a build stage and a runtime stage.

```text
                  SEMANTIC LAYER BUILD
                  ====================

Database Schema
      |
      v
Schema Loading
      |
      v
Schema Validation & Normalization
      |
      v
Relationship Preparation
      |
      v
Semantic Artifact Preparation
      |
      v
Initial Semantic Draft
      |
      v
Semantic Layer
      |
      v
Human Review / Validation
      |
      v
Approved Semantic Layer
      |
      |
      | persisted and prepared for runtime
      v
================================================

                  RUNTIME PIPELINE
                  ================

User Question
      |
      v
Semantic Retrieval
      |
      v
Relevant Semantic Context
      |
      v
Prompt Construction
      |
      v
SQL Generation
      |
      v
LLM Response
      |
      v
Generated SQL
```

The two stages are intentionally separated.

The Semantic Layer is not regenerated for every user question.

---

# 1. Semantic Layer

The Semantic Layer is the main knowledge representation used by the Text-to-SQL system.

Its purpose is to provide the LLM with a structured and meaningful representation of the database instead of relying only on the raw database schema.

The Semantic Layer can represent:

* Database entities
* Tables
* Columns
* Data types
* Relationships
* Business meanings
* Business rules
* Semantic descriptions
* Other metadata required for SQL generation

The Semantic Layer is prepared once and then reused during query-time retrieval.

---

# 2. Semantic Layer Build Process

The Semantic Layer is built as a separate preparation process.

The implemented flow is:

```text
Raw Database Schema
        |
        v
Schema Loading
        |
        v
Schema Validation
        |
        v
Schema Normalization
        |
        v
Relationship Preparation
        |
        v
Semantic Artifact Preparation
        |
        v
Initial Semantic Draft
        |
        v
Semantic Layer
        |
        v
Human Review / Validation
        |
        v
Approved Semantic Layer
```

---

# 3. Schema Loading

The first part of the Semantic Layer build process is loading the database schema.

The `SchemaLoader` is responsible for reading the schema information and making it available to the semantic preparation process.

The schema-loading process includes:

* Loading the schema artifact
* Validating the expected structure
* Reading database entities
* Preparing the schema for normalization

The raw schema is used during the Semantic Layer build process.

It is not intended to be regenerated for every user question.

---

# 4. Schema Normalization

After loading the schema, the schema representation is normalized into a consistent structure.

Normalization provides a stable representation that can be used by the remaining Semantic Layer preparation steps.

The normalized schema becomes the basis for:

* Relationship preparation
* Semantic artifact generation
* Semantic descriptions
* Runtime semantic information

---

# 5. Schema Relationships

Relationships are prepared as part of the Semantic Layer because understanding the database structure is necessary for generating valid SQL.

The relationship information represents how database entities are connected.

It can describe:

* Foreign-key relationships
* Parent/child relationships
* Related entities
* Valid join paths

For the Synthetic Banking database, examples include:

```text
customers
    |
    +---- accounts
             |
             +---- cards
             |
             +---- transactions
                         |
                         +---- merchants

customers
    |
    +---- loans

branches
    |
    +---- accounts
```

This relationship information allows the Semantic Layer to provide the LLM with information about how entities can be connected when generating SQL.

---

# 6. Semantic Artifact Preparation

After schema normalization and relationship preparation, the information is transformed into semantic artifacts.

The purpose of this stage is to move from a purely structural database representation to information that can be consumed semantically.

The preparation process is:

```text
Normalized Schema
       +
Relationships
       |
       v
Semantic Artifact Preparation
       |
       v
Structured Semantic Information
```

The semantic artifacts contain the information required to describe the database semantically.

---

# 7. Initial Semantic Draft

The semantic preparation process produces the initial semantic draft:

```text
initial_draft.json
```

The initial draft is generated from the available schema and semantic information.

The process is:

```text
Raw Schema
    |
    v
Schema Loading
    |
    v
Normalization
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

The initial draft is not automatically treated as the final approved Semantic Layer.

It enters the review and validation stage first.

---

# 8. Semantic Layer Review and Human Validation

Human review is an important part of the Semantic Layer build process.

The generated semantic information is reviewed before it becomes the approved Semantic Layer used by the runtime system.

The review process is:

```text
Initial Semantic Draft
        |
        v
Semantic Review
        |
        +------------------+
        |                  |
        v                  v
     Valid              Invalid
        |                  |
        v                  v
Approved Layer       Revision / Update
                           |
                           v
                     Review Again
```

The review verifies that the semantic representation correctly describes the database and its intended meaning.

This is especially important for:

* Business meanings
* Business rules
* Definitions
* Relationships
* Semantic descriptions
* Business-specific interpretation

The LLM is not treated as the authority for defining or approving business semantics.

Only the reviewed and validated Semantic Layer is used by the runtime pipeline.

---

# 9. Approved Semantic Layer

After successful review and validation, the Semantic Layer becomes the approved semantic representation.

The lifecycle is:

```text
Schema
   |
   v
Semantic Preparation
   |
   v
Initial Draft
   |
   v
Human Review
   |
   v
Approved Semantic Layer
```

The approved Semantic Layer is then prepared for runtime retrieval.

This creates a clear separation between:

```text
Build Time
    |
    v
Create + Review Semantic Layer

Runtime
    |
    v
Retrieve + Use Semantic Layer
```

The runtime does not regenerate the Semantic Layer.

---

# 10. Semantic Layer Runtime Preparation

Once the Semantic Layer has been approved, its semantic documents are prepared for runtime retrieval.

The documents are converted into embeddings using:

```text
all-MiniLM-L6-v2
```

The model is stored locally under:

```text
models/embeddings/all-MiniLM-L6-v2/
```

The preparation flow is:

```text
Approved Semantic Layer
        |
        v
Semantic Documents
        |
        v
Embedding Generation
        |
        v
Vector Representations
        |
        v
Local Vector Index
```

The resulting vector index is used during runtime retrieval.

A keyword-based retrieval fallback is also available.

---

# 11. Vector Index

The semantic documents are indexed so that relevant semantic information can be retrieved for a user question.

The current implementation uses local vector storage.

The indexing flow is:

```text
Semantic Documents
       |
       v
Embedding Generation
       |
       v
Vector Representations
       |
       v
Local Vector Index
```

No external vector database is required by the current implementation.

The index is prepared from the approved Semantic Layer and reused during runtime.

---

# 12. Runtime Semantic Retrieval

After the Semantic Layer has been prepared and indexed, the runtime pipeline can retrieve relevant semantic information for each user question.

The retrieval flow is:

```text
User Question
      |
      v
Query Embedding
      |
      v
Vector Search
      |
      v
Relevant Semantic Documents
```

Vector retrieval is the primary retrieval mechanism.

A keyword-based fallback is available when vector retrieval cannot be used.

```text
Vector Retrieval
       |
       | unavailable
       v
Keyword Retrieval
```

The goal is to retrieve the semantic information relevant to the current question instead of passing the entire Semantic Layer to the LLM.

---

# 13. Semantic Context Construction

The retrieved semantic documents are passed to the application layer to construct the context used by the LLM.

The flow is:

```text
User Question
      |
      v
Semantic Retrieval
      |
      v
Relevant Documents
      |
      v
Semantic Context
```

The semantic context provides the LLM with the information required to generate the SQL query.

The context is designed to keep SQL generation grounded in the approved Semantic Layer.

The LLM should not invent:

* Tables
* Columns
* Relationships
* Business rules
* Measures
* Semantic definitions

when the required information is not supported by the supplied context.

---

# 14. SQL Generation

SQL Generation is the stage where the natural-language question and the retrieved semantic context are passed to the local LLM to generate a SQL query.

The current implementation separates SQL generation from semantic retrieval.

The generation flow is:

```text
User Question
      |
      v
Semantic Context
      |
      v
Prompt Construction
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
qwen2.5-coder:7b
      |
      v
Generation Response
      |
      v
Generated SQL
```

## Prompt Construction

Before calling the LLM, the application combines the required information into the generation prompt.

The prompt provides the model with:

* The user's natural-language question
* The retrieved semantic context
* The information needed to generate the SQL query
* Instructions that keep the generated SQL grounded in the supplied semantic information

The purpose of this step is to give the LLM only the relevant semantic information required for the current question.

---

## Generation Request

The application does not call Ollama directly from the business logic.

Instead, the generation request is passed through the LLM abstraction.

The request contains the information required for generation, including the prompt and the configured generation parameters.

The application therefore remains independent from the specific LLM runtime.

---

## Ollama Integration

The generation request is sent through the Ollama infrastructure implementation.

The current model is:

```text
qwen2.5-coder:7b
```

Ollama executes the model locally and returns the generation response to the application.

The flow is:

```text
Application
    |
    v
LLM Abstraction
    |
    v
Ollama Client
    |
    v
qwen2.5-coder:7b
    |
    v
Generation Response
```

---

## Generation Response

The LLM returns a generation response to the application.

The response contains the generated model output from which the SQL query is obtained.

The current result is:

```text
Generated SQL Query
```

At this point, the generated SQL has **not yet passed through the SQL validation/correction stage**.

Therefore, SQL Generation is considered complete when the LLM response containing the generated SQL is received.

---

# 15. Current Runtime Text-to-SQL Flow

Putting the implemented runtime components together:

```text
User Question
      |
      v
Semantic Retrieval
      |
      v
Relevant Semantic Documents
      |
      v
Semantic Context
      |
      v
Prompt Construction
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
qwen2.5-coder:7b
      |
      v
Generation Response
      |
      v
Generated SQL Query
```

This is the current stopping point of the AI implementation.

---

# 16. LLM Integration

The LLM is integrated as a separate infrastructure component.

The implementation includes:

* LLM client abstraction
* Ollama implementation
* Model configuration
* Generation request
* Generation response
* Unit tests
* Integration testing

The LLM integration is intentionally separated from Semantic Layer retrieval.

This allows the application to retrieve and prepare the semantic context before passing it to the LLM.

---

# 17. Clean Architecture

The project follows Clean Architecture principles.

The main source structure is:

```text
src/
├── domain/
├── application/
├── infrastructure/
└── config/
```

## Domain Layer

Contains the core domain concepts and abstractions.

The domain layer does not depend on infrastructure implementations.

## Application Layer

Contains application-level services and use cases.

Application components depend on abstractions rather than directly depending on infrastructure implementations.

Current responsibilities include:

* Semantic context retrieval
* LLM generation handling
* Application DTOs
* Repository interfaces

## Infrastructure Layer

Contains implementations that interact with external systems and local resources.

Current responsibilities include:

* Schema loading
* Semantic Layer persistence
* Embedding generation
* Vector storage
* Semantic retrieval
* Ollama integration

## Configuration

Contains runtime configuration used by application and infrastructure components.

---

# 18. Architectural Decisions

The current implementation follows these main decisions:

* The Semantic Layer is built separately from the runtime query pipeline.
* The Semantic Layer is reviewed and validated before runtime use.
* The approved Semantic Layer is persisted and reused.
* Runtime questions do not regenerate the Semantic Layer.
* Semantic retrieval is separated from SQL generation.
* Prompt construction is separated from the LLM infrastructure.
* Application code depends on abstractions rather than infrastructure implementations.
* Infrastructure-specific dependencies remain inside the infrastructure layer.
* Local models are used for embeddings and LLM execution.
* Semantic context is retrieved before SQL generation.
* The current pipeline stops after receiving the generated SQL from the LLM.

---

# 19. Testing

The implemented components include unit and integration tests.

The test suite can be executed from the `ai` directory:

```bash
pytest
```

Testing currently covers implemented components such as:

* Application components
* Semantic retrieval components
* LLM request/response handling
* Ollama integration
* LLM generation

The LLM infrastructure also has an integration test that verifies generation through the local Ollama runtime.

---

# 20. Local Models

The project uses two local models for different purposes.

## Embedding Model

```text
all-MiniLM-L6-v2
```

Used for semantic retrieval.

Stored under:

```text
models/embeddings/all-MiniLM-L6-v2/
```

## LLM

```text
qwen2.5-coder:7b
```

Used for SQL generation through Ollama.

---

# 21. Current Status

## Semantic Layer

```text
Schema Loading                    ✅
Schema Validation                 ✅
Schema Normalization              ✅
Schema Relationships              ✅
Semantic Artifact Preparation     ✅
Initial Semantic Draft            ✅
Semantic Layer Build              ✅
Human Review                      ✅
Human Validation                  ✅
Approved Semantic Layer           ✅
```

## Runtime Semantic Pipeline

```text
Semantic Layer Loading            ✅
Embedding Generation              ✅
Local Vector Index                ✅
Semantic Retrieval                ✅
Keyword Retrieval Fallback        ✅
Context Construction              ✅
Prompt Construction               ✅
```

## SQL Generation

```text
Generation Request                ✅
LLM Abstraction                   ✅
Ollama Integration                ✅
qwen2.5-coder:7b                  ✅
Generation Response                ✅
Generated SQL Query                ✅
```

## Testing

```text
LLM Unit Tests                    ✅
LLM Integration Test              ✅
Semantic Retrieval Tests          ✅
```

---

# 22. Not Implemented Yet

The following stages are the next development steps:

```text
SQL Validation                    ⏳
SQL Correction / Retry            ⏳
Human Approval / Rejection        ⏳
Backend Integration                ⏳
Secure SQL Execution               ⏳
Full End-to-End Pipeline           ⏳
```

The next flow will extend the current implementation:

```text
Generated SQL
      |
      v
SQL Validation
      |
      +------------------+
      |                  |
    Valid              Invalid
      |                  |
      |                  v
      |             Correction
      |                  |
      |                  v
      |                Retry
      |                  |
      +--------<---------+
      |
      v
Human Approval / Rejection
      |
      v
Backend Integration
      |
      v
Secure SQL Execution
```

---

# Current Milestone

**Approved Semantic Layer + Runtime Semantic Retrieval + SQL Generation**

The current AI implementation has completed the Semantic Layer build and validation process and connected the approved Semantic Layer to the runtime Text-to-SQL flow.

The implemented system currently provides:

```text
Database Schema
      |
      v
Schema Preparation
      |
      v
Semantic Layer Preparation
      |
      v
Initial Semantic Draft
      |
      v
Human Review / Validation
      |
      v
Approved Semantic Layer
      |
      v
Embedding / Vector Index
      |
      v
Semantic Retrieval
      |
      v
Semantic Context
      |
      v
Prompt Construction
      |
      v
SQL Generation
      |
      v
Local LLM / Ollama
      |
      v
Generation Response
      |
      v
Generated SQL Query
```

The current stopping point is:

```text
SQL Query / LLM Response
```

The immediate next development stage is:

```text
SQL Validation
      |
      v
Correction / Retry
      |
      v
Human Approval / Rejection
      |
      v
Backend Integration
      |
      v
Secure SQL Execution
```

The complete end-to-end Text-to-SQL pipeline is therefore still under development.