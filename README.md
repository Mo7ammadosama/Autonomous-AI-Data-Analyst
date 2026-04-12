# 🧠 DataMind AI — Autonomous AI Data Analyst

> Enterprise-grade AI-powered analytics platform. Upload datasets, chat with your data, generate dashboards, and receive automated insights.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- npm 9+

---

### Backend Setup

```bash
cd backend

# 1. Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY (optional)

# 4. Start the API server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API available at: http://localhost:8000
API docs at: http://localhost:8000/docs

---

### Frontend Setup

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Start the development server
npm run dev
```

Frontend available at: http://localhost:3000

---

## 🔑 First Login

1. Open http://localhost:3000
2. Click **"Try Demo — No signup required"** for instant access
3. Or register a new account

---

## 🤖 AI Configuration

### Option A: OpenAI (recommended)
Add to `backend/.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

### Option B: Ollama (local, free)
1. Install Ollama from https://ollama.ai
2. Run: `ollama pull llama3`
3. Add to `backend/.env`:
```
USE_OLLAMA=true
OLLAMA_MODEL=llama3
```

### Option C: No LLM (rule-based)
Works without any AI configuration — uses built-in statistical analysis.

---

## 📁 Project Structure

```
AUTONOMOUS_AI_DATA_ANALYST/
├── backend/                  # FastAPI backend
│   ├── main.py               # App entry point
│   ├── models/               # SQLAlchemy models
│   ├── routers/              # API route handlers
│   ├── services/             # Business logic
│   │   ├── ai_agent.py       # Autonomous AI agent
│   │   ├── data_processor.py # Data analysis engine
│   │   ├── llm_service.py    # LLM abstraction
│   │   └── visualization.py  # Chart generation
│   ├── security/             # JWT auth
│   └── requirements.txt
│
├── frontend/                 # Next.js 14 frontend
│   ├── src/app/              # App router pages
│   │   ├── page.tsx          # Login/landing
│   │   ├── dashboard/        # Overview dashboard
│   │   ├── datasets/         # Dataset manager + upload
│   │   ├── chat/             # AI chat interface
│   │   ├── analytics/        # Analytics explorer
│   │   ├── insights/         # AI insights
│   │   ├── dashboards/       # Dashboard builder
│   │   ├── reports/          # Report generation
│   │   └── settings/         # Configuration
│   ├── src/components/       # Reusable components
│   └── src/lib/              # API client, store, utils
│
└── README.md
```

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📊 Dataset Manager | Upload CSV, JSON, Excel with drag & drop |
| 🤖 AI Chat | Ask questions in plain English |
| 📈 Analytics Explorer | Correlations, outliers, distributions, ML |
| 💡 AI Insights | Auto-generated business insights |
| 🎛️ Dashboards | Auto-generate dashboards from commands |
| 📄 Reports | PDF report generation with charts |
| 🔐 Auth | JWT-based auth with roles |
| 🌙 Dark Mode | Professional dark UI throughout |

---

## 🛠 Tech Stack

**Backend:** FastAPI · SQLAlchemy · Pandas · NumPy · Scikit-learn · Plotly · JWT

**Frontend:** Next.js 14 · React · TypeScript · Tailwind CSS · Framer Motion · Plotly.js · Zustand

**AI:** OpenAI GPT-4o-mini · Ollama (local) · Rule-based fallback

---

## 📝 Environment Variables

### Backend (`backend/.env`)
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./ai_analyst.db` | Database connection |
| `SECRET_KEY` | (change this!) | JWT signing key |
| `UPLOAD_DIR` | `./uploads` | Dataset storage path |
| `OPENAI_API_KEY` | `` | OpenAI API key |
| `USE_OLLAMA` | `false` | Use Ollama instead |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3` | Ollama model name |

---

## 🐛 Troubleshooting

**Backend won't start:** Check Python version (`python --version` ≥ 3.10) and that all packages installed.

**CORS errors:** Ensure backend is running on port 8000 and frontend on port 3000.

**Charts not rendering:** Plotly.js requires a browser environment. SSR is handled — refresh if blank.

**Upload fails:** Check `uploads/` directory exists and is writable in the backend folder.

**PDF download fails:** Install reportlab: `pip install reportlab`
