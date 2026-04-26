# \ud83c\udf93 StudyMate AI \u2014 Single-Project (FastAPI + Vercel)

Full AI study app. **Pure Python backend serves the frontend too** \u2014 one repo, one deploy, no Docker.

## Features
- Auth (JWT, bcrypt, signup/login)
- Personalized study plans
- AI tutor (step-by-step / Socratic / exam-focused) with voice I/O
- RAG: ingest PDF / URL / YouTube \u2192 keyword search \u2192 cited answers + confidence
- Auto notes (short / detailed / bullet / Mermaid mindmap)
- Live DuckDuckGo search + AI summary
- Adaptive MCQ quizzes with explanations
- Flashcards with **SM-2 spaced repetition**
- Coding mentor (Python / JS / Java / C++ / SQL)
- Pomodoro timer (client-side)
- Exam strategy optimizer
- Progress dashboard with weak-area detection
- Multilingual, dark/light mode, mobile responsive

## Run locally (one command)
```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env \u2192 paste GROQ_API_KEY (free at https://console.groq.com)
python app.py
```
Open http://localhost:8000

Default admin: `admin@studymate.local` / `admin1234`

## Deploy to Vercel (one project)
1. Push this repo to GitHub.
2. On [vercel.com](https://vercel.com) \u2192 **Add New \u2192 Project** \u2192 import your repo.
3. Framework preset: **Other** (Vercel detects `vercel.json` automatically).
4. **Settings \u2192 Environment Variables** add:
   - `GROQ_API_KEY` \u2192 your free Groq key
   - `JWT_SECRET` \u2192 a long random string
   - *(optional)* `DATABASE_URL` \u2192 a free Postgres URL from [Neon](https://neon.tech) or [Supabase](https://supabase.com)
     - Format: `postgresql://user:pass@host/db`
     - If omitted, SQLite is used in `/tmp` (resets on cold start \u2014 fine for testing).
5. Click **Deploy**. Done. Your app is live at `https://your-project.vercel.app`.

## Notes on Vercel limits
- Vercel functions have a 10s execution limit on the free plan, 60s on Pro. Long LLM calls (>10s) may time out on free tier \u2014 Groq is fast (typically 1\u20133s) so this works well.
- For persistent data, use **Neon** (free 512 MB Postgres) or **Vercel Postgres**.
- Pomodoro runs in the browser \u2014 no server timer needed.
- WebSocket-based collaborative rooms are not included in the Vercel build (serverless functions don't support WS). Use the local `python app.py` mode if you need them.

## File structure
```
.
\u251c\u2500 app.py              # FastAPI app: API + serves frontend
\u251c\u2500 static/index.html   # SPA (Tailwind CDN + vanilla JS)
\u251c\u2500 api/index.py        # Vercel entry
\u251c\u2500 vercel.json
\u251c\u2500 requirements.txt
\u251c\u2500 .env.example
\u2514\u2500 README.md
```

## API surface
All under `/api/*`. Open `/docs` locally for interactive Swagger UI.

- `POST /api/auth/signup`, `POST /api/auth/login`, `GET /api/me`
- `POST /api/plans`, `GET /api/plans`
- `POST /api/tutor`
- `POST /api/rag/ingest/url`, `POST /api/rag/ingest/pdf`, `GET /api/rag/documents`, `DELETE /api/rag/documents/{id}`, `POST /api/rag/ask`
- `POST /api/search`
- `POST /api/notes`, `GET /api/notes`
- `POST /api/quiz/generate`, `POST /api/quiz/submit`
- `POST /api/flashcards/generate`, `GET /api/flashcards/due`, `POST /api/flashcards/review`
- `POST /api/coding/help`
- `POST /api/exam/strategy`
- `GET /api/analytics/progress`
- `GET /api/health`
