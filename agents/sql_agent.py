"""
Real SQL agent wrapper for the orchestrator — replaces the earlier stub now
that a real database (Docker/local Postgres, see build-sql-query-agent/) is
available. Wraps build-sql-query-agent's functions into the
{success, answer, sources, metadata} shape synthesise() expects.
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "build-sql-query-agent"))
from sql_agent import generate_sql, execute_query
from bedrock_client import invoke_claude


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
