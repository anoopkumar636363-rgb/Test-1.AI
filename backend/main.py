import json
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "backend" / "bis_data.json"
DATA = json.loads(DATA_FILE.read_text(encoding="utf-8"))

app = FastAPI(
    title="BIS AI Assistant API",
    description="SIH26107 prototype: AI-assisted guidance for Indian Standards and BIS services.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)

class VerifyRequest(BaseModel):
    license_number: str = Field(min_length=2, max_length=100)


def search_records(query: str):
    q = query.lower().strip()
    results = []
    for item in DATA["standards"]:
        haystack = " ".join([
            item.get("title", ""), item.get("product", ""), item.get("category", ""),
            item.get("summary", ""), " ".join(item.get("keywords", []))
        ]).lower()
        terms = [x for x in q.split() if len(x) > 2]
        score = sum(1 for term in terms if term in haystack)
        if score:
            results.append((score, item))
    return [item for _, item in sorted(results, key=lambda x: x[0], reverse=True)]


def fallback_answer(question: str):
    matches = search_records(question)
    if matches:
        top = matches[:3]
        lines = ["I found relevant entries in the prototype knowledge base:"]
        for item in top:
            lines.append(f"• {item['title']} — {item['summary']}")
        lines.append("\nThis is guidance from the demo dataset. Verify the current requirement on the official BIS source before relying on it for certification or compliance.")
        return "\n".join(lines), top
    return (
        "I could not find a confident match in the current demo knowledge base. "
        "Try the product name, an IS number, 'BIS certification', 'hallmarking', or 'testing laboratory'. "
        "For a production system, we will connect a verified BIS corpus and retrieval pipeline here.", []
    )


def ai_answer(question: str):
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return fallback_answer(question)
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        matches = search_records(question)[:5]
        context = json.dumps(matches, ensure_ascii=False)
        prompt = f"""You are a BIS information assistant prototype. Answer only from the supplied context. Do not invent Indian Standard numbers, certification rules, fees, deadlines, license validity, or legal requirements. If the context is insufficient, say so. Clearly label the answer as guidance and tell the user to verify current requirements with BIS.\n\nQuestion: {question}\n\nVerified demo context:\n{context}"""
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        return response.text, matches
    except Exception as exc:
        answer, matches = fallback_answer(question)
        return answer + f"\n\nAI service fallback active ({type(exc).__name__}).", matches


@app.get("/api/health")
def health():
    return {"status": "online", "service": "BIS AI Assistant", "ai_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))}

@app.get("/api/categories")
def categories():
    return DATA["categories"]

@app.get("/api/standards")
def standards(q: Optional[str] = Query(default=None, max_length=200)):
    return search_records(q) if q else DATA["standards"]

@app.post("/api/ask")
def ask(request: AskRequest):
    answer, sources = ai_answer(request.question)
    return {"answer": answer, "sources": sources, "ai_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))}

@app.post("/api/verify")
def verify(request: VerifyRequest):
    number = request.license_number.strip().upper()
    for item in DATA["demo_licenses"]:
        if item["license_number"].upper() == number:
            return {"found": True, "result": item, "demo": True}
    return {
        "found": False,
        "demo": True,
        "message": "No record found in the local demo registry. This prototype does not query the live BIS registry yet."
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
