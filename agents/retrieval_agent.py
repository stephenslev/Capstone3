"""
Real, already-validated retrieval agent (same code tested earlier this
session against the shared vector-search-lesson OpenSearch domain).
Recreated here after the local Downloads reset wiped the original files.
"""
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from sentence_transformers import SentenceTransformer
from bedrock_client import invoke_claude

HOST = "search-vector-search-lesson-a3enhrb4w4wuu2w5vv52whqu2q.us-east-1.es.amazonaws.com"
REGION = "us-east-1"

_embed_model = None


def get_embedding(text: str) -> list[float]:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model.encode(text).tolist()


def get_opensearch_client():
    credentials = boto3.Session().get_credentials()
    auth = AWS4Auth(credentials.access_key, credentials.secret_key,
                     REGION, "es", session_token=credentials.token)
    return OpenSearch(
        hosts=[{"host": HOST, "port": 443}],
        http_auth=auth, use_ssl=True, verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def retrieve(question: str, top_k: int = 5) -> list[dict]:
    query_vector = get_embedding(question)
    client = get_opensearch_client()
    response = client.search(
        index="documents",
        body={"size": top_k, "query": {"knn": {"embedding": {"vector": query_vector, "k": top_k}}}}
    )
    return [
        {"content": hit["_source"]["content"], "source": hit["_source"]["source"], "score": hit["_score"]}
        for hit in response["hits"]["hits"]
    ]


def generate_cited_answer(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join([f"[Source {i+1}: {c['source']}]\n{c['content']}" for i, c in enumerate(chunks)])
    prompt = (
        "Answer the question using ONLY the context provided below. "
        "If the answer is not in the context, say 'I cannot find this information in the provided documents.' "
        "Always cite the source number(s) you used.\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:"
    )
    return invoke_claude(prompt, max_tokens=500)["text"]


def check_grounding(answer: str, chunks: list[dict]) -> bool:
    import re
    cited_sources = re.findall(r"Source (\d+)", answer)
    if not cited_sources:
        return "cannot find" in answer.lower()
    return all(1 <= int(s) <= len(chunks) for s in cited_sources)


def run_retrieval_agent(question: str) -> dict:
    chunks = retrieve(question)
    if not chunks:
        return {"success": False, "answer": "No relevant documents found.", "sources": [], "metadata": {"chunk_count": 0, "grounded": False}}

    answer = generate_cited_answer(question, chunks)
    return {
        "success": True,
        "answer": answer,
        "sources": [c["source"] for c in chunks],
        "metadata": {"chunk_count": len(chunks), "grounded": check_grounding(answer, chunks)}
    }
