from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List

app = FastAPI(title="SkillBridge API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SKILLS = ["python", "javascript", "react", "html/css", "git", "fastapi", "sql", "communication", "problem solving"]

OPPORTUNITIES = [
    {"id": 1, "title": "Frontend Developer Intern", "company": "TechNova Labs", "location": "Bengaluru", "skills": ["javascript", "react", "html/css", "git"], "type": "Internship"},
    {"id": 2, "title": "Python Backend Intern", "company": "Alpha Systems", "location": "Remote", "skills": ["python", "fastapi", "sql", "git"], "type": "Internship"},
    {"id": 3, "title": "Software Engineering Intern", "company": "Orbit Technologies", "location": "Hyderabad", "skills": ["python", "javascript", "git", "problem solving"], "type": "Internship"},
    {"id": 4, "title": "Junior Full Stack Developer", "company": "BuildWorks", "location": "Pune", "skills": ["javascript", "react", "python", "sql", "git"], "type": "Job"},
]

class Student(BaseModel):
    name: str = "Demo Student"
    college: str = "Demo Engineering College"
    branch: str = "Computer Science"
    year: int = Field(default=3, ge=1, le=5)
    skills: List[str] = []

class CompanyRole(BaseModel):
    title: str
    company: str
    skills: List[str]
    location: str = "Remote"

def normalize(items):
    return {x.strip().lower() for x in items if x.strip()}

def match_score(student_skills, required):
    have, need = normalize(student_skills), normalize(required)
    return round(len(have & need) / max(len(need), 1) * 100)

@app.get("/api/health")
def health():
    return {"status": "online", "service": "SkillBridge API"}

@app.get("/api/skills")
def skills():
    return {"skills": SKILLS}

@app.get("/api/opportunities")
def opportunities():
    return OPPORTUNITIES

@app.post("/api/match")
def match(student: Student):
    results = []
    have = normalize(student.skills)
    for item in OPPORTUNITIES:
        need = normalize(item["skills"])
        matched = sorted(have & need)
        missing = sorted(need - have)
        results.append({**item, "match": match_score(student.skills, item["skills"]), "matched_skills": matched, "missing_skills": missing})
    results.sort(key=lambda x: x["match"], reverse=True)
    readiness = round(sum(min(len(have & normalize(x["skills"])), 3) for x in OPPORTUNITIES) / max(len(OPPORTUNITIES) * 3, 1) * 100)
    return {"student": student, "readiness": readiness, "matches": results}

@app.post("/api/roles")
def add_role(role: CompanyRole):
    new_id = max([x["id"] for x in OPPORTUNITIES], default=0) + 1
    item = {"id": new_id, **role.model_dump(), "type": "Industry Opportunity"}
    OPPORTUNITIES.append(item)
    return item

# Serve the frontend when the backend is started from the project root.
frontend = Path(__file__).resolve().parent.parent / "sih26044-demo"
if frontend.exists():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
