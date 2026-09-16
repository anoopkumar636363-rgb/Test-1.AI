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

# The first model is the configured primary. If a transient provider error such
# as 503/429/5xx occurs, the assistant automatically tries the remaining models.
# All models use the same Gemini API key/project; no extra keys are required.
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
configured_models = [item.strip() for item in os.getenv("GEMINI_MODELS", "").split(",") if item.strip()]
GEMINI_MODELS = list(dict.fromkeys(([GEMINI_MODEL] if GEMINI_MODEL else []) + configured_models + DEFAULT_FALLBACK_MODELS))

DATA = json.loads(DATA_FILE.read_text(encoding="utf-8"))

app = FastAPI(
    title="BIS AI Assistant API",
    description="SIH26107 prototype for Indian Standards and BIS services.",
    version="2.7.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class VerifyRequest(BaseModel):
    license_number: str = Field(min_length=2, max_length=100)


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "did", "do", "does",
    "for", "from", "how", "i", "if", "in", "is", "it", "me", "my", "of", "on", "or", "that",
    "the", "this", "to", "u", "was", "we", "what", "when", "where", "which", "who", "why", "with",
    "you", "your", "tell", "about", "please", "would", "should", "will", "has", "have", "had",
}


def _tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def _record_text(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False).lower()


def search_records(query: str):
    """Retrieve only meaningfully related curated BIS records."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    query_lower = query.lower()
    results = []
    records = DATA.get("knowledge", []) + DATA.get("standards", [])

    for item in records:
        title_tokens = set(_tokens(str(item.get("title", ""))))
        summary_tokens = set(_tokens(str(item.get("summary", ""))))
        keyword_tokens = set(_tokens(" ".join(str(k) for k in item.get("keywords", []))))
        all_tokens = title_tokens | summary_tokens | keyword_tokens | set(_tokens(_record_text(item)))

        score = 0
        for token in query_tokens:
            if token in keyword_tokens:
                score += 5
            elif token in title_tokens:
                score += 4
            elif token in summary_tokens:
                score += 2
            elif token in all_tokens:
                score += 1

        title = str(item.get("title", "")).lower()
        if query_lower.strip() and query_lower.strip() in title:
            score += 6

        if score >= 3:
            results.append((score, item))

    results.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in results]


def is_bis_question(question: str) -> bool:
    q = question.lower()
    bis_terms = (
        "bis", "bureau of indian standards", "indian standard", "indian standards", "isi mark",
        "hallmark", "hallmarking", "certification", "certified", "licence", "license", "cm/l",
        "testing laboratory", "testing lab", "manak", "crs", "fmcs", "product certification",
        "bis care", "bis portal", "standards portal",
    )
    return any(term in q for term in bis_terms)


GEMINI_CLIENT = None
if GEMINI_API_KEY:
    try:
        from google import genai
        GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as exc:
        print("GEMINI CLIENT INIT ERROR:", repr(exc))


def _history_prompt(history: list[ChatMessage]) -> str:
    if not history:
        return "No previous conversation."
    lines = []
    for message in history[-12:]:
        speaker = "User" if message.role == "user" else "Assistant"
        lines.append(f"{speaker}: {message.content}")
    return "\n".join(lines)


def _is_transient_gemini_error(exc: Exception) -> bool:
    """Only fail over for errors that can reasonably be temporary."""
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            " 429", "429 ", "resource_exhausted", "rate limit",
            " 500", "500 ", " 502", "502 ", " 503", "503 ",
            " 504", "504 ", "unavailable", "overloaded", "temporarily",
        )
    )


def _error_label(exc: Exception) -> str:
    text = str(exc).lower()
    if "429" in text or "resource_exhausted" in text or "rate limit" in text:
        return "rate_limit_or_quota"
    if "503" in text or "unavailable" in text or "overloaded" in text:
        return "temporary_model_unavailable"
    if "401" in text or "unauthorized" in text or "api key" in text:
        return "authentication"
    if "403" in text or "permission" in text or "forbidden" in text:
        return "permission"
    if "404" in text or "not found" in text:
        return "model_not_found"
    return "provider_error"


def ai_answer(question: str, history: list[ChatMessage]):
    """Let Gemini handle conversation with automatic multi-model failover."""
    if not GEMINI_CLIENT:
        return (
            "The AI service is not configured on the server. Check GEMINI_API_KEY in the deployment environment.",
            [],
            "configuration",
            None,
        )

    matches = search_records(question)[:8]
    context = json.dumps(matches, ensure_ascii=False, indent=2)
    bis_question = is_bis_question(question)

    system_instruction = """
