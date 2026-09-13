# Sakila Semantic Layer Documentation

## Purpose

This file contains **technical and structural documentation** for the Sakila Semantic Layer.

It answers:

> **What exists in the database, how is it technically connected, and how does the Semantic Layer obtain and maintain that technical truth?**

This file is intended to be used by the **Semantic Builder as a technical source**, together with the authoritative physical schema (`schema.json`) and the Business Glossary.

It does **not** define business synonyms, business metrics, ranking meaning, natural-language interpretation, SQL-generation policy, SQL safety rules, test cases, or few-shot examples.

## 1. Database

The target database is the SQL Server database named `sakila`.

The application reads database metadata through `TargetConnection` and executes read-only SQL against the same connection.

The physical database schema is authoritative for:

- tables
- columns
- primary keys
- foreign keys
- column types and other physical metadata

`schema.json` remains the final structural source of truth. This documentation describes the technical organization and lifecycle around that schema; it does not replace it.

---

## 2. Available Base Tables

The available base tables are:

- `actor`
- `address`
- `category`
- `city`
- `country`
- `customer`
- `film`
- `film_actor`
- `film_category`
- `film_text`
- `inventory`
- `language`
- `payment`
- `rental`
- `staff`
- `store`

The SQL Server metadata synchronization process reads base tables, columns, primary keys, and foreign keys.

Views from the source script are not included as base-table metadata.

---

## 3. Technical Relationship Paths

The following are documented physical relationship paths available to the Semantic Layer.

### Customer → Store

```text
customer.store_id → store.store_id
```

### Customer → Address → City → Country

```text
customer.address_id → address.address_id
address.city_id → city.city_id
city.country_id → country.country_id
```

### Store → Address → City → Country

```text
store.address_id → address.address_id
address.city_id → city.city_id
city.country_id → country.country_id
```

### Rental → Inventory → Film

```text
rental.inventory_id → inventory.inventory_id
inventory.film_id → film.film_id
```

### Payment → Customer

```text
payment.customer_id → customer.customer_id
```

### Payment → Rental → Inventory → Store

```text
payment.rental_id → rental.rental_id
rental.inventory_id → inventory.inventory_id
inventory.store_id → store.store_id
```

### Rental → Inventory → Store

```text
rental.inventory_id → inventory.inventory_id
inventory.store_id → store.store_id
```

### Film → Film Actor → Actor

```text
film_actor.film_id → film.film_id
film_actor.actor_id → actor.actor_id
```

The bridge table `film_actor` is the technical path between films and actors.

### Film → Film Category → Category

```text
film_category.film_id → film.film_id
film_category.category_id → category.category_id
```

The bridge table `film_category` is the technical path between films and categories.

### Film → Language

```text
film.language_id → language.language_id
```

### Film → Original Language

```text
film.original_language_id → language.language_id
```

### Rental → Customer

```text
rental.customer_id → customer.customer_id
```

### Payment → Staff

```text
payment.staff_id → staff.staff_id
```

### Rental → Staff

```text
rental.staff_id → staff.staff_id
```

---

## 4. Technical Relationship Principles

1. Physical relationships must come from the authoritative schema metadata.
2. A relationship path may contain one or more intermediate tables when those tables are required by the schema.
3. Bridge tables such as `film_actor` and `film_category` are part of the approved physical path.
4. Matching column names alone do not establish a relationship.
5. The Semantic Builder must not invent a foreign key or shortcut an approved multi-hop relationship.
6. If documentation and the physical schema disagree, the physical schema is authoritative for structural truth.
7. Business meaning of a relationship belongs in the Business Glossary; the physical mapping belongs here.

---

## 5. Metadata Lifecycle

The database metadata synchronization endpoint is:

```text
POST /api/v1/semantic-layer/{id}/sync-metadata
```

The synchronization result is stored in:

```text
SemanticLayers.DatabaseMetadataJson
```

and in the active revision's:

```text
PhysicalSchemaJson
```

Metadata synchronization updates the technical database representation used by the Semantic Layer.

Existing RLS policy is not overwritten by metadata synchronization.

---

## 6. Semantic Revision and Physical Schema

The active semantic revision contains the physical schema representation used by downstream Semantic Layer processing.

The physical schema is the authoritative source for the existence of:

- tables
- columns
- primary keys
- foreign keys
- physical relationship structure

Semantic knowledge may enrich this structural baseline with business meaning, but it must remain mapped to real physical objects.

---

## 7. RLS Technical Integration

RLS policy is stored in:

```text
SemanticLayers.RlsPolicyJson
```

The current user's security value comes from:

```text
Users.BranchId
```

For Sakila, this value represents:

```text
store.store_id
```

Example:

```text
Users.BranchId = 1
```

means that the user may access rows belonging to:

```text
store_id = 1
```

The mapping between the application user's security value and the physical store scope is a technical/security concern. It should not be inferred from natural-language wording.

---

## 8. RLS Scope and Protected Data Paths

The technical RLS configuration determines how store scope applies to protected data.

Relevant physical paths include:

- store-owned customer data through `customer.store_id`
- store-owned inventory through `inventory.store_id`
- store-owned staff through `staff.store_id`
- rental data through `rental → inventory → store`
- payment data through `payment → customer → store`, and where applicable through the documented rental/inventory path

The exact enforcement mechanism remains a pipeline/security responsibility. This document records the technical integration and mapping, not the SQL-generation implementation.

---

## 9. What Belongs in This File

This Documentation file is the source for:

- database identity
- physical database organization
- available base tables
- technical relationships
- foreign-key paths
- bridge-table paths
- metadata synchronization lifecycle
- semantic revision physical-schema lifecycle
- RLS storage and user-value mapping
- technical security scope paths

---

## 10. What Does Not Belong in This File

Do **not** use this file as the source for:

- business synonyms such as `movie = film`
- business definitions such as what a customer means
- metric definitions such as Customer Count or Total Payment Amount
- ranking semantics such as `top N`
- date-language interpretation
- NULL/business-state interpretation
- ambiguity handling
- user-question examples
- few-shot examples
- SQL syntax rules
- SQL read-only restrictions
- prompt-injection rules
- RLS SQL templates
- validation checklists

Those concerns belong to the Business Glossary or the separate Reference file, depending on their purpose.

---

## 11. Architectural Boundary

The Documentation file answers:

> **What exists physically and how is it technically connected?**

The Business Glossary answers:

> **What do those physical objects mean in business/user language?**

The Reference file answers:

> **How should the semantic knowledge be tested, demonstrated, constrained, and validated during implementation?**

The authoritative physical schema remains the final source of structural truth.