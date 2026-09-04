# ALETHEIA Operational Command Center Frontend

The frontend for ALETHEIA is an operational incident command center designed under the **Orchid Noir** design system.

---

## 🎨 Design Philosophy (Orchid Noir)

- **Operational Density:** Table-first, high information density, restrained dark color palette with vivid accent tokens.
- **Diff Viewer:** High-precision unified/split diff viewer with line numbers, status badges, copy-to-clipboard, and approval/rejection safety gates.
- **Real-Time Visibility:** Live polling with explicit connectivity indicators (`Connecting` | `Production` | `Demo data`).

---

## 🛠️ Tech Stack

- **Framework:** React 18, TypeScript, Vite
- **Styling:** TailwindCSS, Custom CSS Tokens
- **Icons:** Lucide React
- **Deployment:** Vercel (`frontend/vercel.json`)

---

## 🚀 Local Development

```bash
# 1. Install dependencies
npm install

# 2. Run Vite development server
npm run dev
```

The frontend will be accessible at [http://localhost:5174](http://localhost:5174).

### Environment Variables
Configure `.env` or set environment variables:
```env
VITE_API_BASE_URL=http://localhost:8001/api/v1
VITE_API_KEY=your_api_key_here
```

---

## ☁️ Production Build & Vercel Deployment

```bash
# Build production bundle into /dist
npm run build
```

When deploying to **Vercel**:
1. Set Root Directory to `frontend`.
2. Framework Preset: `Vite`.
3. Add `VITE_API_BASE_URL` pointing to your Render backend (e.g. `https://aletheia-api.onrender.com/api/v1`).
4. Add `VITE_API_KEY`.
5. [`vercel.json`](vercel.json) handles SPA routing rewrites automatically.
