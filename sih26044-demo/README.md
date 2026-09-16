# SkillBridge Demo

This folder contains the browser UI for the SIH26044 prototype. The recommended way to run it is through the FastAPI backend so the UI can call `/api`.

From the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000/
