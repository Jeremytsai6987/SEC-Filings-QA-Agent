# SEC Filings Question Answering System

This project implements a production-grade question answering system over real SEC filings.
It supports complex financial research queries involving company fundamentals, risk factors, insider trading, compensation, and more — with precise source attribution and multi-dimensional control (by company, document type, time period).

---

## Features

* Answer open-ended financial research questions
* Automatically extracts companies, time ranges, document types from user queries
* Retrieves real SEC filings from `sec-api.io` (10-K, 10-Q, 8-K, DEF 14A, Forms 3/4/5)
* Synthesizes answers using OpenAI (`gpt-4o`) via `pydantic-ai` agents
* Provides inline citations `[C1]`, `[C2]` linked to real filing sources
* Supports single-ticker analysis, peer comparisons, trend analysis, and thematic queries

---

## Setup Instructions

### 1. Clone the repository and set up environment

```bash
git clone https://github.com/Jeremytsai6987/SEC-Filings-QA-Agent.git
cd sec-filing-qa-agent

python -m venv .venv
source .venv/bin/activate  # For Windows: .\.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Provide API keys

Set the following environment variables manually, or create a `.env` file:

```bash
export OPENAI_API_KEY=your-openai-key
export SEC_API_KEY=your-sec-api-key
```

### 4. Run the application

```bash
streamlit run streamlit_demo.py
```

Streamlit will launch at `http://localhost:8501`.

---

## Example Queries

Here are some sample prompts to try in the app:

* What are JPMorgan’s 2023 risk factors?
* Compare Apple and Microsoft’s revenue trends over time.
* What insider trading activity occurred recently for Tesla?
* How has Amazon’s executive compensation changed in recent filings?
* What climate risks are disclosed by energy companies?

---

## Sample Evaluation Questions

These questions are designed for benchmarking and feature validation:

1. What are the primary revenue drivers for major technology companies, and how have they evolved?
2. Compare R\&D spending trends across companies. What insights about innovation investment strategies?
3. Identify significant working capital changes for financial services companies and driving factors.
4. What are the most commonly cited risk factors across industries? How do same-sector companies prioritize differently?
5. How do companies describe climate-related risks? Notable industry differences?
6. Analyze recent executive compensation changes. What trends emerge?
7. What significant insider trading activity occurred? What might this indicate?
8. How are companies positioning regarding AI and automation? Strategic approaches?
9. Identify recent M\&A activity. What strategic rationale do companies provide?
10. How do companies describe competitive advantages? What themes emerge?

---

## Project Structure

```
sec-filing-qa-agent/
├── streamlit_demo.py         # Streamlit interface
├── qa_system.py              # Main QA pipeline
├── query_agent.py            # LLM query analyzer
├── analysis_agent.py         # LLM financial answer synthesizer
├── data_retriever.py         # SEC filings retriever (via sec-api.io)
├── company_resolver.py       # Ticker resolution and enrichment
├── models.py                 # Data models for queries and answers
├── requirements.txt
├── company_tickers.json                 
├── company_cache.json                 
└── README.md
```

---

## Notes

* Each cited answer includes links to real SEC filings via `[C#]` notation.
* The system processes a limited number of chunks (up to 6–8) to ensure concise and verifiable output.
* Output includes metadata such as companies analyzed, document types, time range, and any limitations or recommendations.

---

如果你需要我再根據實際 repo 的 `requirements.txt` 或補充部署教學（如 Docker、HuggingFace、Streamlit Cloud）都可以再說。
