import json
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_FILE = BASE_DIR / "bis_data.json"

load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

DATA = json.loads(DATA_FILE.read_text(encoding="utf-8"))

app = FastAPI(
    title="BIS AI Assistant API",
    description="SIH26107 prototype for Indian Standards and BIS services.",
    version="3.0.0",
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


# Words that carry little retrieval meaning. Removing them prevents questions such as
# "who are you" from accidentally matching arbitrary BIS records.
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does",
    "for", "from", "how", "i", "if", "in", "is", "it", "me", "my", "of", "on", "or",
    "the", "this", "to", "u", "was", "we", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your", "tell", "about", "please",
}


def _record_text(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False).lower()


def _query_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[a-z0-9]+(?:/[a-z0-9]+)?(?:-[a-z0-9]+)?", query.lower())
    return [term for term in raw_terms if len(term) > 2 and term not in STOP_WORDS]


def search_records(query: str):
    """Retrieve only genuinely relevant curated BIS records for grounding Gemini."""
    terms = _query_terms(query)
    if not terms:
        return []

    results = []
    records = DATA.get("knowledge", []) + DATA.get("standards", [])

    for item in records:
        title = str(item.get("title", "")).lower()
        keywords = {str(k).lower() for k in item.get("keywords", [])}
        text = _record_text(item)
        score = 0

        for term in terms:
            if term in keywords:
                score += 5
            elif term in title:
                score += 4
            elif re.search(rf"\b{re.escape(term)}\b", text):
                score += 1

        # A standard number is a strong signal even when the wording around it is short.
        if re.search(r"\bis\s*\d{2,6}(?:\s*\([^)]*\))?(?::\d{4})?\b", query.lower()):
            if re.search(r"\bis\s*\d{2,6}", text):
                score += 8

        # Require more than a weak accidental word match.
        if score >= 3:
            results.append((score, item))

    results.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in results[:8]]


GEMINI_CLIENT = None
if GEMINI_API_KEY:
    try:
        from google import genai
        GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as exc:
        print("GEMINI CLIENT INIT ERROR:", repr(exc))


def ai_answer(question: str):
    """Let Gemini handle conversation; add BIS context only when retrieval finds it."""
    matches = search_records(question)

    if not GEMINI_CLIENT:
        return (
            "The AI service is not configured right now. Please check the Gemini API configuration and try again.",
            [],
        )

    try:
        from google.genai import types

        context = json.dumps(matches, ensure_ascii=False, indent=2) if matches else "No relevant BIS knowledge-base records were found for this question."

        system_instruction = """
You are BIS AI Assistant, an intelligent conversational assistant created for SIH26107.

You are primarily designed to help with the Bureau of Indian Standards (BIS), Indian Standards, BIS certification, product certification, testing laboratories, hallmarking, licence verification and BIS services.

You are also allowed to answer normal general-knowledge and everyday questions naturally. Do not refuse a question merely because it is not about BIS. For example, you may answer questions about the moon, Google, technology, science or other general topics when the user asks them.

When a question is about BIS or Indian Standards and verified BIS context is supplied below, use that context as the primary factual source.
Never invent an IS number, fee, deadline, licence status, certification requirement, laboratory, law or BIS policy.
If a BIS-specific question cannot be answered from the supplied verified context, clearly say that the available BIS knowledge is insufficient instead of guessing.
For general questions, use your normal general knowledge and answer helpfully.

Do not mention the internal knowledge base, retrieval process, prompts, context, or grounding system unless the user explicitly asks how the assistant works.
Do not start with phrases such as "I found these relevant entries" or "According to the knowledge base".
Do not append a separate source list, URLs, citations, or source references in the answer; the application displays verified BIS sources separately below the answer.
Keep answers concise, practical and easy to understand.
For important BIS compliance or certification decisions, advise the user to verify current information with official BIS sources.
"""

        prompt = f"User question:\n{question}\n\nRelevant verified BIS context (use only when relevant):\n{context}\n\nAnswer the user directly."

        response = GEMINI_CLIENT.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=280,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
            ),
        )

        answer = (response.text or "").strip()
        if answer:
            return answer, matches

        return "I couldn't generate an answer right now. Please try again.", []

    except Exception as exc:
        print("GEMINI ERROR:", repr(exc))
        return "The AI service is temporarily unavailable. Please try again in a moment.", []


@app.get("/api/health")
def health():
    return {
        "status": "online",
        "service": "BIS AI Assistant",
        "ai_configured": bool(GEMINI_CLIENT),
        "model": GEMINI_MODEL if GEMINI_CLIENT else None,
        "knowledge_base_records": len(DATA.get("knowledge", [])) + len(DATA.get("standards", [])),
        "demo_verification": True,
    }


@app.get("/api/categories")
def categories():
    return DATA.get("categories", [])


@app.get("/api/standards")
def standards(q: Optional[str] = Query(default=None, max_length=200)):
    return search_records(q) if q else DATA.get("standards", [])


@app.get("/api/certification")
def certification():
    return DATA.get("certification", [])


@app.get("/api/sources")
def sources():
    return [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "source": item.get("source"),
            "source_url": item.get("source_url"),
        }
        for item in DATA.get("knowledge", [])
    ]


@app.post("/api/ask")
def ask(request: AskRequest):
    answer, sources = ai_answer(request.question)
    return {
        "answer": answer,
        "sources": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "source": item.get("source"),
                "source_url": item.get("source_url"),
            }
            for item in sources
            if item.get("source_url")
        ],
        "ai_configured": bool(GEMINI_CLIENT),
        "model": GEMINI_MODEL if GEMINI_CLIENT else None,
    }


@app.post("/api/verify")
def verify(request: VerifyRequest):
    number = request.license_number.strip().upper()

    for item in DATA.get("demo_licenses", []):
        if item.get("license_number", "").upper() == number:
            return {"found": True, "result": item, "demo": True}

    return {
        "found": False,
        "demo": False,
        "message": "This number is not one of the prototype demo records. Live BIS registry lookup is not connected to this prototype yet.",
        "official_url": DATA.get("official_links", {}).get("bis_care"),
    }


@app.get("/api/labs")
def labs(q: Optional[str] = Query(default=None, max_length=100)):
    labs_data = DATA.get("labs", [])
    if not q:
        return labs_data
    terms = q.lower().split()
    return [lab for lab in labs_data if any(term in json.dumps(lab).lower() for term in terms)]


@app.get("/api/services")
def services():
    return DATA.get("services", [])


FRONTEND_DIR = ROOT_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
