# Sakila Business Semantic Model

This file contains only business-semantic knowledge intended for the Semantic Layer / Business Class.

It defines:
- business entities and concepts
- business terminology and synonyms
- attribute meanings
- supported metrics
- temporal meanings
- NULL meanings where they are directly supported
- supported semantic relationship paths
- ambiguity and business-definition boundaries

It intentionally does **not** contain:
- user-question examples
- few-shot examples
- SQL-generation instructions
- SQL safety rules
- RLS SQL implementation patterns
- validation checklists

The database schema remains the authoritative source for physical tables, columns, and foreign-key relationships.

---

## 1. Core Business Glossary

| Business term | Database mapping | Meaning |
|---|---|---|
| Store | `store` | A physical rental store and its manager/address. |
| Store ID | `store.store_id` | Unique identifier of a store. It is the RLS scope value. |
| Customer | `customer` | A customer who rents films and makes payments. |
| Customer ID | `customer.customer_id` | Unique identifier of a customer. |
| Film | `film` | A movie available for rental. |
| Inventory | `inventory` | A copy of a film held by a store. |
| Rental | `rental` | A rental transaction for an inventory item and customer. |
| Payment | `payment` | A payment related to a customer, staff member, and optional rental. |
| Staff | `staff` | An employee assigned to a store. |
| Actor | `actor` | An actor associated with films. |
| Category | `category` | A film category. |
| Address | `address` | A postal address linked to a city. |
| City | `city` | A city linked to a country. |
| Country | `country` | A country in the address hierarchy. |
| Rental amount | `payment.amount` | The monetary value of a payment. |
| Rental date | `rental.rental_date` | Date and time when a rental was created. |
| Return date | `rental.return_date` | Date and time when a rental was returned; it may be null. |

---

## 2. Business Relationships

These are semantic relationship paths. They do not replace the authoritative schema.

- Customer to store: `customer.store_id = store.store_id`.
- Customer to address: `customer.address_id = address.address_id`.
- Rental to film: `rental.inventory_id = inventory.inventory_id` then `inventory.film_id = film.film_id`.
- Payment to customer: `payment.customer_id = customer.customer_id`.
- Payment to store: join `payment` to `customer` and filter `customer.store_id`.
- Rental to store: join `rental` to `inventory` and filter `inventory.store_id`.
- Film to actor: use `film_actor` as the bridge table.
- Film to category: use `film_category` as the bridge table.

Do not invent joins that are not present in `schema.json`.

---

## 3. Expanded Business Terminology

The following terms are derived only from the existing glossary, `schema.json`, and documented semantic-layer rules. They improve natural-language interpretation without introducing unsupported tables, columns, relationships, or business rules.

