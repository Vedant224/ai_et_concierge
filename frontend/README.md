# Frontend - ET AI Concierge

## Overview
This frontend is a Next.js chat interface for the ET AI Concierge.
It sends full conversation history to the backend and renders streaming responses in real time.

## Tech Stack
- Next.js
- React
- TypeScript
- Vitest + Testing Library

## Setup
1. Open a terminal in the frontend folder.

```bash
cd frontend
```

2. Install dependencies.

```bash
npm install
```

3. Create local environment file.

```bash
copy .env.example .env.local
```

4. Set backend URL in environment file:
- `NEXT_PUBLIC_API_URL=http://localhost:8000`

## Run
```bash
npm run dev
```

App URL:
- `http://localhost:3000`

## Scripts
- `npm run dev` - Start development server
- `npm run build` - Production build
- `npm run start` - Run production server
- `npm run type-check` - TypeScript checks
- `npm run test` - Test suite

## Tests
```bash
npm run type-check
npm run test
```
