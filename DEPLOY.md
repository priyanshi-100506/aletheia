# ALETHEIA — 100% Free-Tier Cloud Deployment Guide

Deploy the full ALETHEIA stack (FastAPI Backend, ARQ Background Worker, PostgreSQL DB, Redis Queue, and React Frontend) with **$0/month cost** using modern serverless and free-tier platforms.

---

## Target Topology

| Component | Platform | Free Tier Limits |
|-----------|----------|------------------|
| **Database** | [Neon Postgres](https://neon.tech) | 0.5 GB storage, serverless, automated branching |
| **Queue / Cache** | [Upstash Redis](https://upstash.com) | 10,000 commands/day, serverless TLS Redis |
| **Backend & Worker** | [Render](https://render.com) | 750 free instance hours/month (Web Service) |
| **Frontend UI** | [Vercel](https://vercel.com) | Unlimited bandwidth & deployments for hobby |
| **AI Engine** | [Google AI Studio](https://aistudio.google.com) | Free rate limits for Gemini 2.0 Flash |

---

## Step 1: Provision Neon PostgreSQL

1. Sign up at [neon.tech](https://neon.tech).
2. Create a new project named `aletheia-db`.
3. Copy the **Connection String** from the Neon dashboard. It looks like:
   ```
   postgresql://user:password@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. ALETHEIA's `app/db/database.py` automatically converts `postgresql://` to `postgresql+asyncpg://` and handles `sslmode=require` / `ssl=require` for asyncpg.

---

## Step 2: Provision Upstash Redis

1. Sign up at [upstash.com](https://upstash.com).
2. Create a new database named `aletheia-redis` in the region closest to your Render service (e.g., `us-east-1`).
3. Under the **Details** tab, copy the **`rediss://...`** URL (TLS enabled).
   ```
   rediss://default:your-token@your-endpoint.upstash.io:6379
   ```

---

## Step 3: Deploy Backend & Worker on Render

Render's free tier provides 750 hours/month for a single web service. To avoid splitting hours between two services (which would run out after 15 days), ALETHEIA supports running the ARQ background worker **in-process** within the FastAPI application via `RUN_WORKER_INPROCESS=true`.

### Option A: Using `render.yaml` (Blueprint)
1. Fork or push your ALETHEIA repository to GitHub.
2. In Render, go to **Blueprints** -> **New Blueprint Instance**.
3. Connect your repository. Render will automatically read [`render.yaml`](render.yaml).
4. Fill in the required environment variables in the dashboard:
   - `DATABASE_URL`: Your Neon connection string
   - `REDIS_URL`: Your Upstash `rediss://...` connection string
   - `GEMINI_API_KEY`: Your Google Gemini API Key
   - `GITHUB_TOKEN`: GitHub Personal Access Token (`repo` scope)
   - `API_KEY`: A generated 32-character secret (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
   - `WEBHOOK_SECRET`: A generated secret for HMAC signature verification
   - `RUN_WORKER_INPROCESS`: `true`
   - `FRONTEND_ORIGINS`: Your Vercel domain (e.g. `https://aletheia.vercel.app,http://localhost:5174`)

### Option B: Manual Web Service Setup
1. In Render, click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Configure settings:
   - **Name:** `aletheia-api`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** `Free`
4. Add the Environment Variables listed in Option A.

Your backend will be live at: `https://aletheia-api.onrender.com` (Health check: `/health`).

---

## Step 4: Deploy Frontend on Vercel

1. Sign up / log in to [vercel.com](https://vercel.com).
2. Click **Add New** -> **Project** and import your GitHub repository.
3. Set the **Root Directory** to `frontend`.
4. Vercel will automatically detect **Vite**.
5. Under **Environment Variables**, add:
   - `VITE_API_BASE_URL`: Your Render backend URL (e.g., `https://aletheia-api.onrender.com/api/v1`)
   - `VITE_API_KEY`: The same `API_KEY` set in Render backend
6. Click **Deploy**.

[`frontend/vercel.json`](frontend/vercel.json) handles client-side SPA routing rewrites automatically.

---

## Step 5: Verify End-to-End Pipeline

1. Open your Vercel URL in your browser.
2. The frontend will connect to Render backend and show the ALETHEIA dashboard.
3. Test sending an incident webhook:
   ```bash
   curl -X POST https://aletheia-api.onrender.com/api/v1/webhooks/ingest \
     -H "Content-Type: application/json" \
     -H "X-API-Key: <YOUR_API_KEY>" \
     -d '{
       "error_log": "TypeError: Cannot read properties of undefined (reading '\''id'\'')",
       "target_file": "app/services/payment.py"
     }'
   ```
4. The incident appears in real-time on your dashboard.
5. Review the AI-generated diff and approve to open a GitHub PR!
