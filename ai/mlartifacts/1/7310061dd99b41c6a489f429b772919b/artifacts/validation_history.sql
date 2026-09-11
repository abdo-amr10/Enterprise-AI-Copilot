-- ====================================================================
-- QUESTION: Show all active customers with their account balance
-- STATUS: PASSED
-- VALIDATION PASSED: YES
-- ====================================================================

-- --------------------------------------------------------------------
-- [STEP 1] INITIAL LLM GENERATION (Attempt 0)
-- --------------------------------------------------------------------
SELECT c.first_name, c.last_name, a.balance_usd AS account_balance FROM customers AS c INNER JOIN accounts AS a ON c.customer_id = a.customer_id WHERE a.branch_id = @UserBranchId;

-- --------------------------------------------------------------------
-- [STEP 2.1] VALIDATION CHECK (Attempt 0)
-- Status: PASSED
-- --------------------------------------------------------------------
SELECT c.first_name, c.last_name, a.balance_usd AS account_balance FROM customers AS c INNER JOIN accounts AS a ON c.customer_id = a.customer_id WHERE a.branch_id = @UserBranchId;

-- ====================================================================
-- FINAL ACCEPTED SQL QUERY:
-- ====================================================================
SELECT c.first_name, c.last_name, a.balance_usd AS account_balance FROM customers AS c INNER JOIN accounts AS a ON c.customer_id = a.customer_id WHERE a.branch_id = @UserBranchId;
