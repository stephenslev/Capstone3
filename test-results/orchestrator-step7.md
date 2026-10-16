# Step 7 Orchestrator Test Results

## rds_1 — PASS
- Type: RDS alone
- Question: Please report how many.
- Route: sql
- Answer: RDS fact: 42 active projects [rds:test-fixture].
- Validation: Passed

## rds_2 — PASS
- Type: RDS alone
- Question: Show the how many results.
- Route: sql
- Answer: RDS fact: 42 active projects [rds:test-fixture].
- Validation: Passed

## docs_1 — PASS
- Type: Documents alone
- Question: Explain the policy.
- Route: retrieval
- Answer: Document fact: onboarding has three steps [document:test-fixture].
- Validation: Passed

## docs_2 — PASS
- Type: Documents alone
- Question: Describe the policy.
- Route: retrieval
- Answer: Document fact: onboarding has three steps [document:test-fixture].
- Validation: Passed

## both_1 — PASS
- Type: Both sources
- Question: Compare how many with the policy.
- Route: both
- Answer: RDS fact: 42 active projects [rds:test-fixture]. Document fact: onboarding has three steps [document:test-fixture].
- Validation: Passed

## both_2 — PASS
- Type: Both sources
- Question: Explain the policy and report how many.
- Route: both
- Answer: RDS fact: 42 active projects [rds:test-fixture]. Document fact: onboarding has three steps [document:test-fixture].
- Validation: Passed

## unsafe_sql — PASS
- Type: Unsafe SQL
- Question: Delete all records; also report how many.
- Route: blocked
- Answer: I was unable to find relevant information to answer this question.
- Validation: Passed

## unanswerable — PASS
- Type: Neither source
- Question: ZXQ_UNANSWERABLE: explain why Lamar Jackson is the goat.
- Route: retrieval
- Answer: I was unable to find relevant information to answer this question.
- Validation: Passed
