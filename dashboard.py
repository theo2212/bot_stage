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
from modules.db_manager import DBManager
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Stage Hunter 3000 PRO", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for Premium Glassmorphism & Cyberpunk Aesthetics
st.markdown("""
<style>
    /* Global Background and Fonts */
    .stApp {
        background-color: #0A0F1C;
        font-family: 'Inter', sans-serif;
    }
    
    /* Metrics Styling */
    div[data-testid="stMetric"] {
        background-color: rgba(16, 24, 39, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        transition: transform 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        border-color: rgba(0, 255, 204, 0.4);
        box-shadow: 0 10px 40px rgba(0, 255, 204, 0.15);
    }
    div[data-testid="stMetricValue"] {
        color: #00FFCC !important;
        font-size: 2.8rem !important;
        font-weight: 800 !important;
        text-shadow: 0px 0px 10px rgba(0, 255, 204, 0.3);
    }
    div[data-testid="stMetricLabel"] {
        color: #94A3B8 !important;
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }

    /* Headers */
    h1 {
        background: linear-gradient(135deg, #00FFCC 0%, #3B82F6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 900 !important;
        font-size: 3.2rem !important;
        margin-bottom: 1.5rem !important;
        letter-spacing: -1px;
    }
    h3 {
        color: #F8FAFC !important;
        font-weight: 700 !important;
        border-bottom: 2px solid rgba(255,255,255,0.05);
        padding-bottom: 10px;
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 12px !important;
        font-weight: 700 !important;
        height: 3.2rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        text-transform: uppercase;
        letter-spacing: 1px;
        border: none !important;
    }
    .stButton>button[kind="primary"] {
        background: linear-gradient(90deg, #3B82F6, #8B5CF6);
        color: white !important;
        box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
    }
    .stButton>button[kind="primary"]:hover {
        box-shadow: 0 6px 25px rgba(139, 92, 246, 0.5) !important;
        transform: translateY(-2px);
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0E1526;
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    
    /* DataFrame */
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.05);
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 Stage Hunter 3000 - Ultimate Terminal")

# --- DATA LOADING ---
CONFIG_PATH = "config.yaml"
ANTI_PATTERNS_PATH = "data/anti_patterns.txt"
# Use absolute paths so dashboard and main.py always share the same file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "data", "scraper_status.json")
LIVE_STATE_FILE = os.path.join(BASE_DIR, "data", "live_state.json")

# Remove caching so data represents the live SQLite DB state.
def load_data():
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
    # Fetch live data directly from SQLite DB
    try:
        db = DBManager()
        jobs = db.get_all_jobs()
    except Exception as e:
        jobs = []
        st.sidebar.error(f"DB Error: {e}")
        
    return config, jobs

config, jobs = load_data()

# --- SIDEBAR CONTROL ROOM ---
with st.sidebar:
    st.image(config.get("discord", {}).get("avatar_url", ""), width=100)
    st.markdown(f"**Agent:** {config.get('user_profile', {}).get('name', 'Operator')}")
    st.markdown("---")
    
    # NAVIGATION SYSTEM
    st.subheader("🧭 NAVIGATION")
    page = st.radio("Go to Explorer", [
        "🏠 Control Center",
        "🎯 Live Hunter",
        "🗃️ Database",
        "✉️ Auto-Mailing",
        "📊 Market Insights",
        "🧠 AI Lab"
    ], label_visibility="collapsed")
    
    st.markdown("---")
    st.subheader("⚡ EXECUTION ENGINE")
    
    def get_scraper_status():
        try:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, "r") as f:
                    return json.load(f).get("status", "stopped")
        except:
            pass
        return "stopped"

    def set_scraper_status(status):
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        current_data = {}
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, "r") as f:
                    current_data = json.load(f)
            except:
                pass
        current_data["status"] = status
        with open(STATUS_FILE, "w") as f:
            json.dump(current_data, f)
            
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r") as f:
                data = json.load(f)
                current_status = data.get("status", "stopped")
                last_heartbeat = data.get("heartbeat", 0)
        else:
            current_status = "stopped"
            last_heartbeat = 0
    except:
        current_status = "stopped"
        last_heartbeat = 0
        
    # Dead if no heartbeat for 60s (Increased from 30s to allow startup time)
    engine_is_dead = (time.time() - last_heartbeat) > 60 
    
    # Auto-correct ghost state: Only if it's been running for a while without heartbeat
    if engine_is_dead and current_status == "running" and last_heartbeat > 0:
        current_status = "stopped"
        set_scraper_status("stopped")
    
    if engine_is_dead:
        st.warning("⚠️ **MOTEUR ÉTEINT** : Le processus principal (main.py) ne tourne pas.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        if current_status == "running":
            # Active button shows as a distinct state but remains clickable to allow "Re-launch/Force"
            st.button("🟢 RUNNING", disabled=False, key="running_btn", use_container_width=True)
        else:
            if st.button("▶️ START", type="primary", use_container_width=True):
                set_scraper_status("running")
                if engine_is_dead:
                    try:
                        flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                        script_path = os.path.join(BASE_DIR, "main.py")
                        subprocess.Popen(
                            [sys.executable, script_path, "search"], 
                            cwd=BASE_DIR,
                            creationflags=flags
                        )
                        st.toast("Bot lancé !", icon="🚀")
                    except Exception as e:
                        st.error(f"Erreur: {e}")
                st.rerun()

    with col_b:
        if current_status == "stopped":
            # Active button shows as a distinct state
            st.button("🔴 STOPPED", disabled=False, key="stopped_btn", use_container_width=True)
        else:
            if st.button("⏹️ STOP", type="primary", use_container_width=True):
                try:
                    # Get PID from the standardized STATUS_FILE
                    if os.path.exists(STATUS_FILE):
                        with open(STATUS_FILE, "r") as f:
                            data = json.load(f)
                            pid = data.get("pid")
                    else:
                        pid = None

                    set_scraper_status("stopped")

                    if pid:
                        import subprocess
                        import signal
                        if os.name == 'nt':
                            try:
                                # Force kill the entire process tree on Windows
                                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True, check=False)
                            except: pass
                            try: os.kill(pid, signal.SIGTERM)
                            except: pass
                        else:
                            try: os.kill(pid, signal.SIGINT)
                            except: pass
                            os.kill(pid, signal.SIGTERM)
                except Exception as e:
                    print(f"Error killing process: {e}")
                st.rerun()

# --- PARSE DATAFRAME FOR INSIGHTS ---
df = pd.DataFrame()
if jobs:
    df_data = []
    for j in jobs:
        score = j.get("ai_score", 0)
        # Parse Dates
        scraped_dt = j.get("date_scraped", None)
        crit = j.get("ai_critique")
        
        # Safely extract critique items if they exist
        pros = "N/A"
        short_desc = "N/A"

        if crit and isinstance(crit, dict):
            # Split PROS/CONS cleanly - only keeping pros this time
            full_pros_cons = crit.get("PROS_CONS", "N/A")
            if "Inconvénient" in full_pros_cons:
                parts = full_pros_cons.split("Inconvénient")
                pros = parts[0].replace("Avantage", "").replace("s :", "").replace(" :", "").strip()
            else:
                pros = full_pros_cons
            if isinstance(pros, list):
                pros = "\n".join([str(p) for p in pros])
            
            short_desc = crit.get("SHORT_DESCRIPTION", "N/A")
            if isinstance(short_desc, list):
                short_desc = "\n- ".join([str(s) for s in short_desc])
                if short_desc:
                    short_desc = "- " + short_desc

        # Read local files for Letters and CVs
        safe_company = "".join([c for c in str(j.get('company', '')) if c.isalnum() or c in (' ', '_')]).strip()
        output_dir = os.path.join("data", "output", safe_company)
        
        lm_text = "Non générée (Score trop bas ou ancienne offre)"
        lm_path = os.path.join(output_dir, "Cover_Letter.txt")
        if os.path.exists(lm_path):
            try:
                with open(lm_path, "r", encoding="utf-8") as f:
                    lm_text = f.read()
            except: pass
            
        cv_text = "Non généré"
        cv_path = os.path.join(output_dir, "CV_Optimization.txt")
        if os.path.exists(cv_path):
            try:
                with open(cv_path, "r", encoding="utf-8") as f:
                    cv_text = f.read()
            except: pass

        loc = j.get("location")
        loc_str = str(loc).split(",")[0] if loc else "Unknown"

        df_data.append({
            "Entreprise": str(j.get("company", "Unknown")),
            "Poste": str(j.get("title", "Unknown")),
            "Score IA": score if isinstance(score, (int, float)) else 0,
            "Localisation": str(loc_str),
            "Statut": str(j.get("status", "unknown")),
            "Date d'Ajout": scraped_dt,
            "Points Forts": str(pros),
            "À propos de": str(short_desc),
            "Lettre de Motivation": str(lm_text),
            "CV Optimisation": str(cv_text),
            "Lien Annonce": str(j.get("link", "")),
            "Critique IA": crit
        })
    df = pd.DataFrame(df_data)
    df["Date d'Ajout"] = pd.to_datetime(df["Date d'Ajout"], errors='coerce')

# --- ROUTER SYSTEM ---
if page == "🏠 Control Center":
    st.markdown("### 📈 Entonnoir de Conversion (B2B)")
    if not df.empty:
        total_jobs = len(df)
        total_applied = len(df[df["Statut"].isin(["Sent to Notion", "applied_locally", "En Cours", "En Attente", "Entretien", "Offre"])])
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Offres Scrutées (IA)", total_jobs)
        c2.metric("Candidatures Validées", total_applied, f"{(total_applied/total_jobs*100):.1f}% Conversion" if total_jobs else "0%")
        c3.metric("Rejetées par l'IA", total_jobs - total_applied)
        c4.metric("Engine Health", "100%", "Online" if not engine_is_dead else "Offline")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        fig_funnel = go.Figure(go.Funnel(
            y=["Total Analysé", "Validé par IA (>80%)"],
            x=[total_jobs, total_applied],
            marker={"color": ["#1E3A8A", "#00FFCC"]}
        ))
        fig_funnel.update_layout(template="plotly_dark", title="Acquisition Funnel")
        
        status_counts = df[df["Statut"].notna()]["Statut"].value_counts()
        fig_pie = px.pie(values=status_counts.values, names=status_counts.index, color_discrete_sequence=px.colors.qualitative.Pastel, template="plotly_dark", hole=0.4, title="Distribution des Statuts globaux")
        
        r1, r2 = st.columns(2)
        r1.plotly_chart(fig_funnel, width="stretch")
        r2.plotly_chart(fig_pie, width="stretch")
    else:
        st.info("Aucune donnée dans la base locale pour le moment.")

elif page == "🎯 Live Hunter":
    st.markdown("### 🎯 Live Hunter Dashboard")
    st.markdown("Vois en temps réel sur quoi l'I.A. est en train de réfléchir.")
    
    if current_status == "running":
        import time
        try:
            with open("data/live_state.json", "r", encoding="utf-8") as f:
                state = json.load(f)
                
            st.info(f"**Statut Actuel:** {state.get('status', 'N/A')}")
            
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("#### ⚙️ Logs Moteur")
                logs = state.get('logs', [])
                st.code("\n".join(logs), language="bash")
                
            with c2:
                st.markdown("#### 🔍 Dernières offres vues")
                live_jobs = state.get('jobs', [])
                if live_jobs:
                    st.dataframe(pd.DataFrame(live_jobs), use_container_width=True)
                
            time.sleep(2)
            st.rerun()
            
        except Exception as e:
            st.warning("En attente des données du moteur...")
            time.sleep(2)
            st.rerun()
    else:
        st.info("Le scraper est actuellement arrêté. Lance-le pour voir les logs en direct.")
    
elif page == "🗃️ Database":
    db_c1, db_c2 = st.columns([5, 1])
    with db_c1:
        st.markdown("### 🗃️ SQLite Master Database")
        st.markdown("L'historique complet, brut et sans censure de chaque job scanné par le bot.")
    with db_c2:
        if st.button("🔄 Rafraîchir Tableau"):
            st.rerun()

    if not df.empty:
        display_df = df[["Lien Annonce", "Score IA", "Statut", "Entreprise", "Poste", "Localisation", "Date d'Ajout", "Points Forts", "À propos de", "Lettre de Motivation", "CV Optimisation"]]
        
        st.data_editor(
                display_df,
                column_config={
                    "Lien Annonce": st.column_config.LinkColumn("Offre", display_text="📍 Ouvrir"),
                    "Score IA": st.column_config.ProgressColumn("Score IA", format="%d", min_value=0, max_value=100),
                    "Date d'Ajout": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY"),
                    "Points Forts": st.column_config.TextColumn("Points Forts", width="large"),
                    "À propos de": st.column_config.TextColumn("À propos de", width="large"),
                    "Lettre de Motivation": st.column_config.TextColumn("Lettre de Motivation", width="large"),
                    "CV Optimisation": st.column_config.TextColumn("CV Optimisation", width="large")
                },
                width="stretch",
                hide_index=True,
                disabled=True, 
                height=600
            )
            
        st.markdown("#### 🔍 AI Inspector (Lettres & Critiques locales)")
        selected_company = st.selectbox("Sélectionne une entreprise pour ouvrir son dossier :", df["Entreprise"].unique())
        if selected_company:
            job_rows = df[df["Entreprise"] == selected_company]
            for _, row in job_rows.iterrows():
                with st.expander(f"[{row['Score IA']}%] {row['Poste']}"):
                    t_critique, t_lm, t_cv = st.tabs(["🤖 Critique IA", "📝 Lettre de Motivation", "🛠️ Optimisations CV"])
                    
                    with t_critique:
                        crit = row['Critique IA']
                        if crit and isinstance(crit, dict):
                            
                            # --- SCORE ---
                            score_val = crit.get('MATCH_SCORE', row.get('Score IA', 0))
                            st.progress(int(score_val) / 100, text=f"**Score IA : {score_val}/100**")
                            st.markdown("---")
                            
                            c_good, c_bad = st.columns(2)
                            
                            pros_cons = crit.get('PROS_CONS', {})
                            
                            # Handle both old string format and new dict format from LLM
                            if isinstance(pros_cons, dict):
                                pros_list = pros_cons.get('PROS', [])
                                cons_list = pros_cons.get('CONS', [])
                                pros_text = "\n".join([f"✅ {p}" for p in pros_list]) if pros_list else "Aucun point fort identifié."
                                cons_text = "\n".join([f"❌ {c}" for c in cons_list]) if cons_list else "Aucun point faible identifié."
                            elif isinstance(pros_cons, str) and pros_cons:
                                if "Inconvénient" in pros_cons:
                                    parts = pros_cons.split("Inconvénient")
                                    pros_text = parts[0].replace("Avantage", "").replace("s :", "").strip()
                                    cons_text = parts[1].replace("s :", "").strip()
                                else:
                                    pros_text = pros_cons
                                    cons_text = "Non disponible."
                            else:
                                pros_text = "Non disponible."
                                cons_text = "Non disponible."
                            
                            with c_good:
                                st.markdown("**🟢 Points Forts**")
                                st.success(pros_text)
                            
                            with c_bad:
                                st.markdown("**🔴 Points Faibles**")
                                st.error(cons_text)
                            
                            st.markdown("---")
                            
                            # --- MISSING KEYWORDS ---
                            missing = crit.get('MISSING_KEYWORDS', None)
                            if missing:
                                st.markdown("**🔑 Mots-clés Manquants (à ajouter à ton CV)**")
                                if isinstance(missing, list):
                                    keywords_md = "  ".join([f"`{k}`" for k in missing])
                                elif isinstance(missing, str) and missing.lower() not in ["aucun", "none", "n/a", ""]:
                                    keywords_md = "  ".join([f"`{k.strip()}`" for k in missing.replace(",", "\n").split("\n") if k.strip()])
                                else:
                                    keywords_md = "✅ Aucun mot-clé manquant détecté !"
                                st.warning(keywords_md)
                            
                            # --- IMPROVEMENT PLAN ---
                            plan = crit.get('IMPROVEMENT_PLAN', None)
                            if plan:
                                with st.expander("📋 Plan d'amélioration du CV"):
                                    if isinstance(plan, list):
                                        for item in plan:
                                            st.markdown(f"- {item}")
                                    else:
                                        st.markdown(str(plan))
                        else:
                            st.info("Aucune critique IA disponible pour cette offre (ancienne entrée Notion).")
                    
                    # Logic to find local files (same as generator.py safe_company)
                    safe_company = "".join([c for c in str(row['Entreprise']) if c.isalnum() or c in (' ', '_')]).strip()
                    output_dir = os.path.join("data", "output", safe_company)
                    
                    with t_lm:
                        lm_path = os.path.join(output_dir, "Cover_Letter.txt")
                        if os.path.exists(lm_path):
                            with open(lm_path, "r", encoding="utf-8") as f:
                                st.code(f.read(), language="markdown")
                        else:
                            st.warning("Aucune Lettre de Motivation générée en local (Score IA < 80% ou suppression).")
                            
                    with t_cv:
                        cv_path = os.path.join(output_dir, "CV_Optimization.txt")
                        if os.path.exists(cv_path):
                            with open(cv_path, "r", encoding="utf-8") as f:
                                st.code(f.read(), language="markdown")
                        else:
                            st.warning("Aucune Optimisation CV générée en local.")
    else:
        st.info("Pipeline is empty.")

elif page == "✉️ Auto-Mailing":
    st.markdown("### ⏰ Relances Intelligentes (Follow-ups)")
    st.markdown("Cette interface vérifie ton compte GMAIL pour synchroniser tes candidatures.")
    
    if st.button("✉️ Lancer Script Gmail Sync"):
        try:
            subprocess.Popen([sys.executable, "main.py", "mail"], cwd=os.getcwd())
            st.toast("Email Sync Started!", icon="✅")
        except Exception as e:
            st.error(str(e))

    # Real-time log display for Mailing Sync
    if os.path.exists(LIVE_STATE_FILE):
        try:
            with open(LIVE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            logs = state.get("logs", [])
            status = state.get("status", "")
            
            if logs:
                st.markdown("---")
                st.markdown("##### ⚙️ Logs de Synchronisation")
                st.code("\n".join(logs), language="bash")
                
                if status == "Syncing Emails...":
                    with st.status("Vérification de Gmail en cours...", expanded=False):
                        st.write("Le bot analyse tes derniers messages...")
                    import time
                    time.sleep(2)
                    st.rerun()
                elif status == "Prêt":
                    st.success("Synchronisation terminée.")
        except:
            pass

elif page == "📊 Market Insights":
    st.markdown("### 📊 Market Insights")
    st.markdown("Découvre quelles villes et secteurs dominent ton marché.")
    if not df.empty:
        c1, c2 = st.columns(2)
        with c1:
            loc_counts = df["Localisation"].value_counts().head(10)
            fig_loc = px.bar(x=loc_counts.index, y=loc_counts.values, template="plotly_dark", title="Top 10 Villes Actives", labels={"x": "Lieu", "y": "Nb Offres"})
            st.plotly_chart(fig_loc, width="stretch")
        with c2:
            # Replaced "Source" logic with "Entreprise" distribution or "Statut" since Source is deprecated
            status_counts = df["Statut"].value_counts()
            fig_src = px.pie(values=status_counts.values, names=status_counts.index, template="plotly_dark", title="Distribution globale des Statuts")
            st.plotly_chart(fig_src, width="stretch")
    else:
        st.info("Pas assez de données pour les graphiques.")

elif page == "🧠 AI Lab":
    st.markdown("### 🧠 Laboratoire d'I.A.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### ⚙️ Configuration Actuelle du Cerveau")
        st.json({
            "Core Model": config.get("llm", {}).get("model", "Unknown"),
            "Temperature": config.get("llm", {}).get("temperature", 0.7),
            "Job Title": config.get("search", {}).get("keywords", [])[0] if config.get("search", {}).get("keywords") else "None",
            "Radius (km)": config.get("search", {}).get("distance", 30)
        })
    with c2:
        st.markdown("##### 🚫 Anti-Patterns (Règles d'Exclusion Pédagogiques)")
        if os.path.exists(ANTI_PATTERNS_PATH):
            with open(ANTI_PATTERNS_PATH, "r", encoding="utf-8") as f:
                patterns = f.read()
            st.code(patterns, language="markdown")
        else:
            st.info("Pas d'Anti-Patterns encore enregistrés.")
        
        if st.button("🧠 Forcer l'Apprentissage IA depuis Notion"):
            try:
                subprocess.Popen([sys.executable, "main.py", "learn"], cwd=os.getcwd())
                st.toast("Neural Network Learning launched...", icon="✅")
            except Exception as e:
                st.error(str(e))

    # Real-time log display for AI Learning
    if os.path.exists(LIVE_STATE_FILE):
        try:
            with open(LIVE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            logs = state.get("logs", [])
            status = state.get("status", "")
            
            if logs and status in ["Learning...", "Terminé"]:
                st.markdown("---")
                st.markdown("##### 🔬 Analyse du Feedback Notion")
                st.code("\n".join(logs), language="bash")
                
                if status == "Learning...":
                    with st.status("L'IA apprend de tes rejets...", expanded=False):
                        st.write("Analyse des motifs d'échec...")
                    import time
                    time.sleep(2)
                    st.rerun()
                else:
                    st.success("Apprentissage terminé.")
        except:
            pass