| Business term | Database mapping | Meaning |
|---|---|---|
| Store / Branch | `store` | A physical rental store. "Branch" may be used by users as a synonym for store. |
| Store number / Branch ID | `store.store_id` | Unique identifier of a store and the store-level RLS scope value. |
| Store manager | `store.manager_staff_id` → `staff.staff_id` | Staff member assigned as the manager of a store. |
| Customer / Client | `customer` | A customer who rents films and makes payments. "Client" may be used as a synonym for customer. |
| Customer name | `customer.first_name`, `customer.last_name` | First and last name of a customer. |
| Customer email | `customer.email` | Email address of a customer. |
| Active customer | `customer.active` | Customer active-status field. Do not assume a specific character value unless supported by the data/business rules. |
| Customer registration date | `customer.create_date` | Date and time when the customer record was created. |
| Movie / Film | `film` | A movie available for rental. "Movie" is a likely user synonym for film. |
| Movie title | `film.title` | Title of a film. |
| Movie description | `film.description` | Description of a film. |
| Release year | `film.release_year` | Release year stored for a film. |
| Film language | `film.language_id` → `language.language_id` | Language associated with the film through the language relationship. |
| Original language | `film.original_language_id` → `language.language_id` | Original language associated with the film. |
| Rental duration | `film.rental_duration` | Rental duration configured for a film. |
| Rental rate | `film.rental_rate` | Rental rate configured for a film. |
| Movie length / Duration | `film.length` | Film length. |
| Replacement cost | `film.replacement_cost` | Replacement cost associated with a film. |
| Rating | `film.rating` | Film rating value. |
| Special features | `film.special_features` | Special features recorded for a film. |
| Inventory / Copies | `inventory` | Physical copies of films held by stores. |
| Inventory copy / Copy ID | `inventory.inventory_id` | Unique identifier for a physical inventory copy. |
| Rental / Rental transaction | `rental` | A rental transaction for an inventory item and customer. |
| Rental ID | `rental.rental_id` | Unique identifier of a rental transaction. |
| Rental date / Rented at | `rental.rental_date` | Date and time when the rental was created. |
| Return date / Returned at | `rental.return_date` | Date and time when a rental was returned; may be null. |
| Unreturned rental | `rental.return_date` | A rental whose return date is null. This is a direct interpretation of the documented nullable return date. |
| Payment / Revenue transaction | `payment` | A payment related to a customer, staff member, and optional rental. "Revenue" should be interpreted carefully as payment amounts unless a separate business definition is supplied. |
| Payment amount / Rental amount | `payment.amount` | Monetary value recorded for a payment. |
| Payment date | `payment.payment_date` | Date and time when the payment was recorded. |
| Payment ID | `payment.payment_id` | Unique identifier of a payment. |
| Staff / Employee | `staff` | An employee assigned to a store. "Employee" may be used as a synonym for staff. |
| Staff ID / Employee ID | `staff.staff_id` | Unique identifier of a staff member. |
| Staff name | `staff.first_name`, `staff.last_name` | First and last name of a staff member. |
| Staff email | `staff.email` | Email address of a staff member. |
| Staff active status | `staff.active` | Active-status field for staff. Do not assume a specific value unless supported by the data/business rules. |
| Category / Genre | `category` | A film category. "Genre" is a likely user synonym for category. |
| Category name / Genre name | `category.name` | Name of a film category. |
| Actor / Cast member | `actor` | An actor associated with films. "Cast member" may be used as a synonym. |
| Actor name | `actor.first_name`, `actor.last_name` | First and last name of an actor. |
| Address | `address` | A postal address linked to a city. |
| City | `city` | A city linked to a country. |
| Country | `country` | A country in the address hierarchy. |
| Postal code / ZIP code | `address.postal_code` | Postal code stored for an address. |
| Phone number | `address.phone` | Phone number stored for an address. |
| District | `address.district` | District stored for an address. |
| Language | `language` | A language referenced by films. |
| Number of customers | `COUNT(customer.customer_id)` | A derived count of customer rows; use when the user asks how many customers there are. |
| Number of rentals | `COUNT(rental.rental_id)` | A derived count of rental transactions. |
| Number of payments | `COUNT(payment.payment_id)` | A derived count of payment records. |
| Total payment amount | `SUM(payment.amount)` | A derived total of recorded payment amounts. Use only when the user's wording asks for total/sum/payment amount. |
| Average payment amount | `AVG(payment.amount)` | A derived average of recorded payment amounts. |
| Number of films | `COUNT(film.film_id)` | A derived count of film records. |
| Number of inventory copies | `COUNT(inventory.inventory_id)` | A derived count of inventory-copy records. |
| Number of actors | `COUNT(actor.actor_id)` | A derived count of actor records. |
| Number of staff | `COUNT(staff.staff_id)` | A derived count of staff records. |
| Rental activity | `rental.rental_date` | Rental activity represented by rental transactions and their creation timestamps. |
| Payment activity | `payment.payment_date` | Payment activity represented by payment records and their timestamps. |
| Customer location | `customer` → `address` → `city` → `country` | Customer geographic information through the documented address hierarchy. |
| Store location | `store` → `address` → `city` → `country` | Store geographic information through the documented address hierarchy. |
| Films by actor | `film_actor` → `film` / `actor` | Films associated with an actor through the bridge table. |
| Actors in a film | `film_actor` → `actor` / `film` | Actors associated with a film through the bridge table. |
| Films by category | `film_category` → `film` / `category` | Films associated with a film category through the documented bridge table. |
| Category films | `film_category` → `category` / `film` | Films belonging to a category through the documented bridge table. |
| Store-owned customers | `customer.store_id` | Customers assigned to a store. Must respect the active store RLS scope. |
| Store-owned inventory | `inventory.store_id` | Inventory copies belonging to a store. Must respect the active store RLS scope. |
| Store-owned staff | `staff.store_id` | Staff assigned to a store. Must respect the active store RLS scope. |
| Store rentals | `rental` → `inventory` → `inventory.store_id` | Rentals associated with a store through the documented inventory path. |
| Store payments | `payment` → `customer` → `customer.store_id` | Payments associated with a store through the documented customer path. |
| Rentals by customer | `rental.customer_id` → `customer.customer_id` | Rental transactions associated with a customer. |
| Payments by customer | `payment.customer_id` → `customer.customer_id` | Payments associated with a customer. |
| Rentals by film | `rental` → `inventory` → `film` | Rental transactions associated with a film through inventory. |
| Rentals by category | `rental` → `inventory` → `film` → `film_category` → `category` | Rental transactions associated with a film category through the documented bridge/path. |
| Payments by rental | `payment.rental_id` → `rental.rental_id` | Payments associated with a rental when the payment has a rental reference. |
| Rentals by staff | `rental.staff_id` → `staff.staff_id` | Rental transactions associated with a staff member. |
| Payments by staff | `payment.staff_id` → `staff.staff_id` | Payments associated with a staff member. |
| Films by language | `film.language_id` → `language.language_id` | Films grouped or filtered by their language. |
| Films by original language | `film.original_language_id` → `language.language_id` | Films grouped or filtered by their original language. |

