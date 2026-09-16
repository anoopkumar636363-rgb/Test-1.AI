# BIS AI Assistant — SIH26107

Prototype for **SIH26107: AI-powered Intelligent Assistant for Indian Standards and BIS Services for Industries and Consumers**.

## Current structure

```text
Test-1.AI/
├── backend/
│   ├── main.py
│   ├── bis_data.json
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── .gitignore
├── render.yaml
└── README.md
```

## What works now

- FastAPI backend
- Browser frontend served by FastAPI
- Fast local responses for greetings
- Gemini integration through `GEMINI_API_KEY`
- Local BIS knowledge-base search
- Standards search API
- BIS licence verification endpoint placeholder
- Testing laboratory and service endpoints ready for data
- Health endpoint for deployment checks
- Swagger API docs

## Run locally on Windows

From the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Open:

- App: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health`

## Gemini key

Copy `backend/.env.example` to `backend/.env` and put your own key there.

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

`backend/.env` is ignored by Git. Never put a real API key in `.env.example`, source code, screenshots, or GitHub.

## BIS data

`backend/bis_data.json` intentionally contains **no fake BIS standards, certificates, laboratories, fees, or licence records**. The verified BIS information will be added later.

When we add the data, the assistant will use it as its local retrieval context and will be instructed not to invent missing BIS requirements.

## Next build steps

1. Add verified BIS standards and service information.
2. Improve retrieval so product descriptions map to relevant standards.
3. Add official-source references to answers.
4. Connect live BIS services/registry only where an appropriate public or approved integration exists.
5. Test the complete demo and deploy.
