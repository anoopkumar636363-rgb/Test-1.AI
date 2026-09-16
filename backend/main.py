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
    version="3.0.0",
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
    return [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


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
    text = str(exc).lower()
    return any(marker in text for marker in (
        " 429", "429 ", "resource_exhausted", "rate limit",
        " 500", "500 ", " 502", "502 ", " 503", "503 ",
        " 504", "504 ", "unavailable", "overloaded", "temporarily",
    ))


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


AGENT_PROMPTS = {
    "general": """
You are the General Conversation Agent inside the BIS AI Assistant.
Handle normal conversation, casual questions, greetings, general knowledge, simple explanations and harmless random questions naturally.
Do not pretend that general facts are BIS facts. Do not invent BIS-specific information.
If the user asks about BIS, Indian Standards, certification, compliance, laboratories or licence verification, the orchestrator should have routed the request to a BIS specialist instead.
""",
    "standards": """
You are the BIS Standards Specialist.
Your job is to reason over retrieved BIS standards data and explain which Indian Standard records are relevant to the user's product or question.
Treat supplied BIS records as the factual source of truth. Never invent an IS number, title, revision, amendment, scope or requirement.
If the supplied records are insufficient, say so and direct the user to verify the current official BIS record.
""",
    "certification": """
You are the BIS Certification Specialist.
Explain BIS product certification and certification workflow using supplied verified BIS information.
Never invent fees, timelines, licence requirements, mandatory certification claims or legal requirements.
Separate general explanation from facts that must be verified against current BIS information.
""",
    "compliance": """
You are the BIS Compliance Specialist.
Help users understand BIS-related compliance questions, QCO-related context, conformity concepts and practical next steps using supplied verified information.
Never invent a mandatory requirement or claim that a product is legally required to be certified unless the supplied source supports it.
""",
    "verification": """
You are the BIS Verification Specialist.
Help users understand licence/registration verification and BIS verification workflows.
Only report a licence as verified when the connected verification data actually contains it. Never manufacture a licence status.
""",
}


def _run_gemini(instruction: str, prompt: str, max_output_tokens: int = 500):
    if not GEMINI_CLIENT:
        return None, "configuration", None

    try:
        from google.genai import types
    except Exception as exc:
        print("GEMINI SDK IMPORT ERROR:", repr(exc))
        return None, "provider_error", None

    last_error = None
    for index, model in enumerate(GEMINI_MODELS):
        try:
            print(f"GEMINI ATTEMPT {index + 1}/{len(GEMINI_MODELS)} MODEL={model}")
            response = GEMINI_CLIENT.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    max_output_tokens=max_output_tokens,
                ),
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

    print("GEMINI ALL MODELS FAILED:", repr(last_error))
    return None, "provider_error", None


def _clean_route(value: str) -> str:
    value = value.strip().lower()
    aliases = {
        "standard": "standards",
        "indian standards": "standards",
        "product standards": "standards",
        "certification": "certification",
        "certificate": "certification",
        "compliance": "compliance",
        "verification": "verification",
        "verify": "verification",
        "license": "verification",
        "licence": "verification",
        "general": "general",
        "normal": "general",
    }
    return aliases.get(value, value if value in AGENT_PROMPTS else "general")


def route_question(question: str, history: list[ChatMessage]) -> str:
    """Let the orchestration model decide which specialist should handle the turn."""
    router_prompt = f"""
Classify the user's current request for the BIS AI Assistant.
Choose exactly one route: general, standards, certification, compliance, verification.
Use the conversation context when a follow-up such as 'what about certification?' depends on the previous product/topic.
Return ONLY the route name. No punctuation and no explanation.

Conversation:
{_history_prompt(history)}

Current request:
{question}
"""
    answer, status, _ = _run_gemini(
        "You are the Orchestrator Agent. Route requests to the most appropriate internal agent. Do not answer the user.",
        router_prompt,
        max_output_tokens=20,
    )
    if status != "ok" or not answer:
        # This is only a safe degradation path if the AI router itself is unavailable.
        return "general"
    return _clean_route(answer)


def ai_answer(question: str, history: list[ChatMessage], off_topic_count: int):
    if not GEMINI_CLIENT:
        return (
            "The AI service is not configured on the server. Check GEMINI_API_KEY in the deployment environment.",
            [], "configuration", None, "general", off_topic_count,
        )

    route = route_question(question, history)
    bis_route = route != "general"

    if bis_route:
        new_off_topic_count = 0
    else:
        new_off_topic_count = min(off_topic_count + 1, 5)

    # After five consecutive off-topic turns, the assistant politely enforces its scope.
    if route == "general" and new_off_topic_count >= 5:
        return (
            "I can answer general questions for a few turns, but I’m the BIS AI Assistant. "
            "Let’s get back to Indian Standards, BIS certification, compliance, testing, "
            "licence verification, or other BIS services. 🙂",
            [], "ok", None, route, new_off_topic_count,
        )

    matches = search_records(question)[:8] if bis_route else []
    context = json.dumps(matches, ensure_ascii=False, indent=2) if matches else "No relevant verified BIS records were found for this turn."

    specialist = AGENT_PROMPTS[route]
    final_instruction = specialist + """

You are one internal agent in a larger BIS AI system. Answer the user directly, naturally and concisely.
The user should not see internal routing terminology or agent names.
Use conversation history to resolve references and maintain context.
For BIS-specific claims, the supplied retrieved BIS records outrank your general model knowledge.
Do not invent missing BIS facts.
Do not produce a separate source list; the application displays source links separately.
"""

    prompt = f"""
Conversation history:
{_history_prompt(history)}

Current user request:
{question}

Internal route:
{route}

Retrieved BIS records:
{context}

Give the best direct response to the current request.
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
        "fallback_models": GEMINI_MODELS if GEMINI_CLIENT else [],
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
    answer, source_records, status, model_used, route, off_topic_count = ai_answer(
        request.question, request.history, request.off_topic_count
    )
    return {
        "answer": answer,
        "sources": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "source": item.get("source"),
                "source_url": item.get("source_url"),
            }
            for item in source_records
            if item.get("source_url")
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
