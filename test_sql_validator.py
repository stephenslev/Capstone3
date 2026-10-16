# filename: test_sql_validator.py

from agents.sql_agent import validate_sql

cases = [
    ("valid SELECT", "SELECT id FROM clients", True),
    ("destructive statement", "DELETE FROM clients", False),
    ("blocked word inside column name", "SELECT deleted_at FROM clients", True),
    ("stacked query with blocked keyword", "SELECT 1; DROP TABLE clients", False),
    ("stacked SELECT statements", "SELECT 1; SELECT 2", False),
]

for name, query, expected_valid in cases:
    result = validate_sql(query)
    actual_valid = result["valid"]
    assert actual_valid == expected_valid, (
        f"FAIL: {name}: expected valid={expected_valid}, got {result}"
    )
    print(f"PASS: {name} -> valid={actual_valid}")

print("All 5 validator tests passed.")