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
    version="2.2.0",
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


def _record_text(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False).lower()


def search_records(query: str):
    """Search curated BIS knowledge and standards with simple keyword scoring."""
    terms = [term for term in re.findall(r"[a-z0-9-]+", query.lower()) if len(term) > 2]
    results = []
    records = DATA.get("knowledge", []) + DATA.get("standards", [])

    for item in records:
        text = _record_text(item)
        score = 0
        for term in terms:
            if term in text:
                score += 1
                if term in [str(k).lower() for k in item.get("keywords", [])]:
                    score += 3
        if score:
            results.append((score, item))

    results.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in results]


def quick_answer(question: str) -> Optional[str]:
    """Answer simple conversational messages locally for near-zero latency."""
    q = re.sub(r"[^a-z0-9 ]+", " ", question.lower()).strip()

    if q in {"hi", "hello", "hey", "hii", "hiii", "helo", "good morning", "good afternoon", "good evening"}:
        return "Hello! 👋 I'm the BIS AI Assistant. Ask me about Indian Standards, BIS certification, testing, hallmarking, or BIS services."
    if q in {"thanks", "thank you", "thx", "thankyou"}:
        return "You're welcome! 👋"
    if q in {"bye", "goodbye", "see you"}:
        return "Goodbye! 👋"
    if q in {"help", "who are you", "what are you", "what can you do"}:
        return "I'm the BIS AI Assistant. I can help explain Indian Standards, certification, testing, licence verification and BIS services."
    return None


def fallback_answer(question: str):
    matches = search_records(question)[:5]
    if matches:
        answer = "I found these relevant entries in the BIS knowledge base:\n\n"
        answer += "\n".join(
            f"• {item.get('title', 'Untitled')} — {item.get('summary', '')}"
            for item in matches
        )
        answer += "\n\nThis information is grounded in official BIS sources. Verify important compliance requirements against the latest BIS information."
        return answer, matches

    return (
        "I don't have enough verified BIS information in the connected knowledge base to answer that safely. "
        "Try asking about Indian Standards, certification, testing laboratories, licence verification, or BIS services.",
        [],
    )


GEMINI_CLIENT = None
if GEMINI_API_KEY:
    try:
        from google import genai
        GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as exc:
        print("GEMINI CLIENT INIT ERROR:", repr(exc))


def ai_answer(question: str):
    quick = quick_answer(question)
    if quick:
        return quick, []

    if not GEMINI_CLIENT:
        return fallback_answer(question)

    try:
        from google.genai import types

        matches = search_records(question)[:8]
        context = json.dumps(matches, ensure_ascii=False, indent=2)

        system_instruction = """
You are the BIS AI Assistant for SIH26107.

Help users understand Indian Standards, BIS certification, testing, hallmarking, licence verification and BIS services.
Treat the supplied BIS knowledge-base context as the primary factual source.
Use general model knowledge only for conversational wording, not for unsupported BIS-specific facts.
Never invent an IS number, fee, deadline, licence status, certification requirement, laboratory, law or BIS policy.
If the supplied knowledge base does not contain enough verified information, say so clearly instead of guessing.
When a source URL is supplied, do not alter or invent it.
Keep answers concise, practical and easy to understand.
For important compliance or certification decisions, tell the user to verify current information with official BIS sources.
"""

        prompt = f"User question:\n{question}\n\nVerified BIS knowledge-base context:\n{context or 'No matching verified BIS records were found.'}\n\nAnswer the user directly."

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
        return fallback_answer(question)

    except Exception as exc:
        print("GEMINI ERROR:", repr(exc))
        answer, matches = fallback_answer(question)
        return answer + "\n\nGemini could not be reached, so the local grounded response was used.", matches


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
