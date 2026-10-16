# tokenomics_logger.py
import json
from datetime import datetime


def log_decision(stage: str, question: str, details: dict):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "stage": stage,
        "question": question,
        "details": details
    }
    print(f"[LOG] {stage}: {json.dumps(details)}")
    with open("agent_decisions.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

def route_question_logged(state):
    from orchestrator import route_question
    result = route_question(state)  # your existing routing logic from this morning
    log_decision("routing", state["question"], {"route": result["route"]})
    return result

# tokenomics_logger.py (continued)
import uuid

def run_traced_query(orchestrator, question: str) -> dict:
    trace_id = str(uuid.uuid4())[:8]

    log_decision("query_start", question, {"trace_id": trace_id})

    result = orchestrator.invoke({
        "question": question, "route": None, "sql_result": None,
        "retrieval_result": None, "final_answer": None, "token_usage": None
    })

    log_decision("query_complete", question, {
        "trace_id": trace_id,
        "route": result["route"],
        "sql_validation": result.get("sql_result", {}).get("metadata", {}).get("validation") if result.get("sql_result") else None,
        "retrieval_chunk_count": len(result.get("retrieval_result", {}).get("sources", [])) if result.get("retrieval_result") else None,
        "token_usage": result.get("token_usage")
    })

    return result

COST_PER_1K_INPUT = 0.003
COST_PER_1K_OUTPUT = 0.015

def calculate_full_query_cost(sql_tokens: dict, retrieval_tokens: dict, synthesis_tokens: dict) -> dict:
    def cost(tokens):
        return (tokens.get("input_tokens", tokens.get("input", 0)) / 1000 * COST_PER_1K_INPUT +
                tokens.get("output_tokens", tokens.get("output", 0)) / 1000 * COST_PER_1K_OUTPUT)

    sql_cost = cost(sql_tokens) if sql_tokens else 0
    retrieval_cost = cost(retrieval_tokens) if retrieval_tokens else 0
    synthesis_cost = cost(synthesis_tokens) if synthesis_tokens else 0
    total = sql_cost + retrieval_cost + synthesis_cost

    return {
        "sql_agent_cost": round(sql_cost, 6),
        "retrieval_agent_cost": round(retrieval_cost, 6),
        "synthesis_cost": round(synthesis_cost, 6),
        "total_cost": round(total, 6),
        "cost_per_1000_queries": round(total * 1000, 2)
    }