You are the BIS AI Assistant for SIH26107.

You are a natural conversational AI assistant. You can have normal conversations and answer general-knowledge questions naturally. Do not force every conversation to be about BIS.

Your specialist role is helping with Bureau of Indian Standards (BIS), Indian Standards, BIS certification, product certification, testing laboratories, hallmarking, licence verification and BIS services.

When a user asks a BIS-specific question, treat the supplied verified BIS knowledge-base context as the primary factual source. Use general model knowledge only for conversational wording and broad explanations, never to invent BIS-specific facts.
Never invent an IS number, fee, deadline, licence status, certification requirement, laboratory, law, or BIS policy.
If a BIS-specific question has no relevant verified context, clearly say that the connected BIS knowledge base does not contain enough verified information and advise checking official BIS information rather than guessing.

Use the previous conversation to understand references such as "it", "that product", "what standard applies?", and "what about certification?". Do not make the user repeat information already provided.

When a user asks a general question that is not about BIS, answer it normally using your general knowledge. Do not redirect the user to BIS just because you are called the BIS AI Assistant.

Do not include a separate source list, URLs, citations, or phrases such as "I found these relevant entries" or "According to the knowledge base". The application displays verified BIS sources separately when available.
Keep answers natural, concise and useful.
For important BIS compliance or certification decisions, remind the user to verify current information with official BIS sources.
"""

    context_note = context if matches else "No relevant verified BIS knowledge-base records were found for this question."
    scope_note = "This question appears to be BIS-specific." if bis_question else "This is a general conversation question."

    prompt = (
        f"Previous conversation:\n{_history_prompt(history)}\n\n"
        f"Current user question:\n{question}\n\n"
        f"Question classification:\n{scope_note}\n\n"
        f"Verified BIS knowledge-base context:\n{context_note}\n\n"
        "Answer the current user question directly, using conversation context where useful."
    )

    try:
        from google.genai import types
    except Exception as exc:
        print("GEMINI SDK IMPORT ERROR:", repr(exc))
        return "The AI SDK is unavailable on the server.", matches, "provider_error", None

    last_error = None
    for index, model in enumerate(GEMINI_MODELS):
        try:
            print(f"GEMINI ATTEMPT {index + 1}/{len(GEMINI_MODELS)} MODEL={model}")
            response = GEMINI_CLIENT.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=500,
                ),
            )

            answer = (response.text or "").strip()
            if answer:
                if index > 0:
                    print(f"GEMINI FAILOVER SUCCESS: {model}")
                return answer, matches, "ok", model

            last_error = RuntimeError("Gemini returned an empty response")
            print(f"GEMINI EMPTY RESPONSE MODEL={model}")

        except Exception as exc:
            last_error = exc
            label = _error_label(exc)
            print(f"GEMINI ERROR MODEL={model} TYPE={label}: {repr(exc)}")

            # Authentication, permission, invalid-model and malformed-request errors
            # will fail for every model with the same key, so do not waste time looping.
            if not _is_transient_gemini_error(exc):
                return (
                    "The AI provider rejected the request. Please check the Gemini API key, model access, or deployment configuration.",
                    matches,
                    "provider_error",
                    model,
                )

    print("GEMINI ALL MODELS FAILED:", repr(last_error))
    return (
        "The AI service is temporarily busy. I tried multiple Gemini models, but they are currently unavailable. Please try again in a moment.",
        matches,
        "provider_error",
        None,
    )


@app.get("/api/health")
def health():
    return {
        "status": "online",
        "service": "BIS AI Assistant",
        "ai_configured": bool(GEMINI_CLIENT),
        "primary_model": GEMINI_MODEL if GEMINI_CLIENT else None,
        "fallback_models": GEMINI_MODELS if GEMINI_CLIENT else [],
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
    answer, sources, status, model_used = ai_answer(request.question, request.history)
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
        "model": model_used or (GEMINI_MODEL if GEMINI_CLIENT else None),
        "status": status,
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
