# Building the Orchestrator

**Session Time:** 90–120 minutes (full lesson — Agent Tool Design folded in)

## Prerequisites

- Multi-Agent Architectures (this morning)
- Connect SQL Agent and Retrieval Agent to a Shared Tool Registry lab (Day 3)

## Table of Contents

- [Building the Orchestrator](#building-the-orchestrator)
  - [Prerequisites](#prerequisites)
  - [Table of Contents](#table-of-contents)
  - [Learning Objectives](#learning-objectives)
  - [Part 1: Setup](#part-1-setup)
  - [Part 2: Defining the Orchestrator State](#part-2-defining-the-orchestrator-state)
  - [Part 3: The Router Node](#part-3-the-router-node)
  - [Part 4: Agent Tool Design](#part-4-agent-tool-design)
    - [Activity: Audit Your Own Tool Descriptions](#activity-audit-your-own-tool-descriptions)
  - [Part 5: The Worker Nodes](#part-5-the-worker-nodes)
  - [Part 6: The Synthesis Node](#part-6-the-synthesis-node)
  - [Part 7: Assembling the Graph](#part-7-assembling-the-graph)
  - [Part 8: Testing the Full Orchestrator](#part-8-testing-the-full-orchestrator)
  - [Resources](#resources)

## Learning Objectives

- Build a LangGraph orchestrator that routes between two specialist agents
- Apply agent tool design principles so routing decisions are reliable
- Implement a synthesis step that combines multiple agent outputs into one cited answer
- Test an orchestrator against questions requiring one agent, the other, or both

## Part 1: Setup

Bring together your code from Day 2, Day 3, and yesterday's Shared Tool Registry lab into one project:

```powershell
pip install langgraph langchain-core langchain-anthropic anthropic --break-system-packages
```

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
import anthropic
from agents.sql_agent import run_sql_agent
from agents.retrieval_agent import run_retrieval_agent
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic()
```

## Part 2: Defining the Orchestrator State

```python
class OrchestratorState(TypedDict):
    question: str
    route: Optional[str]
    sql_result: Optional[dict]
    retrieval_result: Optional[dict]
    final_answer: Optional[str]
    token_usage: Optional[dict]
```

Notice this state carries both raw agent results (`sql_result`, `retrieval_result`) separately, rather than merging them early — the synthesis node needs access to both independently to combine them correctly.

## Part 3: The Router Node

```python
SQL_KEYWORDS = [
    "how many", "count", "total", "average", "sum", "revenue",
    "how much", "list all", "which clients", "projects", "invoices",
    "consultants", "compare", "trend", "budget"
]
DOC_KEYWORDS = [
    "policy", "process", "procedure", "methodology", "what is",
    "explain", "describe", "guidelines", "approach", "onboarding"
]

def route_question(state: OrchestratorState) -> OrchestratorState:
    question = state["question"].lower()
    is_sql = any(k in question for k in SQL_KEYWORDS)
    is_doc = any(k in question for k in DOC_KEYWORDS)

    if is_sql and is_doc:
        route = "both"
    elif is_sql:
        route = "sql"
    else:
        route = "retrieval"

    return {**state, "route": route}
```

> **Note:** This is the same keyword-based approach from Module 2's LangGraph lesson. It's simple, transparent, and debuggable — good qualities for a bootcamp context. A production system might use a Claude call for classification instead, trading a small amount of latency and cost for better handling of genuinely ambiguous questions. Both approaches are valid engineering choices depending on the system's needs.

## Part 4: Agent Tool Design

Before writing the worker nodes, it's worth being explicit about what makes a tool description effective for routing — this is the "Agent Tool Design" content folded into this lesson.

**Bad tool description** (too vague):
```
"description": "Handles data questions"
```

**Good tool description** (specific about scope and boundaries):
```
"description": "Query the relational database for structured, numeric, or categorical
data about clients, projects, consultants, and invoices — counts, totals, statuses,
and comparisons. Do not use for policy or procedural questions."
```

Notice the good version does two things the bad version doesn't: it names the specific domain (clients, projects, consultants, invoices), and it explicitly states what it's *not* for. Both pieces improve routing reliability — the second piece is easy to forget but genuinely helps the router (or a Claude-based classifier) avoid miscategorizing edge cases.

### Activity: Audit Your Own Tool Descriptions

Pull the tool schemas from yesterday's shared tool registry. For each one, check: does it name specific domain terms, and does it state what it's not for? Revise if not.

## Part 5: The Worker Nodes

```python
def call_sql_agent(state: OrchestratorState) -> OrchestratorState:
    if state["route"] not in ["sql", "both"]:
        return state
    result = run_sql_agent(state["question"])
    return {**state, "sql_result": result}

def call_retrieval_agent(state: OrchestratorState) -> OrchestratorState:
    if state["route"] not in ["retrieval", "both"]:
        return state
    result = run_retrieval_agent(state["question"])
    return {**state, "retrieval_result": result}
```

Both worker functions simply call the agents you already built and validated in Day 2 and Day 3 — no new agent logic is written here. This is the payoff of yesterday's interface standardization: the orchestrator doesn't need to know anything about how each agent works internally.

## Part 6: The Synthesis Node

This is the piece that didn't exist before today — combining potentially two separate agent results into one coherent, cited answer.

```python
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

    synthesis = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": (
                f"Using the information below, answer the following question clearly.\n"
                f"Cite which agent(s) and source(s) the information came from.\n\n"
                f"Question: {state['question']}\n\n"
                f"Information:\n{context}"
            )
        }]
    )

    return {
        **state,
        "final_answer": synthesis.content[0].text,
        "token_usage": {
            "input": synthesis.usage.input_tokens,
            "output": synthesis.usage.output_tokens
        }
    }
```

> **✅ Check:** For a "both" routed question, confirm the synthesis node's answer actually draws on *both* agent results — not just whichever one happens to appear first in the context string. Test this explicitly; it's easy for a synthesis prompt to quietly favor one source over another.

## Part 7: Assembling the Graph

```python
def build_orchestrator():
    graph = StateGraph(OrchestratorState)
    graph.add_node("router", route_question)
    graph.add_node("sql_agent", call_sql_agent)
    graph.add_node("retrieval_agent", call_retrieval_agent)
    graph.add_node("synthesiser", synthesise)

    graph.set_entry_point("router")
    graph.add_edge("router", "sql_agent")
    graph.add_edge("sql_agent", "retrieval_agent")
    graph.add_edge("retrieval_agent", "synthesiser")
    graph.add_edge("synthesiser", END)

    return graph.compile()

orchestrator = build_orchestrator()
```

Notice both worker nodes always run in sequence, but each internally checks `state["route"]` and does nothing if it wasn't selected. This is simpler than conditional branching to different node paths and works well for exactly two workers — with more workers, you'd likely want proper conditional edges instead.

## Part 8: Testing the Full Orchestrator

```python
test_questions = [
    "How many active projects do we have?",                                  # sql only
    "What is our onboarding process?",                                        # retrieval only
    "How many active projects do we have, and what's our onboarding policy?", # both
]

for q in test_questions:
    print(f"\n{'='*60}\nQ: {q}")
    result = orchestrator.invoke({
        "question": q, "route": None, "sql_result": None,
        "retrieval_result": None, "final_answer": None, "token_usage": None
    })
    print(f"Route: {result['route']}")
    print(f"Answer: {result['final_answer']}")
    print(f"Tokens: {result['token_usage']}")
```

> **✅ Check:** Confirm the third question — the one requiring both agents — now produces a properly combined answer citing both sources. Compare this directly against yesterday's `suggest_tool` result for the same kind of question, which could only suggest one tool. This comparison is the concrete payoff of today's architecture.

## Resources

- [LangGraph Multi-Agent Systems](https://langchain-ai.github.io/langgraph/concepts/multi_agent/)
- [Anthropic: Tool use best practices](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
