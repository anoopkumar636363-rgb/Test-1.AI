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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
DEFAULT_FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
configured_models = [item.strip() for item in os.getenv("GEMINI_MODELS", "").split(",") if item.strip()]
GEMINI_MODELS = list(dict.fromkeys(([GEMINI_MODEL] if GEMINI_MODEL else []) + configured_models + DEFAULT_FALLBACK_MODELS))
MAX_MODEL_ATTEMPTS = 2

DATA = json.loads(DATA_FILE.read_text(encoding="utf-8"))

app = FastAPI(
    title="BIS AI Assistant API",
    description="SIH26107 prototype for Indian Standards and BIS services.",
    version="3.3.0",
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
    off_topic_count: int = Field(default=0, ge=0, le=5)


class VerifyRequest(BaseModel):
    license_number: str = Field(min_length=2, max_length=100)


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "did", "do", "does",
    "for", "from", "how", "i", "if", "in", "is", "it", "me", "my", "of", "on", "or", "that",
    "the", "this", "to", "u", "was", "we", "what", "when", "where", "which", "who", "why", "with",
    "you", "your", "tell", "about", "please", "would", "should", "will", "has", "have", "had",
}


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2 and token not in STOPWORDS]


def _record_text(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False).lower()


def search_records(query: str):
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


BIS_TERMS = {
    "bis", "bureau of indian standards", "indian standard", "indian standards", "isi mark",
    "hallmark", "hallmarking", "certification", "certified", "licence", "license", "cm/l",
    "testing laboratory", "testing lab", "manak", "crs", "fmcs", "product certification",
    "bis care", "bis portal", "standards portal", "qco", "quality control order", "conformity",
}
CERTIFICATION_TERMS = {"certification", "certified", "certificate", "certify", "licence application", "license application", "product certification", "scheme", "grant of licence", "surveillance"}
COMPLIANCE_TERMS = {"compliance", "qco", "quality control order", "mandatory", "conformity", "requirement", "requirements", "legal requirement", "regulation", "regulatory", "compulsory"}
VERIFICATION_TERMS = {"verify", "verification", "licence", "license", "cm/l", "registration number", "registration", "is my licence", "is my license", "genuine licence", "genuine license", "check licence", "check license"}


def _contains_term(text: str, terms: set[str]) -> bool:
    return any(term in text.lower() for term in terms)


def is_bis_question(question: str, history: list[ChatMessage] | None = None) -> bool:
    if _contains_term(question, BIS_TERMS):
        return True
    prior_user_text = " ".join(message.content for message in (history or []) if message.role == "user")[-5000:]
    if prior_user_text and _contains_term(prior_user_text, BIS_TERMS):
        words = _tokens(question)
        return len(words) <= 12 or _contains_term(question, {"standard", "product", "certification", "compliance", "license", "licence", "lab", "testing"})
    return False


GEMINI_CLIENT = None
if GEMINI_API_KEY:
    try:
        from google import genai
        from google.genai import types
        try:
            GEMINI_CLIENT = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=12000, retry_options=types.HttpRetryOptions(attempts=1)),
            )
        except Exception:
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
    text = str(exc).lower()
    return any(marker in text for marker in (" 408", "408 ", " 429", "429 ", "resource_exhausted", "rate limit", " 500", "500 ", " 502", "502 ", " 503", "503 ", " 504", "504 ", "unavailable", "overloaded", "temporarily", "deadline"))


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
    if "408" in text or "504" in text or "deadline" in text:
        return "timeout"
    return "provider_error"


AGENT_PROMPTS = {
    "general": """
You are the General Conversation Agent inside the BIS AI Assistant.
You are not a generic unnamed chatbot. Your identity is the BIS AI Assistant, an AI assistant focused on Indian Standards and BIS services.
When the user asks who you are, what you are, what you do, or similar identity questions, answer naturally from that identity and briefly explain your BIS-focused capabilities.
Handle normal conversation, greetings, general knowledge, simple explanations and harmless random questions naturally.
You may answer general questions; do not force BIS into unrelated conversations.
Do not claim to be a human, BIS employee, government official, or an official BIS decision-maker.
""",
    "standards": """
You are the BIS Standards Specialist.
Reason over the supplied BIS records and explain which Indian Standard information is relevant to the user's product or question.
Treat supplied BIS records as the factual source of truth. Never invent an IS number, title, revision, amendment, scope or requirement.
""",
    "certification": """
You are the BIS Certification Specialist.
Explain BIS product certification and certification workflow using supplied verified BIS information.
Never invent fees, timelines, licence requirements, mandatory certification claims or legal requirements.
""",
    "compliance": """
You are the BIS Compliance Specialist.
Help users understand BIS-related compliance, QCO context, conformity concepts and practical next steps using supplied verified information.
Never invent a mandatory requirement or claim that a product is legally required to be certified unless the supplied source supports it.
""",
    "verification": """
You are the BIS Verification Specialist.
Help users understand licence/registration verification and BIS verification workflows.
Only report a licence as verified when connected verification data actually contains it. Never manufacture a licence status.
""",
}


