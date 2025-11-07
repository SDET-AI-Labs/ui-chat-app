# ChatStack — Pluggable Python Chat App (FastAPI + CLI)

A minimal, extensible chat service that can talk to multiple model types:

- **OpenAI-compatible APIs** (OpenAI, Groq, OpenRouter, etc.)
- **Ollama** (local models on your machine)

> Intentional constraints: No heavyweight frameworks. Simple, auditable code. Easy to extend.

---

## 1) Quickstart

### Prereqs
- Python 3.10+
- (Optional) [Ollama](https://ollama.com) installed locally for local models

### Create & activate a venv
**Linux/macOS**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install
```bash
pip install -U pip
pip install -e .
pip install Pillow  # required for visual baseline diffs in playwright_run tool
```

### Configure
Create a `.env` in the repo root. Examples:
```
# Choose default backend: openai_like or ollama
BACKEND=openai_like

# For OpenAI-compatible APIs
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# For Ollama
OLLAMA_BASE=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

### Run API
```bash
uvicorn chatstack.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Try it
```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json"   -d '{ "messages": [{"role":"user","content":"Say hi in 5 words"}] }'
curl -s -X POST http://localhost:8000/agent -H "Content-Type: application/json" \
	-d '{"messages":[{"role":"user","content":"tool: playwright_run {\"script\":\"await page.goto(\\\"https://example.com\\\")\",\"baseline\":\"homepage\"}"}],"tools_allowed":["playwright_run"]}'
```

### CLI
```bash
python -m chatstack.cli_chat
```

---

## 2) What you get

- **/chat** — POST endpoint for chat completions (non-streaming)
- **/chat/stream** — SSE endpoint for token streaming
- **Adapters**: `openai_like`, `ollama` (easy to add more)
- **SQLite** transcript store for sessions
- **.env** config via Pydantic `BaseSettings`

---

## 3) Extending
### Visual Baseline Diff (Playwright Tool)

If you pass a `baseline` name in the args to `playwright_run`, the tool will:
1. Capture a screenshot (auto-enables screenshot even if `screenshot` arg not set).
2. Create `./data/baseline/<name>.png` if it doesn't exist and return `result: baseline_created`.
3. On subsequent runs, compare the current screenshot to the baseline (pixel diff) and return:
	- `result: pass|fail` (≤2% pixel difference passes)
	- `diff_percent` (float)
	- `screenshot` (current run path)
	- `baseline` (baseline path)

Install Pillow (`pip install Pillow`) to enable this comparison. Without it you'll get an error message prompting installation.


Create a new file in `src/chatstack/models/your_backend.py` implementing `ChatBackend`,
then register it in `models/__init__.py`. See existing adapters for examples.

---

## 4) About GitHub Copilot

You **cannot** use Copilot as a runtime LLM in your app. It's an IDE assistant, not an inference API.
Use it to speed up coding, but wire your app to OpenAI-compatible APIs or local Ollama.

---

## 5) License

MIT
