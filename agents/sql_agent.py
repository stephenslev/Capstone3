"""
Real SQL agent wrapper for the orchestrator — replaces the earlier stub now
that a real database (Docker/local Postgres, see build-sql-query-agent/) is
available. Vendors generate_sql()/validate_sql()/execute_query_safely() from
Day 2's Trust but Verify / Add a Validation Layer lessons directly (rather
than importing across a sibling repo) so this package is self-contained and
buildable as a standalone Docker image. Validation is mandatory here for the
same reason multi-agent-architectures-main says it should be: "Validating
SQL — that's already inside the SQL agent, from Day 2's Trust but Verify
lesson" is only true if this file actually calls validate_sql, same as
shared-tool-registry-lab-solution's run_sql_agent does via
validated_agent_solution.validated_sql_agent().
"""
import os
import psycopg2
from bedrock_client import invoke_claude
from response_contract import enforce_response_contract

SCHEMA_CONTEXT = """
Tables available:

- clients(id, name, contact_name, industry, region, contract_value,
  created_date, billing_address)
- projects(id, client_id, name, description, status, start_date, end_date,
  budget)
- consultants(id, project_id, name, email, specialisation, level,
  billable_hours, home_office, start_date)
- invoices(id, project_id, amount, status, due_date, paid_date, invoice_date)

Primary keys:
- clients.id
- projects.id
- consultants.id
- invoices.id

Foreign keys:
- projects.client_id references clients.id.
- consultants.project_id references projects.id and may be NULL.
- invoices.project_id references projects.id.

Field details:
- clients.contract_value, projects.budget, and invoices.amount are monetary
  values in USD.
- created_date, start_date, end_date, due_date, paid_date, and invoice_date
  are DATE fields, stored as dates.
- consultants.start_date is the consultant's firm start date.
- consultants.specialisation is spelled with an 's'.

Allowed values:
- projects.status: 'Planned', 'Active', 'Completed', 'Cancelled'.
- consultants.level: 'Intern', 'Analyst', 'Consultant',
  'Senior Consultant', 'Manager', 'Senior Manager', 'Partner'.
- invoices.status: 'Draft', 'Issued', 'Paid', 'Overdue', 'Cancelled'.

Use PostgreSQL syntax. Column and table names must match this schema.
"""

BLOCKED_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
                    "EXEC", "EXECUTE", "GRANT", "REVOKE"]


def generate_sql(question: str) -> tuple[str, dict]:
    prompt = (
        f"{SCHEMA_CONTEXT}\n\n"
        f"Generate a SQL query to answer: {question}\n\n"
        "Return ONLY the SQL query. No explanation, no markdown, no backticks."
    )
    result = invoke_claude(prompt, max_tokens=512)
    sql = result["text"].strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    return sql, {"input": result["input_tokens"], "output": result["output_tokens"]}


def validate_sql(query: str) -> dict:
    query_upper = query.upper().strip()
    padded = f" {query_upper} "

    for keyword in BLOCKED_KEYWORDS:
        if f" {keyword} " in padded or query_upper.startswith(keyword + " ") or query_upper == keyword:
            return {
                "valid": False,
                "reason": f"Blocked: '{keyword}' is not permitted. Only SELECT queries are allowed."
            }

    if not query_upper.startswith("SELECT"):
        return {
            "valid": False,
            "reason": "Only SELECT queries are permitted. Query must begin with SELECT."
        }

    stripped = query.strip().rstrip(";")
    if ";" in stripped:
        return {
            "valid": False,
            "reason": "Blocked: multiple statements detected (possible stacked query attempt)."
        }

    return {"valid": True, "reason": "OK"}


def execute_query_safely(sql: str) -> dict:
    validation = validate_sql(sql)

    if not validation["valid"]:
        return {"success": False, "error": validation["reason"], "validation": "BLOCKED"}

    try:
        conn = psycopg2.connect(
            host=os.getenv("RDS_HOST"), port=int(os.getenv("RDS_PORT")),
            dbname=os.getenv("RDS_DATABASE"), user=os.getenv("RDS_USER"),
            password=os.getenv("RDS_PASSWORD")
        )
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        conn.close()
        return {"success": True, "columns": cols, "rows": rows, "validation": "PASSED"}
    except Exception as e:
        return {"success": False, "error": str(e), "validation": "EXECUTION_ERROR"}

@enforce_response_contract("sql_agent")
def run_sql_agent(question: str) -> dict:
    sql, gen_usage = generate_sql(question)
    result = execute_query_safely(sql)

    if not result["success"]:
        return {
            "success": False,
            "answer": f"Query {result['validation'].lower()}: {result['error']}",
            "sources": [f"SQL: {sql}"],
            "metadata": {"row_count": 0, "validation": result["validation"], "token_usage": gen_usage}
        }

    prompt = (
        f"The user asked: {question}\n"
        f"SQL used: {sql}\n"
        f"Columns: {result['columns']}\n"
        f"Data: {result['rows'][:20]}\n\n"
        "Provide a clear, concise natural-language answer based on this data."
    )
    interpretation = invoke_claude(prompt, max_tokens=500)
    token_usage = {
        "input": gen_usage["input"] + interpretation["input_tokens"],
        "output": gen_usage["output"] + interpretation["output_tokens"]
    }
    return {
        "success": True,
        "answer": interpretation["text"],
        "sources": [f"SQL: {sql}"],
        "metadata": {"row_count": len(result["rows"]), "validation": result["validation"], "token_usage": token_usage}
    }
