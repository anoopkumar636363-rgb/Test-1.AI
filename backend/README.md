# SkillBridge backend

## Windows setup

From the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000/ for the app and http://127.0.0.1:8000/docs for the API docs.
