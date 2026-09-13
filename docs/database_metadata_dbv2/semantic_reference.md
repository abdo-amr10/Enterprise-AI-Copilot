# Sakila Semantic Reference, Examples, and Query Policies

This file contains the material that should remain available for implementation reference, prompt design, testing, and validation.

It intentionally separates these concerns from the Business Class:
- natural-language question examples
- SQL-generation constraints
- RLS/security rules
- RLS-safe SQL patterns
- negative examples / hallucination guards
- aggregation/query-shape guidance
- final validation checklist

The Business Class remains focused on business meaning.

---

## 1. Common User-Question Patterns

These are **reference examples**, not business entities or definitions. They can be used for testing, few-shot prompting, evaluation, or validating the Semantic Parser.

The model should be prepared for natural-language variations of supported concepts, including:

- "Show all customers", "List clients", "Which customers do we have?"
- "Show the top 5 customers", "Top customers by number of rentals", "Customers with the most payments".
- "How many customers are there?"
- "Show active customers", "List inactive customers" — only if the meaning of the stored `active` values is established by the data/business rules.
- "Show all movies", "List films", "Find movies by title".
- "Which movies are rated ...?", "Show films released in ...", "Longest movies", "Movies with the highest rental rate".
- "Show all rentals", "Recent rentals", "Rentals from a specific date", "Unreturned rentals".
- "How many rentals?", "Top rented movies", "Movies rented the most".
- "Show payments", "Total payments", "Total payment amount", "Average payment", "Payments by date".
- "How much was collected?", "How much did customers pay?" — map to `SUM(payment.amount)` only when the intended meaning is total recorded payments.
- "Show staff", "List employees", "Employees for a store".
- "Which employee handled the most rentals/payments?"
- "Show categories", "List genres", "Movies in the Action category".
- "Which actors are in a movie?", "Movies featuring an actor", "Actors with the most films".
- "Show customers by city/country", "Customers in a country".
- "Show stores by city/country", "Store address/location".
- "Show inventory for a store", "How many copies of a film does a store have?"
- "Show movies by category", "Categories with the most films".
- "Show movies by language", "Films in a specific language".
- "Show rentals by customer/movie/category/store".
- "Show payments by customer/staff/rental".
- "Compare stores by customers/rentals/payments/inventory" — only for stores/data visible under the current RLS scope.
- "Top 10", "bottom 10", "highest", "lowest", "most", "least", "average", "total", "count" should be translated into the appropriate SQL aggregation/order only when the requested entity and metric are supported.
- "Today", "yesterday", "this month", "last month", "this year", and similar relative dates should be handled as date filters against the relevant documented datetime column; do not invent a different date definition.
- "Between two dates", "after a date", "before a date", and "during a period" should use the relevant documented datetime field (`rental.rental_date`, `rental.return_date`, or `payment.payment_date`) according to the user's wording.

### Important

These examples are not supposed to become hardcoded deterministic rules such as:

```text
if question contains "top 5 customers":
    ...
```

They are representative examples of the supported semantic space.

---

## 2. SQL Generation Safety Constraints

Generated SQL must follow these constraints:

1. Generate read-only `SELECT` or `WITH` queries only.
2. Never generate `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `TRUNCATE`, or other write/DDL statements.
3. Use only tables present in the supplied schema.
4. Use only columns present in the supplied schema.
5. Use only documented relationships and join paths.
6. Do not invent tables, columns, metrics, formulas, or relationships.
7. Apply the required RLS scope to every protected query scope.
8. Preserve RLS in CTEs and subqueries.
9. Never hardcode a user's store ID in place of `@UserStoreId`.
10. Do not remove or bypass the security predicate merely because the user did not mention the store.

---

## 3. RLS-Aware Query Interpretation

The semantic layer applies store-level security using `@UserStoreId`.

The model must treat this as a security requirement, not as a user-provided filter.

Protected direct tables include:

- `store`
- `customer`
- `inventory`
- `staff`

Protected `rental` data must be scoped through `inventory.store_id`.

Protected `payment` data must be scoped through `customer.store_id`.

The RLS policy explicitly defines `BranchId` as the source user value and `@UserStoreId` as the security parameter.

Every query scope that reads protected data, including CTEs and subqueries, must preserve the applicable RLS predicate.

The security parameter must never be hardcoded or omitted.

---

## 4. RLS-Safe SQL Patterns

The configured security parameter is:

```text
@UserStoreId
```

### Direct store-scoped table

For `store`:

```sql
SELECT ...
FROM store
WHERE store.store_id = @UserStoreId;
```

For `customer`:

```sql
SELECT ...
FROM customer
WHERE customer.store_id = @UserStoreId;
```

For `inventory`:

```sql
SELECT ...
FROM inventory
WHERE inventory.store_id = @UserStoreId;
```

For `staff`:

```sql
SELECT ...
FROM staff
WHERE staff.store_id = @UserStoreId;
```

### Rental through inventory

```sql
SELECT ...
FROM rental
INNER JOIN inventory
    ON rental.inventory_id = inventory.inventory_id
