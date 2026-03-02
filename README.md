# 🎯 Stage Hunter 3000

Stage Hunter 3000 is an automated internship hunting robot. It silently scrapes job boards (like LinkedIn) in the background, scores the offers against your personal CV using an AI model, pushes the best opportunities to a Notion database, and alerts you via Discord. 

It comes with a full Streamlit Dashboard to monitor the engine's real-time performance.

## 🚀 Features

*   **🕵️ Automated Scraping:** Periodically scans for internships based on your custom queries and locations, bypassing basic anti-bot defenses with a headless browser.
*   **🧠 AI Scoring System:** Uses a local LLM (via LM Studio/AnythingLLM) to analyze the job description against your `master_cv.pdf`. It assigns a `MATCH_SCORE` out of 100, lists pros/cons, and provides an improvement plan for your application.
*   **📝 Notion Integration:** Automatically saves high-scoring jobs to a Notion Database, preventing duplicate entries via URL tracking.
*   **🔔 Discord Notifications:** Sends rich embed alerts directly to a Discord webhook when a matching job is found, as well as a status update if a scan finds nothing.
*   **🎛️ Interactive Dashboard:** A Streamlit GUI allowing you to view live statistics, monitor recently scraped jobs, and securely Start/Stop the background engine.
*   **🔄 Heartbeat Safety:** The dashboard actively tracks a heartbeat from the background engine so it accurately displays if the scraper is running or crashed.

## 🛠️ Setup Instructions

### 1. Prerequisites
*   Python 3.10+
*   Google Chrome installed (for Selenium WebDriver)
*   A running local LLM API (like LM Studio) acting as an OpenAI drop-in replacement.
*   A Notion Integration Token and Database ID.
*   A Discord Webhook URL.

### 2. Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/theo2212/bot_stage.git
   cd bot_stage
   ```
2. Create and activate a Virtual Environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Mac/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Configuration
1. Rename `config.example.yaml` to `config.yaml`.
2. Open `config.yaml` and fill out your specific tokens:
   *   `notion.token` and `notion.database_id`
   *   `discord.webhook_url`
   *   `search.keywords` and `search.locations`
3. Place your resume PDF at `data/resumes/master_cv.pdf`.

## ▶️ Usage

### Start the Engine
To start the background scraper engine, simply run:
```bash
python main.py search
```
*Note: The engine sleeps for 10 minutes between full scan cycles to avoid getting IP banned.*

### Open the Dashboard
To open the control panel, open a **separate terminal** and run:
```bash
python -m streamlit run dashboard.py
```

## ⚠️ Disclaimer
This is an educational project. Web scraping may violate the Terms of Service of some job platforms. Use responsibly, do not lower the sleep intervals, and rely on local LLMs to avoid massive API costs.
