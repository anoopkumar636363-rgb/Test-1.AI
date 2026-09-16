# BIS AI Assistant — SIH26107

A working MVP for **SIH26107: AI-powered Intelligent Assistant for Indian Standards and BIS Services for Industries and Consumers**.

## What is included
- BIS-style AI chat interface
- Product / keyword standard search
- Certification guidance flow
- Consumer BIS licence verification demo endpoint
- Testing laboratory endpoint
- Service/category endpoints
- Optional Gemini integration through an environment variable
- Local fallback mode when no AI key is configured
- FastAPI Swagger documentation
- Clearly labelled demo data so no placeholder record is mistaken for a real BIS certificate or standard

## Run on Windows

From the repository root, with your existing virtual environment activated:

```powershell
git pull origin main
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Open:
- App: http://127.0.0.1:8000/
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health

## Add your AI API key later

Copy `backend/.env.example` to `backend/.env` and add your key. `.env` is ignored by Git.

```text
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The assistant works in fallback/retrieval mode without a key, so we can build and test the UI and APIs first.

## Data plan

`backend/bis_data.json` currently contains **demo records only**. Before a production or competition submission, replace them with a verified, legally usable BIS knowledge base. We can add records manually, import approved public BIS material, or build a retrieval pipeline around permitted sources. The assistant is instructed not to invent standard numbers or certification requirements.

## Next build stages
1. Replace demo records with verified BIS data.
2. Add document ingestion and retrieval/RAG.
3. Add user login and conversation history.
4. Add live BIS service/registry integrations where an approved public/API route exists.
5. Add multilingual support.
6. Add admin tools for updating and reviewing the knowledge base.
