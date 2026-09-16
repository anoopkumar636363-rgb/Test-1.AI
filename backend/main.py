import json
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "backend" / "bis_data.json"
DATA = json.loads(DATA_FILE.read_text(encoding="utf-8"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

app = FastAPI(
    title="BIS AI Assistant API",
    description="SIH26107 prototype: AI-assisted guidance for Indian Standards and BIS services.",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class VerifyRequest(BaseModel):
    license_number: str = Field(min_length=2, max_length=100)


def search_records(query: str):
    q = query.lower().strip()
    results = []
    for item in DATA["standards"]:
        haystack = " ".join(
            [
                item.get("title", ""),
                item.get("product", ""),
                item.get("category", ""),
                item.get("summary", ""),
                " ".join(item.get("keywords", [])),
            ]
        ).lower()
        terms = [x for x in q.split() if len(x) > 2]
        score = sum(1 for term in terms if term in haystack)
        if score:
            results.append((score, item))
    return [item for _, item in sorted(results, key=lambda x: x[0], reverse=True)]


def fallback_answer(question: str):
    matches = search_records(question)
    if matches:
        top = matches[:3]
        lines = ["I found relevant entries in the connected BIS prototype knowledge base:"]
        for item in top:
            lines.append(f"• {item['title']} — {item['summary']}")
        lines.append(
            "\nThis is prototype guidance. Verify the current requirement with an official BIS source before relying on it for certification or compliance."
        )
        return "\n".join(lines), top

    return (
        "I could not find a confident match in the connected BIS knowledge base yet. "
        "Try a product name, IS number, BIS certification question, hallmarking, or testing laboratory query. "
        "For questions requiring current regulatory information, verify the answer against official BIS sources.",
        [],
    )


def ai_answer(question: str):
    if not GEMINI_API_KEY:
        return fallback_answer(question)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)
        matches = search_records(question)[:8]
        context = json.dumps(matches, ensure_ascii=False, indent=2)

        system_instruction = """
You are BIS AI Assistant, a helpful assistant for Indian Standards and BIS services.

Rules:
1. Be helpful and conversational for greetings and general navigation questions.
2. For BIS factual, certification, compliance, standards, fees, deadlines, licence, testing, or legal questions, use the supplied knowledge-base context first.
3. Never invent an IS number, certification requirement, fee, deadline, licence status, laboratory, legal requirement, or BIS policy.
4. If the supplied context is insufficient, explicitly say that the knowledge base does not contain enough verified information.
5. Clearly distinguish prototype/demo data from verified current BIS information.
6. Encourage the user to verify important compliance decisions using the official BIS source.
7. Keep answers concise and easy for students, consumers, and small businesses to understand.
"""

        prompt = f"""
User question:
{question}

Connected knowledge-base context:
{context if context else "No matching knowledge-base records were found."}

Answer the user directly. If this is a simple greeting, respond naturally. If it is a BIS factual question and the context is insufficient, say so rather than guessing.
"""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=800,
            ),
        )

        answer = (response.text or "").strip()
        if not answer:
            return fallback_answer(question)
        return answer, matches

    except Exception:
        answer, matches = fallback_answer(question)
        return (
            answer
            + "\n\nThe Gemini service could not be reached, so the local knowledge-base response was used instead.",
            matches,
        )


@app.get("/api/health")
def health():
    return {
        "status": "online",
        "service": "BIS AI Assistant",
        "ai_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL if GEMINI_API_KEY else None,
    }


@app.get("/api/categories")
def categories():
    return DATA["categories"]


@app.get("/api/standards")
def standards(q: Optional[str] = Query(default=None, max_length=200)):
    return search_records(q) if q else DATA["standards"]


@app.post("/api/ask")
def ask(request: AskRequest):
    answer, sources = ai_answer(request.question)
    return {
        "answer": answer,
        "sources": sources,
        "ai_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL if GEMINI_API_KEY else None,
    }


@app.post("/api/verify")
def verify(request: VerifyRequest):
    number = request.license_number.strip().upper()
    for item in DATA["demo_licenses"]:
        if item["license_number"].upper() == number:
            return {"found": True, "result": item, "demo": True}
    return {
        "found": False,
        "demo": True,
        "message": "No record found in the local demo registry. This prototype does not query the live BIS registry yet.",
    }


@app.get("/api/labs")
def labs(q: Optional[str] = Query(default=None, max_length=100)):
    if not q:
        return DATA["labs"]
    terms = q.lower().split()
    return [lab for lab in DATA["labs"] if any(t in json.dumps(lab).lower() for t in terms)]


@app.get("/api/services")
def services():
    return DATA["services"]


frontend = ROOT / "sih26044-demo"
if frontend.exists():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