---

## 4. Supported Metrics

Use these metrics only when the user's wording clearly requests the corresponding concept.

| Metric | SQL expression | Source | Typical semantic meaning |
|---|---|---|---|
| Customer Count | `COUNT(customer.customer_id)` | `customer` | Number of customers |
| Rental Count | `COUNT(rental.rental_id)` | `rental` | Number of rentals |
| Payment Count | `COUNT(payment.payment_id)` | `payment` | Number of payments |
| Total Payment Amount | `SUM(payment.amount)` | `payment` | Total recorded payment amount |
| Average Payment Amount | `AVG(payment.amount)` | `payment` | Average recorded payment amount |
| Film Count | `COUNT(film.film_id)` | `film` | Number of films |
| Inventory Count | `COUNT(inventory.inventory_id)` | `inventory` | Number of copies |
| Actor Count | `COUNT(actor.actor_id)` | `actor` | Number of actors |
| Staff Count | `COUNT(staff.staff_id)` | `staff` | Number of staff |

Do not silently substitute one metric for another. For example, "best customer" is not a defined metric by itself and should not automatically mean highest payment or highest rental count.

---

## 5. Ranking Semantics

Common ranking phrases can be translated semantically when the metric is explicit:

- `top N` → descending order for the requested metric with an appropriate result limit.
- `bottom N` → ascending order for the requested metric with an appropriate result limit.
- `highest` / `largest` / `most` → descending order for the requested metric.
- `lowest` / `smallest` / `least` → ascending order for the requested metric.
- `latest` / `most recent` → descending order on the relevant documented datetime column.
- `oldest` / `earliest` → ascending order on the relevant documented datetime column.

Do not invent the ranking metric when the question is ambiguous. "Show the best customers" does not define whether "best" means most rentals, highest payment amount, or another metric.

---

## 6. Date and Time Semantics

Use the date column that matches the user's wording:

