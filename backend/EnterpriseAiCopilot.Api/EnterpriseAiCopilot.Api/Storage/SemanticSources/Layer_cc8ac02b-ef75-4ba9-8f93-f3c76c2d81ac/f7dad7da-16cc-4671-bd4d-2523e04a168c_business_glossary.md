# Banking Business Glossary

This glossary provides business-friendly meanings for terms used in the synthetic banking schema.

| Business Term | Database Mapping | Meaning |
|---|---|---|
| Customer | `customers` | A person represented in the banking system. |
| Customer ID | `customers.customer_id` | Unique identifier for a customer. |
| Credit Score | `customers.credit_score` | Numeric score stored for the customer's credit profile. |
| Branch | `branches` | A banking branch represented in the database. |
| Account | `accounts` | A banking account owned by a customer. |
| Account Type | `accounts.account_type` | Category/type of the bank account. |
| Account Balance | `accounts.balance_usd` | Balance value associated with an account, in USD. |
| Account Opening Date | `accounts.open_date` | Date on which an account was opened. |
| Card | `cards` | A card associated with a bank account. |
| Card Type | `cards.card_type` | Type/category of the card. |
| Merchant | `merchants` | A merchant referenced by transactions. |
| Transaction | `transactions` | A financial transaction associated with an account and merchant. |
| Transaction Amount | `transactions.amount_usd` | Monetary amount of a transaction, in USD. |
| Transaction Date | `transactions.transaction_date` | Date and time when the transaction occurred. |
| Loan | `loans` | A loan record associated with a customer. |
| Loan Amount | `loans.loan_amount` | Principal amount of a loan, in USD. |
| Interest Rate | `loans.interest_rate` | Interest-rate value stored for a loan. |
| Loan Start Date | `loans.start_date` | Date on which a loan starts. |
| Transaction Volume | Derived from `transactions.amount_usd` | Sum of transaction amounts over a selected population/time period. |
| Total Balance | Derived from `accounts.balance_usd` | Sum of account balances over a selected population. |
| Loan Exposure | Derived from `loans.loan_amount` | Sum of loan amounts over a selected population. |

## Join Paths

### Customer → Transactions
`customers → accounts → transactions`

### Customer → Cards
`customers → accounts → cards`

### Customer → Loans
`customers → loans`

### Branch → Transactions
`branches → accounts → transactions`

### Merchant → Customer
`merchants → transactions → accounts → customers`

## Ambiguity Rules

- When a user asks for **customer transactions**, join through `accounts`.
- When a user asks for **customer cards**, join through `accounts`.
- When a user asks for **customer loans**, use the direct `loans.customer_id` relationship.
- When calculating **transaction volume**, aggregate `transactions.amount_usd`.
- When calculating **total balance**, aggregate `accounts.balance_usd`.
- Do not join `loans` directly to `accounts` because no such relationship is defined in the supplied schema.
