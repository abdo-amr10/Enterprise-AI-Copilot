# Synthetic Banking Database — Semantic Layer Documentation

## Source of Truth

This semantic metadata follows the uploaded **Database Test Schema**.

## Tables

The database contains seven tables:

- `customers`
- `branches`
- `accounts`
- `cards`
- `merchants`
- `transactions`
- `loans`

## Relationships

The schema defines these 1:N relationships:

1. `customers.customer_id` → `accounts.customer_id`
2. `branches.branch_id` → `accounts.branch_id`
3. `accounts.account_id` → `cards.account_id`
4. `accounts.account_id` → `transactions.account_id`
5. `merchants.merchant_id` → `transactions.merchant_id`
6. `customers.customer_id` → `loans.customer_id`

## Semantic Join Paths

- Customer → Accounts → Transactions
- Customer → Accounts → Cards
- Customer → Loans
- Branch → Accounts → Transactions
- Merchant → Transactions → Accounts → Customer

## Important Fields

- `accounts.balance_usd`: account balance value in USD.
- `transactions.amount_usd`: transaction amount in USD.
- `loans.loan_amount`: loan amount in USD.
- `loans.interest_rate`: interest-rate value stored for a loan.
- `transactions.transaction_date`: transaction timestamp.
- `accounts.open_date`: account opening date.

## Text-to-SQL Guidance

Use only the relationships explicitly defined in `relationships.json` when generating JOINs.

Do not invent, infer, or assume relationships that are not explicitly defined in the schema or `relationships.json`, even when column names appear similar.

For customer-level transaction or card queries, join through `accounts`.
For customer-level loan queries, use the direct `customers.customer_id` → `loans.customer_id` relationship.
Do not join `loans` directly to `accounts` because no such relationship is defined.

## Sample Data

`sample_data.json` contains synthetic, referentially complete examples.

The sample records are intentionally aligned across all defined relationships and can be used to validate JOIN logic and Text-to-SQL generation.

The sample dataset is not a representation of the full database and must not be used to infer row counts, distributions, nullability, or business rules that are not explicitly defined in the schema.

All records in `sample_data.json` are synthetic examples and are not presented as raw source rows.