WHERE inventory.store_id = @UserStoreId;
```

### Payment through customer

```sql
SELECT ...
FROM payment
INNER JOIN customer
    ON payment.customer_id = customer.customer_id
WHERE customer.store_id = @UserStoreId;
```

These are examples of the configured security paths. Do not replace them with invented alternatives.

---

## 5. Negative Examples and Hallucination Guards

The following should not be invented as database fields or predefined business metrics:

- `profit`
- `net revenue`
- `overdue fees`
- `customer lifetime value`
- `inventory availability`
- `utilization rate`
- `churn rate`
- `customer satisfaction`
- `revenue growth`
- `sales target`
- `customer segment`
- `due date`
- `late fee`

If the user asks for one of these, the model should not fabricate SQL columns or formulas. It should only produce SQL if the user supplies a precise business definition that can be expressed using the available schema.

### Reference examples

| User question | Supported interpretation | Avoid |
|---|---|---|
| Show total payments | `SUM(payment.amount)` | Inventing a revenue table |
| Show available movies | No defined availability rule | Inventing `available` column |
| Show best customers | Ask/require a metric | Assuming payments or rentals without clarification |
| Show employee sales | Can use payments/staff if "sales" clearly means recorded payments | Inventing `sales` column |
| Show overdue rentals | No defined overdue rule | Inventing a due-date or late-fee formula |
| Show profit | No profit formula exists | `SUM(payment.amount) - ...` with invented costs |

---

## 6. Store Comparison and Aggregation Boundaries

Questions such as:

- compare stores
- top stores
- stores with the most customers
- stores with the most rentals
- stores with the highest payment totals

must remain limited to data visible under the current RLS scope.

Do not bypass the active `@UserStoreId` restriction in order to compare all stores.

If the current security context allows only one store, a request to compare all stores cannot be fulfilled by removing the RLS predicate.

---

## 7. Query-Shape Guidance

The model may combine supported operations when the question requires them:

- filtering with `WHERE`
- grouping with `GROUP BY`
- aggregation with `COUNT`, `SUM`, or `AVG`
- ordering with `ORDER BY`
- ranking/limiting results
- joins using documented relationships
- CTEs when useful

Do not add an operation simply because it is common.

Every aggregation, filter, grouping, or date condition should correspond to the user's actual request.

---

## 8. Final Validation Checklist

Before producing SQL, verify:

1. Does every referenced table exist in the schema?
2. Does every referenced column exist in the schema?
3. Is every join supported by a documented relationship/path?
4. Is the requested metric actually defined or directly derivable?
5. Is the requested date mapped to the correct datetime column?
6. Are NULL semantics handled correctly where relevant?
7. Is the query read-only?
8. Is the RLS predicate present for every protected query scope?
9. Is `@UserStoreId` used instead of a hardcoded store ID?
10. Did the model avoid inventing a business rule for an ambiguous term?

---

## 9. How to Use the Two Files

### Business Class / Semantic Model

Use `Sakila_Business_Semantic_Model.md` as the source for:

- entity recognition
- terminology normalization
- synonym resolution
- attribute interpretation
- metric interpretation
- relationship/path interpretation
- temporal interpretation
- NULL semantics
- ambiguity detection
- supported business-definition boundaries

### Reference / Policy File

Use `Sakila_Semantic_Reference_and_Policies.md` as the source for:

- test questions
- few-shot/reference examples
- prompt examples
- SQL safety constraints
- RLS requirements
- RLS-safe SQL patterns
- hallucination guards
- validation rules

### Architectural boundary

The Business Class should answer:

> What does the user's business language mean?

The Reference/Policy file should answer:

> How should that meaning be tested, constrained, validated, and safely translated into SQL?

Security enforcement should remain deterministic in the pipeline. The LLM should not be trusted as the sole enforcer of RLS or SQL safety.