# ET AI Concierge

## What Problem This Solves
Economic Times has a broad set of products and services (Prime, Markets, Wealth, Masterclass, Enterprise, Lifestyle), but users often discover only one or two.

This project solves the discovery and personalization problem by running a short conversational profiling flow that:
- understands user intent (goals, risk appetite, interests, background),
- maps that profile to the most relevant ET offerings,
- explains recommendations in a conversational, actionable way.

## Solution Overview
The system is split into two apps:
- `backend`: FastAPI + LangChain/Gemini service for persona extraction, product matching, recommendation formatting, and streaming responses.
- `frontend`: Next.js chat UI that sends full history each turn and renders streaming assistant output.

The architecture is stateless from an API perspective: conversation context is reconstructed from `conversation_history` sent by the client.

## Project Structure
- `backend/` - API, orchestration, models, catalog, tests
- `frontend/` - chat UI, styles, tests

## Quick Start

### 1. Backend
See full instructions in [backend/README.md](backend/README.md).

Quick commands:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
venv\Scripts\python -m uvicorn --app-dir . api.main:app --host 127.0.0.1 --port 8000
```

### 2. Frontend
See full instructions in [frontend/README.md](frontend/README.md).

Quick commands:

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

## Environment Notes
- Backend requires `GEMINI_API_KEY` and uses `GEMINI_MODEL` (default: `gemini-2.5-flash-lite`).
- Frontend requires `NEXT_PUBLIC_API_URL`.
- Recommended backend catalog path is `data/et_catalog.json` when running from the backend directory.

## Testing

Backend:

```bash
cd backend
venv\Scripts\python -m pytest tests -q
```

Frontend:

```bash
cd frontend
npm run type-check
npm run test
```