# Building the Orchestrator

## Introduction

This morning you named the gap: a single agent with two tools doesn't reliably use both. This afternoon you close it, and the interesting part isn't any single node in the graph — it's watching state accumulate across steps that stay decoupled from each other. The router only classifies. Each worker only checks whether it was asked to run. The synthesizer only combines whatever results actually showed up. No node needs to understand what any other node did, which is exactly why this scales past two workers in a way a hand-written `while` loop wouldn't. By Part 8, you'll run the same "both" question that only ever got a single-tool answer from yesterday's `suggest_tool`, and see it correctly draw on both sources this time — a direct, concrete before-and-after for the architecture this whole two-day arc has been building toward.

## Prerequisites

- Multi-Agent Architectures (this morning)
- Connect SQL Agent and Retrieval Agent to a Shared Tool Registry lab (Day 3)

## Table of Contents

- [Building the Orchestrator](#building-the-orchestrator)
  - [Introduction](#introduction)
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
  - [Running in Docker](#running-in-docker)
  - [Resources](#resources)

## Learning Objectives

By the end of this lesson, students will be able to:
- Build a LangGraph orchestrator that routes questions to appropriate specialist agents
- Apply agent tool-design principles to improve routing decisions based on tool scope and boundaries
- Implement a synthesis step that combines results from multiple specialist agents into a coherent, cited response
- Evaluate an orchestrator using single-agent and multi-agent questions and identify routing or synthesis failures
- Analyze common multi-agent failure modes, including incomplete routing, synthesis errors, redundant calls, and cascading failures

## Part 1: Setup

Bring together your code from Day 2, Day 3, and yesterday's Shared Tool Registry lab into one project. Create a new file, `orchestrator.py`, in the **same directory** where your existing `bedrock_client.py` and `agents/` package (containing `sql_agent.py` and `retrieval_agent.py`) already live from those earlier labs — this file imports them directly, so it should be created in the same project directory as the existing modules. Every code block from Parts 2, 3, 5, 6, and 7 below builds on the ones before it and belongs in this same file, added in order (Part 4 is a design discussion with no code to add).

```bash
pip install langgraph boto3 python-dotenv --break-system-packages
```

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from bedrock_client import invoke_claude
from agents.sql_agent import run_sql_agent
from agents.retrieval_agent import run_retrieval_agent
from dotenv import load_dotenv
load_dotenv()
```

> **This calls Claude via Bedrock, not the direct Anthropic SDK** — same as every other lab this week. `langchain-core` and `langchain-anthropic` aren't needed here either; this orchestrator is built directly with `langgraph` and your own `bedrock_client.py` helper, not LangChain's Anthropic integration.

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

By this point, `orchestrator.py` should contain, in order: Part 1's imports, Part 2's `OrchestratorState`, Part 3's `route_question`, Part 5's `call_sql_agent`/`call_retrieval_agent`, Part 6's `synthesise`, and Part 7's `build_orchestrator()` plus the `orchestrator = build_orchestrator()` line. Add the block below to the end of that file — this is what actually runs the graph and prints results:

```python
if __name__ == "__main__":
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

> **Why the `if __name__ == "__main__":` guard matters here, specifically:** this afternoon's Deployment Patterns on AWS lesson wraps this file in a Lambda handler with `from orchestrator import build_orchestrator`. Without this guard, that import re-runs all 3 test questions — real Bedrock, database, and OpenSearch calls — on every single Lambda cold start, before the handler is even callable. Same reasoning applies any time this module gets imported rather than run directly, including this afternoon's tokenomics lesson.

Run it from your terminal:

```bash
python3 orchestrator.py
```

You should see all three test questions printed with their route, final answer, and token usage.

> **✅ Check:** Confirm the third question — the one requiring both agents — now produces a properly combined answer citing both sources. Compare this directly against yesterday's `suggest_tool` result for the same kind of question, which could only suggest one tool. This comparison is the concrete payoff of today's architecture.

## Running in Docker

This lesson environment can run in a container instead of a local Python install — useful since `retrieval_agent.py`'s `sentence-transformers` dependency pulls in a full PyTorch install.

### One-time setup: Docker permissions

If `docker compose build` fails with a `permission denied` error connecting to the Docker daemon, your user isn't in the `docker` group yet. Fix it once:

```bash
sudo usermod -aG docker $USER
```

Then log out and back in (or run `newgrp docker` in your current terminal) for the group change to take effect. After that, every `docker compose` command below works without `sudo`.

> **If you can't add yourself to the `docker` group** (locked-down environment) and must keep using `sudo docker compose ...`: `sudo` resets `$HOME` to `/root` by default, which breaks the `~/.aws` mount below silently (it mounts an empty/nonexistent directory instead of your real credentials). Use `sudo -E docker compose ...` instead — the `-E` flag preserves your environment, including `$HOME`, so `~` still resolves to your own home directory.

```bash
docker compose build
```

Provide AWS credentials for the locked-down IAM identity either as environment variables before running, or by mounting `~/.aws` (already enabled in `docker-compose.yml`):

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...   # if using temporary credentials
docker compose run --rm orchestrator
```

The working directory is bind-mounted into the container, so edits to `orchestrator.py` or `agents/` take effect without rebuilding the image — only rebuild after changing `requirements.txt`. The `sentence-transformers` model cache is kept in a named volume (`hf-cache`) so it downloads once, not on every run.

## Resources

- [LangGraph Multi-Agent Systems](https://langchain-ai.github.io/langgraph/concepts/multi_agent/)
- [Anthropic: Tool use best practices](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
