import streamlit as st
import json
import os
import sys
import subprocess
import yaml
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

# Add current dir to path to import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from modules.notion_api import NotionAPI
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Stage Hunter 3000 PRO", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for Trading-Style Metrics
st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background-color: #1E1E1E;
        border: 1px solid #333;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetricValue"] {
        color: #00FFCC;
    }
    h1 {
        background: -webkit-linear-gradient(45deg, #00FFCC, #4A00E0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 Stage Hunter 3000 - Ultimate Terminal")

# --- DATA LOADING ---
CONFIG_PATH = "config.yaml"
DB_PATH = "data/jobs_db.json"
ANTI_PATTERNS_PATH = "data/anti_patterns.txt"

@st.cache_data(ttl=30)  # Refresh cache every 30 seconds
def load_data():
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
    # Fetch live data directly from Notion API
    notion = NotionAPI(CONFIG_PATH)
    jobs = notion.get_all_jobs()
    
    # Fallback to local DB if Notion fails or is empty
    if not jobs and os.path.exists(DB_PATH):
        with open(DB_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                jobs = sorted(data, key=lambda x: x.get('timestamp', ''), reverse=True)
            except:
                pass
    else:
        # Sort Notion jobs by timestamp descending
        jobs = sorted(jobs, key=lambda x: x.get('timestamp', ''), reverse=True)
        
    return config, jobs

config, jobs = load_data()

# --- SIDEBAR CONTROL ROOM ---
with st.sidebar:
    st.image(config.get("discord", {}).get("avatar_url", ""), width=100)
    st.markdown(f"**Agent:** {config.get('user_profile', {}).get('name', 'Operator')}")
    st.markdown("---")
    
    st.subheader("⚡ EXECUTION ENGINE")
    
    def get_scraper_status():
        try:
            if os.path.exists("data/scraper_status.json"):
                with open("data/scraper_status.json", "r") as f:
                    return json.load(f).get("status", "stopped")
        except:
            pass
        return "stopped"

    def set_scraper_status(status):
        os.makedirs("data", exist_ok=True)
        # Preserve heartbeat if it exists
        current_data = {}
        if os.path.exists("data/scraper_status.json"):
            try:
                with open("data/scraper_status.json", "r") as f:
                    current_data = json.load(f)
            except:
                pass
        current_data["status"] = status
        with open("data/scraper_status.json", "w") as f:
            json.dump(current_data, f)
            
    try:
        if os.path.exists("data/scraper_status.json"):
            with open("data/scraper_status.json", "r") as f:
                data = json.load(f)
                current_status = data.get("status", "stopped")
                last_heartbeat = data.get("heartbeat", 0)
        else:
            current_status = "stopped"
            last_heartbeat = 0
    except:
        current_status = "stopped"
        last_heartbeat = 0
        
    engine_is_dead = (time.time() - last_heartbeat) > 30 # Dead if no heartbeat for 30s
    
    if engine_is_dead:
        st.error("🚨 **MOTEUR ÉTEINT !**\n\nLe terminal exécutant le bot est fermé. Lance `python main.py search` dans ton terminal pour réactiver le bot.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        if current_status == "running":
            st.button("🟢 SCRAPER RUNNING", disabled=True, use_container_width=True)
        else:
            if st.button("▶️ START SCRAPER", type="primary", use_container_width=True, disabled=engine_is_dead):
                set_scraper_status("running")
                st.rerun()

    with col_b:
        if current_status == "stopped":
            st.button("🔴 SCRAPER STOPPED", disabled=True, use_container_width=True)
        else:
            if st.button("⏹️ STOP SCRAPER", type="primary", use_container_width=True):
                set_scraper_status("stopped")
                st.rerun()
            
    if st.button("✉️ LAUNCH: Gmail Sync", use_container_width=True):
        python_exec = sys.executable
        try:
            subprocess.Popen([python_exec, "main.py", "mail"], cwd=os.getcwd())
            st.toast("Email Sync Started!", icon="✅")
        except Exception as e:
            st.error(str(e))
            
    if st.button("🧠 LAUNCH: AI Learning", use_container_width=True):
        python_exec = sys.executable
        try:
            subprocess.Popen([python_exec, "main.py", "learn"], cwd=os.getcwd())
            st.toast("Neural Network Learning from Notion...", icon="✅")
        except Exception as e:
            st.error(str(e))

# --- PARSE DATAFRAME ---
df = pd.DataFrame()
if jobs:
    df_data = []
    for j in jobs:
        score = j.get("ai_score", 0)
        date_str = j.get("timestamp", "1970-01-01T")[:10]
        if date_str == "1970-01-01":
            date_str = None
            
        df_data.append({
            "Entreprise": j.get("company", "Unknown"),
            "Poste": j.get("title", "Unknown"),
            "Score IA": score if isinstance(score, (int, float)) else 0,
            "Localisation": j.get("location", "Unknown").split(",")[0],
            "Statut": j.get("status", "unknown"),
            "Date": date_str,
            "Lien Annonce": j.get("link", ""),
            "Lien Notion": j.get("notion_url", "")
        })
    df = pd.DataFrame(df_data)
    # Convert dates properly, keeping NaT for missing ones
    df["Date"] = pd.to_datetime(df["Date"], errors='coerce')

# --- MAIN TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Analytics (Funnel)", "💼 Master Pipeline", "⏰ Relances (Follow-ups)", "⚙️ Agent Settings"])

with tab1:
    st.markdown("### 📈 Entonnoir de Conversion (B2B)")
    if not df.empty:
        # CONVERSION METRICS
        total_jobs = len(df)
        total_applied = len(df[df["Statut"].isin(["Postulé", "En Cours", "En Attente", "Entretien", "Offre"])])
        total_interviews = len(df[df["Statut"].isin(["En Cours", "Entretien", "Offre", "Offre refusée"])])
        total_rejections = len(df[df["Statut"] == "Refusé"])
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Offres Sourcées", total_jobs)
        c2.metric("Candidatures Envoyées", total_applied, f"{(total_applied/total_jobs*100):.1f}% Conversion" if total_jobs else "0%")
        c3.metric("Entretiens Obtenus", total_interviews, f"{(total_interviews/total_applied*100):.1f}% Conversion" if total_applied else "0%")
        c4.metric("Refus Essuyés", total_rejections)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # FUNNEL CHART
        fig_funnel = go.Figure(go.Funnel(
            y=["Offres", "Candidatures", "Entretiens"],
            x=[total_jobs, total_applied, total_interviews],
            marker={"color": ["#1E3A8A", "#00FFCC", "#F59E0B"]}
        ))
        fig_funnel.update_layout(template="plotly_dark", title="Funnel d'Acquisition de Stage")
        
        # STATUS DISTRIBUTION
        status_counts = df[df["Statut"] != "None"]["Statut"].value_counts()
        fig_pie = px.pie(values=status_counts.values, names=status_counts.index, color_discrete_sequence=px.colors.qualitative.Pastel, template="plotly_dark", hole=0.4, title="Distribution des Statuts")
        
        r1, r2 = st.columns(2)
        r1.plotly_chart(fig_funnel, use_container_width=True)
        r2.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Aucune donnée pour le moment.")

with tab2:
    st.markdown("### 💼 Grille Active (Data Editor)")
    if not df.empty:
        c1, c2 = st.columns([1, 4])
        with c1:
            min_score = st.slider("Strictness Filter (Min Score %)", 0, 100, 0)
            status_filter = st.multiselect("Statuts à afficher", df["Statut"].unique(), default=list(df["Statut"].unique()))
            
        with c2:
            filtered_df = df[(df["Score IA"] >= min_score) & (df["Statut"].isin(status_filter))]
            display_df = filtered_df[["Score IA", "Statut", "Entreprise", "Poste", "Localisation", "Date", "Lien Annonce", "Lien Notion"]]
            
            # Use st.data_editor with specialized ColumnConfig
            st.data_editor(
                display_df,
                column_config={
                    "Lien Annonce": st.column_config.LinkColumn("Source", display_text="📍 Ouvrir l'offre"),
                    "Lien Notion": st.column_config.LinkColumn("Notion", display_text="📝 Ouvrir la carte"),
                    "Score IA": st.column_config.ProgressColumn("Score IA", format="%d", min_value=0, max_value=100),
                    "Date": st.column_config.DateColumn("Date d'ajout", format="DD/MM/YYYY")
                },
                use_container_width=True,
                hide_index=True,
                disabled=True, # We disable editing so we don't desync with Notion
                height=500
            )
    else:
        st.info("Pipeline is empty.")

with tab3:
    st.markdown("### ⏰ Relances Intelligentes (Follow-ups)")
    st.markdown("Candidatures envoyées il y a **plus de 7 jours** sans réponse (statut `Postulé` ou `En Attente`).")
    
    if not df.empty:
        # Filter for logic: Date is older than 7 days, and status is "Postulé" or "En Attente"
        seven_days_ago = pd.Timestamp(datetime.now() - timedelta(days=7))
        follow_up_df = df[
            (df["Statut"].isin(["Postulé", "En Attente"])) & 
            (df["Date"].notna()) & 
            (df["Date"] <= seven_days_ago)
        ].copy()
        
        if not follow_up_df.empty:
            follow_up_df["Jours d'attente"] = (pd.Timestamp(datetime.now()) - follow_up_df["Date"]).dt.days
            
            st.dataframe(
                follow_up_df[["Jours d'attente", "Entreprise", "Poste", "Lien Notion"]].sort_values("Jours d'attente", ascending=False),
                column_config={
                    "Lien Notion": st.column_config.LinkColumn("Ouvrir", display_text="➡️ Notion")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("Toutes les candidatures récentes sont fraîches ! Aucune relance urgente.")
    else:
        st.info("Aucune donnée.")

with tab4:
    st.markdown("### 🧠 Neural Network & Execution Engine")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### 🚫 Critical Anti-Patterns (Exclusion Rules)")
        if os.path.exists(ANTI_PATTERNS_PATH):
            with open(ANTI_PATTERNS_PATH, "r", encoding="utf-8") as f:
                patterns = f.read()
            st.code(patterns, language="markdown")
        else:
            st.warning("No patterns learned yet. Mark Notion jobs as 'NULL' and run AI Learning.")
            
    with col_b:
        st.markdown("##### ⚙️ LLM Configuration")
        st.json({
            "Model": config.get("llm", {}).get("model", "Unknown"),
            "Temperature": config.get("llm", {}).get("temperature", 0.7),
            "Core Target": config.get("search", {}).get("keywords", [])[0] if config.get("search", {}).get("keywords") else "None",
            "Database ID": config.get("notion", {}).get("database_id", "Hidden")
        })
