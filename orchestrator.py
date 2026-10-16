from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from bedrock_client import invoke_claude
from agents.sql_agent import run_sql_agent
from agents.retrieval_agent import run_retrieval_agent
from dotenv import load_dotenv
load_dotenv()

import re

from tool_registry import TOOL_REGISTRY

import tokenomics_logger
 
class OrchestratorState(TypedDict):
    question: str
    route: Optional[str]
    sql_result: Optional[dict]
    retrieval_result: Optional[dict]
    final_answer: Optional[str]
    token_usage: Optional[dict]


# SQL_KEYWORDS = [
#     "how many", "count", "total", "average", "sum", "revenue",
#     "how much", "list all", "which clients", "projects", "invoices",
#     "consultants", "compare", "trend", "budget"
# ]
# DOC_KEYWORDS = [
#     "policy", "process", "procedure", "methodology", "what is",
#     "explain", "describe", "guidelines", "approach", "onboarding"
# ]
 
def route_question(state: OrchestratorState) -> OrchestratorState:
    question = state["question"].lower()

    if re.search(r"\b(delete|drop|truncate|insert|update|alter)\b", question):
        return {**state, "route": "blocked"}
    
    is_sql = any(k in question for k in TOOL_REGISTRY["sql_agent"]["keywords"])
    is_doc = any(k in question for k in TOOL_REGISTRY["retrieval_agent"]["keywords"])
 
    if is_sql and is_doc:
        route = "both"
    elif is_sql:
        route = "sql"
    else:
        route = "retrieval"
 
    return {**state, "route": route}
 
def call_sql_agent(state: OrchestratorState) -> OrchestratorState:
    if state["route"] not in ["sql", "both"]:
        return state
    result = TOOL_REGISTRY["sql_agent"]["function"](state["question"])
    return {**state, "sql_result": result}
 
def call_retrieval_agent(state: OrchestratorState) -> OrchestratorState:
    if state["route"] not in ["retrieval", "both"]:
        return state
    result = TOOL_REGISTRY["retrieval_agent"]["function"](state["question"])
    return {**state, "retrieval_result": result}
 
def synthesise(state: OrchestratorState) -> OrchestratorState:
    context = ""
 
    if state.get("sql_result") and state["sql_result"].get("success"):
        r = state["sql_result"]
        context += f"SQL Agent Result:\n{r['answer']}\nSources: {r['sources']}\n\n"
 
    if state.get("retrieval_result") and state["retrieval_result"].get("success"):
        r = state["retrieval_result"]
        context += f"Retrieval Agent Result:\n{r['answer']}\nSources: {r['sources']}\n\n"
 
    if not context:
        return {
            **state,
            "final_answer": "I was unable to find relevant information to answer this question.",
            "token_usage": {"input": 0, "output": 0}
        }
 
    prompt = (
        f"Using the information below, answer the following question clearly.\n"
        f"Cite which agent(s) and source(s) the information came from.\n\n"
        f"Question: {state['question']}\n\n"
        f"Information:\n{context}"
    )
    result = invoke_claude(prompt, max_tokens=800)
 
    return {
        **state,
        "final_answer": result["text"],
        "token_usage": {
            "input": result["input_tokens"],
            "output": result["output_tokens"]
        }
    }

 
def build_orchestrator():
    
 
    graph = StateGraph(OrchestratorState)
    graph.add_node("router", tokenomics_logger.route_question_logged)
    graph.add_node("sql_agent", call_sql_agent)
    graph.add_node("retrieval_agent", call_retrieval_agent)
    graph.add_node("synthesiser", synthesise)
 
    graph.set_entry_point("router")
    graph.add_edge("router", "sql_agent")
    graph.add_edge("sql_agent", "retrieval_agent")
    graph.add_edge("retrieval_agent", "synthesiser")
    graph.add_edge("synthesiser", END)
 
    return graph.compile()
 
 
 
if __name__ == "__main__":
    from cost_summary import log_query_cost
    orchestrator = build_orchestrator()
    test_questions = [
        "How many active projects do we have?",                                  # sql only
        "What is our onboarding process?",                                        # retrieval only
        "How many active projects do we have, and what's our onboarding policy?", # both
    ]

 
    for q in test_questions:
        print(f"\n{'='*60}\nQ: {q}")
        # result = orchestrator.invoke({
        #     "question": q, "route": None, "sql_result": None,
        #     "retrieval_result": None, "final_answer": None, "token_usage": None
        # })
 
        result = tokenomics_logger.run_traced_query(orchestrator, q)
        sql_result = result.get("sql_result")
        retrieval_result = result.get("retrieval_result")
        sql_tokens = (sql_result or {}).get("metadata", {}).get("token_usage", {})
        retrieval_tokens = (retrieval_result or {}).get("metadata", {}).get("token_usage", {})
        synthesis_tokens = result.get("token_usage") or {}
 
        breakdown = log_query_cost(q, result)
 
        print(breakdown)
 
        print(f"Route: {result['route']}")
        print(f"Answer: {result['final_answer']}")
        print(f"Tokens: {result['token_usage']}")