import json
from app.services import llm, vectorstore


async def answer(user_id: int, language: str, question: str, doc_ids=None, k: int = 5) -> dict:
    qv = (await llm.embed(question)).tolist()
    hits = vectorstore.query(user_id, qv, k=k, doc_ids=doc_ids)
    if not hits:
        return {"answer": "No documents indexed yet. Upload a PDF/URL/YouTube first.",
                "citations": [], "confidence": 0.0}
    context = "\n\n".join(f"[{i+1}] {h['text']}" for i, h in enumerate(hits))
    prompt = (
        f"Use ONLY the context to answer. Cite as [1], [2]. If not answerable from context, say so honestly.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    text = await llm.chat(
        prompt,
        system="You are a grounded study tutor. Cite sources. Be precise.",
        language=language, temperature=0.2,
    )
    # confidence = inverse of best distance, normalized
    best = min(h["distance"] for h in hits) if hits else 1.0
    confidence = max(0.0, min(1.0, 1.0 - best))
    return {
        "answer": text,
        "confidence": round(confidence, 3),
        "citations": [
            {
                "index": i + 1,
                "text": h["text"][:600],
                "doc_id": h["metadata"].get("doc_id"),
                "score": round(1 - h["distance"], 3),
            }
            for i, h in enumerate(hits)
        ],
    }


async def summarize_search(language: str, query: str, results: list[dict]) -> str:
    return await llm.chat(
        f"Summarize for a high schooler researching '{query}':\n{json.dumps(results)[:4500]}",
        system="Concise study assistant. Markdown bullets with [1][2] citations.",
        language=language, temperature=0.3,
    )