def route_question(question: str, history: list[ChatMessage], bis_question: bool) -> str:
    if not bis_question:
        return "general"
    q = question.lower()
    if _contains_term(q, VERIFICATION_TERMS):
        return "verification"
    if _contains_term(q, CERTIFICATION_TERMS):
        return "certification"
    if _contains_term(q, COMPLIANCE_TERMS):
        return "compliance"
    return "standards"


def _run_gemini(instruction: str, prompt: str, max_output_tokens: int = 500):
    if not GEMINI_CLIENT:
        return None, "configuration", None
    try:
        from google.genai import types
    except Exception as exc:
        print("GEMINI SDK IMPORT ERROR:", repr(exc))
        return None, "provider_error", None

    last_error = None
    attempts = min(MAX_MODEL_ATTEMPTS, len(GEMINI_MODELS))
    for index, model in enumerate(GEMINI_MODELS[:attempts]):
        try:
            print(f"GEMINI ATTEMPT {index + 1}/{attempts} MODEL={model}")
            thinking_config = None
            if model in {"gemini-3.6-flash", "gemini-3.5-flash"}:
                thinking_config = types.ThinkingConfig(thinking_level="low")
            config_kwargs = {"system_instruction": instruction, "max_output_tokens": max_output_tokens}
            if thinking_config is not None:
                config_kwargs["thinking_config"] = thinking_config
            response = GEMINI_CLIENT.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            answer = (response.text or "").strip()
            if answer:
                if index > 0:
                    print(f"GEMINI FAILOVER SUCCESS: {model}")
                return answer, "ok", model
            last_error = RuntimeError("Gemini returned an empty response")
        except Exception as exc:
            last_error = exc
            label = _error_label(exc)
            print(f"GEMINI ERROR MODEL={model} TYPE={label}: {repr(exc)}")
            if not _is_transient_gemini_error(exc):
                return None, "provider_error", model
    print("GEMINI REQUESTS EXHAUSTED:", repr(last_error))
    return None, "provider_error", None


def ai_answer(question: str, history: list[ChatMessage], off_topic_count: int):
    if not GEMINI_CLIENT:
        return "The AI service is not configured on the server. Check GEMINI_API_KEY in the deployment environment.", [], "configuration", None, "general", off_topic_count

    bis_question = is_bis_question(question, history)
    route = route_question(question, history, bis_question)
    new_off_topic_count = 0 if bis_question else min(off_topic_count + 1, 5)

    if not bis_question and new_off_topic_count >= 5:
        return (
            "I can answer general questions for a few turns, but I’m the BIS AI Assistant. Let’s get back to Indian Standards, BIS certification, compliance, testing, licence verification, or other BIS services. 🙂",
            [], "ok", None, "general", new_off_topic_count,
        )

    matches = search_records(question)[:8] if bis_question else []
    context = json.dumps(matches, ensure_ascii=False, indent=2) if matches else "No relevant verified BIS records were found for this turn."

    final_instruction = AGENT_PROMPTS[route] + """

You are one internal specialist in a larger BIS AI Assistant. Answer the user directly and naturally.
The user should not see internal routing or agent terminology.
Use the conversation history to resolve references and maintain context.
For BIS-specific claims, supplied retrieved BIS records outrank your general model knowledge.
Never invent missing BIS facts.
Do not output a separate source list; the application displays source links separately.
For important compliance/certification decisions, recommend checking the current official BIS information.
"""

    prompt = f"""
Conversation history:
{_history_prompt(history)}

Current user request:
{question}

Internal specialist role:
{route}

Retrieved BIS records:
{context}

Respond to the current user request directly. Keep a normal conversation tone.
"""

    answer, status, model_used = _run_gemini(final_instruction, prompt, max_output_tokens=500)
    if status != "ok" or not answer:
        answer = "The AI service is temporarily unavailable. Please try again in a moment."
    return answer, matches, status, model_used, route, new_off_topic_count


@app.get("/api/health")
def health():
    return {
        "status": "online",
        "service": "BIS AI Assistant",
        "ai_configured": bool(GEMINI_CLIENT),
        "primary_model": GEMINI_MODEL if GEMINI_CLIENT else None,
        "fallback_models": GEMINI_MODELS[:MAX_MODEL_ATTEMPTS] if GEMINI_CLIENT else [],
        "knowledge_base_records": len(DATA.get("knowledge", [])) + len(DATA.get("standards", [])),
        "agents": list(AGENT_PROMPTS.keys()),
        "session_memory": True,
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
        {"id": item.get("id"), "title": item.get("title"), "source": item.get("source"), "source_url": item.get("source_url")}
        for item in DATA.get("knowledge", [])
    ]


@app.post("/api/ask")
def ask(request: AskRequest):
    answer, source_records, status, model_used, route, off_topic_count = ai_answer(request.question, request.history, request.off_topic_count)
    return {
        "answer": answer,
        "sources": [
            {"id": item.get("id"), "title": item.get("title"), "source": item.get("source"), "source_url": item.get("source_url")}
            for item in source_records if item.get("source_url")
        ],
        "ai_configured": bool(GEMINI_CLIENT),
        "model": model_used or (GEMINI_MODEL if GEMINI_CLIENT else None),
        "status": status,
        "route": route,
        "off_topic_count": off_topic_count,
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
