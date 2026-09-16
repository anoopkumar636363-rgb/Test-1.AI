# BIS AI Assistant backend

FastAPI backend for SIH26107.

## Windows

From the repository root, keep your existing `venv` active:

```powershell
git pull origin main
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000/` for the app and `http://127.0.0.1:8000/docs` for Swagger.

Optional AI configuration:

```powershell
Copy-Item backend\.env.example backend\.env
```

Then put your API key in `backend/.env`. Never commit the real key.
