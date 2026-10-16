# filename: cost_summary.py

from datetime import datetime
import tokenomics_logger


def log_query_cost(question, result, log_path="tokenomics_cost_summary.txt"):
    sql_result = result.get("sql_result") or {}
    retrieval_result = result.get("retrieval_result") or {}

    sql_tokens = (sql_result.get("metadata") or {}).get("token_usage") or {}
    retrieval_tokens = (
        (retrieval_result.get("metadata") or {}).get("token_usage") or {}
    )
    synthesis_tokens = result.get("token_usage") or {}

    breakdown = tokenomics_logger.calculate_full_query_cost(
        sql_tokens=sql_tokens,
        retrieval_tokens=retrieval_tokens,
        synthesis_tokens=synthesis_tokens,
    )

    component_tokens = {}
    for name, usage in (
        ("SQL", sql_tokens),
        ("Retrieval", retrieval_tokens),
        ("Synthesis", synthesis_tokens),
    ):
        input_count = usage.get("input_tokens", usage.get("input", 0)) or 0
        output_count = usage.get("output_tokens", usage.get("output", 0)) or 0
        component_tokens[name] = int(input_count) + int(output_count)

    most_tokens = max(component_tokens.values(), default=0)
    largest_components = [
        name for name, count in component_tokens.items()
        if count == most_tokens
    ]

    entry = (
        f"Timestamp: {datetime.now().isoformat(timespec='seconds')}\n"
        f"Question: {question}\n"
        f"Route: {result.get('route', 'unknown')}\n"
        f"Total cost: ${breakdown['total_cost']:.6f}\n"
        f"Tokens by component: {component_tokens}\n"
        f"Most tokens: {', '.join(largest_components)} ({most_tokens})\n"
        f"{'-' * 60}\n"
    )

    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(entry)

    return breakdown
