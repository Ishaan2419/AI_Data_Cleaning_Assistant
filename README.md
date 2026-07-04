# ✨ AI Data Cleaning Assistant

A premium, locally-run SaaS-style data cleaning tool. Upload a CSV/Excel file,
let a local Llama 3 model (via **Ollama**) explain your dataset, review every
detected data-quality issue, and approve each fix yourself — nothing is ever
cleaned automatically.

**100% local. No OpenAI, no Gemini, no Claude API, no paid services.**

---

## 🧱 Project Structure

```
ai_data_cleaning_assistant/
├── app.py                      # Main Streamlit entry point
├── requirements.txt
├── .streamlit/config.toml      # Streamlit base theme
├── config/settings.py          # Global constants & thresholds
├── core/
│   ├── data_loader.py          # Upload parsing + metadata + column classification
│   ├── quality_scorer.py       # 0-100 data quality scoring engine
│   ├── issue_detector.py       # Issue detection engine (Phase 1: 8 detectors)
│   ├── cleaning_engine.py      # Cleaning operations + undo/redo history
│   └── ai_engine.py            # Ollama/Llama integration (insights, explain, chat)
├── ui/
│   ├── theme.py                # Glassmorphism CSS, dark/light mode
│   ├── landing_page.py         # Hero landing page + upload zone
│   └── components.py           # KPI cards, issue cards, gauges
└── utils/
    ├── logger.py                # Centralized logging
    └── validators.py            # Email/phone/URL/pincode validators
```

---

## ⚙️ Setup

### 1. Install Ollama (one-time)

Download from **https://ollama.com** and install for your OS, then pull a model:

```bash
ollama pull llama3.1
ollama serve        # starts the local Ollama server on http://localhost:11434
```

Keep `ollama serve` running in a terminal while you use the app (on macOS/Windows
the desktop app usually keeps this running for you automatically).

### 2. Install Python dependencies

```bash
cd ai_data_cleaning_assistant
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the app

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

---

## 🧪 How to test it

1. **Landing page** — you should see the animated gradient hero title, feature
   cards, and an upload dropzone (not default Streamlit styling).
2. **Upload a messy CSV** — try one with some missing values, duplicate rows,
   a constant column, and inconsistent capitalization (e.g. "Mumbai" vs
   "mumbai"). You can generate a quick test file with:
   ```python
   import pandas as pd, numpy as np
   df = pd.DataFrame({
       "Name": ["Alice", "alice", "Bob", " Bob "] * 25,
       "Age": list(np.random.randint(18, 60, 90)) + [None]*10,
       "City": ["Mumbai", "mumbai", "Delhi"] * 33 + ["Delhi"],
       "Flag": ["X"] * 100,
   })
   df.to_csv("test_data.csv", index=False)
   ```
3. **Overview tab** — check rows/columns/memory/missing %/duplicate % and the
   quality gauge render correctly.
4. **AI Insights tab** — click "Analyze Dataset with AI". Requires Ollama
   running; if it's not reachable you'll see a clear setup instruction instead
   of a crash.
5. **Issues & Cleaning tab** — this is the core feature. Each issue is a card
   with a severity badge, plain-English description, and an AI recommendation.
   Click **Accept** to apply the suggested (or an alternative) method, or
   **Skip** to leave it. The dashboard and quality score update immediately.
6. **Dashboard tab** — histograms, box plots, correlation heatmap, pie charts,
   and a missing-value heatmap, all reflecting the *current* cleaned state.
7. **History tab** — see every applied action with a timestamp, and test
   **Undo/Redo**.
8. **Chatbot tab** — ask "Explain this dataset" or click a quick-question chip.

---

## 🗺️ Roadmap (next phases)

This is **Phase 1** of the build — a fully working core loop (upload → AI
understanding → 8-detector issue review with approval → live dashboard →
history with undo/redo → chatbot). Planned next phases, to be added the same
modular way:

- **Phase 2:** Full issue catalog (outliers, invalid emails/phones/URLs,
  encoding issues, skewness, correlation/leakage, imbalance, rare categories,
  boolean/date issues, infinite/negative/zero values) plugged into the same
  `detect_all_issues()` registry.
- **Phase 3:** Export (CSV/Excel/JSON), PDF/HTML report generation with
  before/after charts and AI summary.
- **Phase 4:** Settings panel (font size, chart color themes, language),
  `ydata-profiling` deep-dive report, `great_expectations` validation suite.

Because everything is registered through `METHOD_REGISTRY` (cleaning_engine.py)
and the detector list in `detect_all_issues()` (issue_detector.py), adding new
issue types or cleaning methods never requires touching existing code — just
add a new function and register it.

---

## 🔒 Notes

- No API keys are used or required anywhere in this codebase.
- If Ollama isn't running, every AI feature degrades gracefully with a clear
  setup message instead of crashing the app.
- All processing happens on your machine — uploaded files never leave it.
