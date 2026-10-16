# filename: tool_registry.py

from agents.sql_agent import run_sql_agent
from agents.retrieval_agent import run_retrieval_agent


TOOL_REGISTRY = {
    "sql_agent": {
        "function": run_sql_agent,
        "keywords": [
            "how many", "count", "total", "average", "sum", "revenue",
            "how much", "list all", "which clients", "projects", "invoices",
            "consultants", "compare", "trend", "budget",
        ],
        "schema": {
            "name": "sql_agent",
            "description": (
                "Query structured RDS records about clients, projects, "
                "consultants, and invoices. Use for counts, budgets, statuses, "
                "and billing questions. Do not use for document text, policies, "
                "or procedures."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"}
                },
                "required": ["question"],
            },
        },
    },
    "retrieval_agent": {
        "function": run_retrieval_agent,
        "keywords": [
            "policy", "process", "procedure", "methodology", "what is",
            "explain", "describe", "guidelines", "approach", "onboarding",
        ],
        "schema": {
            "name": "retrieval_agent",
            "description": (
                "Search indexed documents for policies, processes, procedures, "
                "guidelines, and narrative information. Do not use for live "
                "counts, totals, or other structured RDS queries."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"}
                },
                "required": ["question"],
            },
        },
    },
}


def get_all_schemas() -> list:
    return [tool["schema"] for tool in TOOL_REGISTRY.values()]


def call_tool(tool_name: str, question: str) -> dict:
    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        return {
            "success": False,
            "answer": f"Unknown tool: {tool_name}",
            "sources": [],
            "metadata": {},
        }

    return tool["function"](question)