| User wording | Database field |
|---|---|
| rental date / rented on / rental activity date | `rental.rental_date` |
| return date / returned on | `rental.return_date` |
| payment date / paid on | `payment.payment_date` |
| customer registration / customer created | `customer.create_date` |
| film release year | `film.release_year` |

Supported temporal patterns:

- today
- yesterday
- this month
- last month
- this year
- last year
- after a date
- before a date
- between two dates
- during a specified period
- recent / latest, when a relevant datetime column is clear

Do not invent date semantics such as fiscal year, business day, month-to-date, or rolling-period definitions unless they are explicitly defined by the user or another authoritative business rule.

---

## 7. NULL and Missing-Value Semantics

`rental.return_date` may be null.

Therefore:

- unreturned rentals
- rentals not returned
- pending returns

can be interpreted as:

`rental.return_date IS NULL`

Do not assume that other nullable or status fields have business meanings that are not documented.

---

## 8. Supported Join-Intent Patterns

Use only schema-supported relationship paths.

| User intent | Supported path |
|---|---|
| customers by store | `customer → store` |
| customer location | `customer → address → city → country` |
| store location | `store → address → city → country` |
| rentals by film | `rental → inventory → film` |
| rentals by store | `rental → inventory → store` |
| payments by customer | `payment → customer` |
| payments by store | `payment → customer → store` or documented rental/inventory path where appropriate |
| films by actor | `film → film_actor → actor` |
| actors in a film | `film → film_actor → actor` |
| films by category | `film → film_category → category` |
| films by language | `film → language` |
| rentals by customer | `rental → customer` |
| payments by rental | `payment → rental` |
| rentals by staff | `rental → staff` |
| payments by staff | `payment → staff` |

Do not create a join simply because two entities sound related. The schema is authoritative.

---

## 9. Business-Definition Boundaries and Ambiguity

The semantic model must recognize when a business term does not define a unique interpretation.

### Ambiguous terms

- `best customers` → metric not specified.
- `popular movies` → popularity metric not specified.
- `best employees` → metric not specified.
- `available movies` → availability rule is not defined.
- `revenue` / `sales` / `income` → not separately defined business metrics; use recorded `payment.amount` only when the intended meaning is clearly total recorded payments.
- `overdue rentals` → no overdue-duration or due-date business rule is defined.
- `profit` → no cost/profit formula is defined.

When a phrase is ambiguous, do not invent a column, metric, formula, relationship, or business rule.

### Unsupported business calculations

The following are not defined by the supplied business semantics:

- profit
- net revenue
- overdue fees
- customer lifetime value
- inventory availability
- utilization rate
- churn rate
- customer satisfaction
- revenue growth
- sales target
- customer segment
- due date
- late fee

If the user asks for one of these, the semantic layer should not fabricate a business definition. It should only support the request if the user supplies a precise definition that can be expressed using the available schema.

### Business interpretation boundaries

- "Revenue", "sales", "income", and "collected money" are not separately defined business metrics in the source materials. The safest supported interpretation is recorded `payment.amount`, but no additional revenue rules should be invented.
- "Available movies/copies" is not explicitly defined as a business metric. Do not invent an availability rule unless the user specifies one.
- "Popular movie", "best customer", "top employee", "best category", or similar ranking language is ambiguous until the metric is clear.
- Do not invent relationships between tables.
- Do not treat `film_text` as a replacement for `film` unless the requested columns are actually present there.
- Do not assume the values of `customer.active` or `staff.active` beyond what the stored schema exposes.
- Do not invent date semantics such as "business day", "fiscal year", or "month-to-date" unless explicitly defined elsewhere.
- Do not invent calculations such as profit, net revenue, customer lifetime value, utilization rate, or overdue fees because the supplied schema/glossary does not define them.

---

## 10. Semantic Layer Principle

The Business Class answers:

> "What does the user's business language mean?"

It should not be responsible for:

> "What SQL syntax is allowed?"

or:

> "How is RLS mechanically enforced?"

or:

> "Which test/example questions should be used?"

Those concerns belong in the companion reference/policy file.