# SkillBridge — SIH26044 Prototype

A prototype for SIH26044: Portal for Academia–Industry Collaboration for Skill Mapping, Internships and Placement.

## Current MVP
- Student profile and skill selection
- Skill-gap analysis
- Dynamic internship/job matching
- Match percentage with matched and missing skills
- Career readiness indicator
- Industry role posting API
- FastAPI backend with interactive Swagger docs
- Frontend served by FastAPI

## Run locally

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000/

API docs: http://127.0.0.1:8000/docs
