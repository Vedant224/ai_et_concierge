# AI Concierge for ET

## Project Structure

- backend: FastAPI + LangChain orchestration + tests
- frontend: Next.js chat UI + tests

## Prerequisites

- Python 3.12+
- Node.js 18+
- npm 9+

## Backend Setup

1. Create and activate a virtual environment (already present in this repo as backend/venv in local setup).
2. Install dependencies:

```bash
cd backend
venv\Scripts\pip install -r requirements.txt
```

3. Configure environment:

```bash
copy .env.example .env
```

Set at minimum:

- GEMINI_API_KEY (preferred) or GOOGLE_API_KEY
- GEMINI_MODEL=gemini-2.5-flash-lite

Optional backend settings:

- CATALOG_PATH
- CORS_ORIGINS (comma-separated list, for example: http://localhost:3000,http://127.0.0.1:3000)

4. Run backend:

```bash
venv\Scripts\python -m uvicorn --app-dir . api.main:app --host 127.0.0.1 --port 8000
```

## Frontend Setup

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Configure environment:

```bash
copy .env.example .env.local
```

Or create `.env` with the same values if you prefer a single local env file.

3. Run frontend:

```bash
npm run dev
```

Frontend default URL: http://localhost:3000

## Test Commands

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

## Notes

- `/api/chat` supports both JSON response mode and streaming mode (`stream: true`).
- The system is stateless and reconstructs conversation context from `conversation_history`.
- If both `GEMINI_API_KEY` and `GOOGLE_API_KEY` are missing, chat endpoints will return service-unavailable behavior.

## Problem Statement
ET has a large ecosystem that includes ET Prime, ET Markets, masterclasses, corporate events, wealth summits, and financial-services partnerships. However, most users discover only a small portion of what ET offers. The opportunity is to build an AI concierge that understands each user in a single conversation and then guides them to the most relevant ET products, services, and experiences.

## What You May Build
- **ET Welcome Concierge:** An AI voice or chat agent that greets new and returning users, runs a smart 3-minute profiling conversation, and maps each user to the right ET products through a personalized onboarding path.
- **Financial Life Navigator:** A deep conversational AI that understands a user's financial situation and directs them to suitable ET tools and partner services by identifying portfolio gaps, financial goals, and immediate needs.
- **ET Ecosystem Cross-Sell Engine:** An AI layer across ET touchpoints that proactively identifies cross-sell and upsell opportunities based on user behavior and profile, then engages users at the right moment with the right offer.
- **ET Services Marketplace Agent:** A conversational AI concierge for financial services such as credit cards, loans, insurance, and wealth management, delivered through ET partnerships.