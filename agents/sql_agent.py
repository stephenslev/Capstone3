"""
Real SQL agent wrapper for the orchestrator — replaces the earlier stub now
that a real database (Docker/local Postgres, see build-sql-query-agent/) is
available. Vendors generate_sql()/execute_query() from build-sql-query-agent
directly (rather than importing across a sibling repo) so this package is
self-contained and buildable as a standalone Docker image.
"""
import os
import psycopg2
from bedrock_client import invoke_claude

SCHEMA_CONTEXT = """
Tables available:
- clients(id, name, industry, region, contract_value, created_date)
- projects(id, client_id, name, status, start_date, end_date, budget)
- consultants(id, name, grade, specialisation, project_id, billable_hours)
- invoices(id, project_id, amount, status, due_date, paid_date)

All monetary values are in USD. Dates are in ISO 8601 format.
status in projects is one of: 'active', 'completed', 'on-hold'.
"""


def generate_sql(question: str) -> str:
    prompt = (
        f"{SCHEMA_CONTEXT}\n\n"
        f"Generate a SQL query to answer: {question}\n\n"
        "Return ONLY the SQL query. No explanation, no markdown, no backticks."
    )
    result = invoke_claude(prompt, max_tokens=512)
    sql = result["text"].strip()
    return sql.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()


def execute_query(sql: str) -> dict:
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
        return {"success": True, "columns": cols, "rows": rows}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_sql_agent(question: str) -> dict:
    sql = generate_sql(question)
    result = execute_query(sql)

    if not result["success"]:
        return {
            "success": False,
            "answer": f"Query failed: {result['error']}",
            "sources": [f"SQL: {sql}"],
            "metadata": {"row_count": 0}
        }

    prompt = (
        f"The user asked: {question}\n"
        f"SQL used: {sql}\n"
        f"Columns: {result['columns']}\n"
        f"Data: {result['rows'][:20]}\n\n"
        "Provide a clear, concise natural-language answer based on this data."
    )
    interpretation = invoke_claude(prompt, max_tokens=500)
    return {
        "success": True,
        "answer": interpretation["text"],
        "sources": [f"SQL: {sql}"],
        "metadata": {"row_count": len(result["rows"])}
    }
