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
from modules.config_loader import load_config
from modules.auth import AuthManager
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="L'Éclaireur", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for Premium Glassmorphism & Cyberpunk Aesthetics
st.markdown("""
<style>
    /* Global Background and Fonts */
    .stApp {
        background: #0B1121;
        font-family: 'Inter', sans-serif;
    }
    
    /* Metrics Styling */
    div[data-testid="stMetric"] {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 24px;
        border-radius: 16px;
        backdrop-filter: blur(12px);
        transition: all 0.3s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-4px);
        border-color: rgba(59, 130, 246, 0.5);
        box-shadow: 0 10px 30px rgba(59, 130, 246, 0.1);
    }
    div[data-testid="stMetricValue"] {
        color: #60A5FA !important;
        font-size: 2.5rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #94A3B8 !important;
        font-size: 1rem !important;
        font-weight: 500 !important;
    }
    
    /* Headers */
    .stApp h1 {
        color: #F8FAFC !important;
        font-weight: 800 !important;
        letter-spacing: -1px !important;
    }
    .stApp h3 {
        color: #F8FAFC !important;
        font-weight: 600 !important;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        padding-bottom: 8px;
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        height: 3rem;
        transition: all 0.2s ease;
        border: 1px solid rgba(255,255,255,0.1) !important;
    }
    .stButton>button[kind="primary"] {
        background: #2563EB;
        color: white !important;
        border: none !important;
    }
    .stButton>button[kind="primary"]:hover {
        background: #1D4ED8;
        transform: translateY(-1px);
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    
    /* DataFrame */
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.05);
    }

    /* Auth Styling - Full Screen Center */
    .stApp > header {
        display: none !important;
    }
    
    [data-testid="stHeader"] {
        background: transparent !important;
    }
    
    .auth-wrapper {
        display: flex;
        justify-content: center;
        margin-top: 15vh;
        width: 100%;
    }
    
    .auth-container {
        width: 100%;
        max-width: 480px;
        padding: 40px;
        background: #1E293B !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 24px !important;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4) !important;
    }

    .auth-header h1 {
        font-size: 2.5rem !important;
        line-height: 1.2 !important;
        margin-bottom: 0.5rem !important;
        text-align: center;
        background: linear-gradient(90deg, #60A5FA 0%, #3B82F6 100%);
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
    }
    
    .auth-header p {
        text-align: center;
    }
    
    /* Hide Radio Button Circles in Sidebar */
    .stRadio > div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }
    .stRadio > div[role="radiogroup"] > label {
        padding: 10px 15px;
        background: rgba(255,255,255,0.02);
        border-radius: 8px;
        margin-bottom: 5px;
        transition: all 0.2s ease;
        border: 1px solid transparent;
        cursor: pointer;
    }
    .stRadio > div[role="radiogroup"] > label:hover {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
    }
    .stRadio > div[role="radiogroup"] > label[data-checked="true"] {
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid #3B82F6;
    }
    
    .glow-text {
        color: #60A5FA !important;
    }
</style>
""", unsafe_allow_html=True)

# st.title removed from here to avoid showing on login page

# --- DATA LOADING ---
# Use absolute paths so dashboard and main.py always share the same file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
ANTI_PATTERNS_PATH = os.path.join(BASE_DIR, "data", "anti_patterns.txt")
STATUS_FILE = os.path.join(BASE_DIR, "data", "scraper_status.json")
LIVE_STATE_FILE = os.path.join(BASE_DIR, "data", "live_state.json")

# Remove caching so data represents the live PostgreSQL DB state.
def load_data(user_id=None):
    config = load_config(CONFIG_PATH)
            
    try:
        db = DBManager(init_db=True)
        if db.connected:
            jobs = db.get_all_jobs(user_id=user_id)
            if db.use_sqlite:
                st.sidebar.info("🏠 **Base Locale Active** (SQLite)")
                st.sidebar.caption("Le réseau de l'école bloque Supabase (Port 5432/6543). Vos données sont stockées en local sur ce PC.")
            else:
                st.sidebar.success("☁️ **Base Cloud Active** (Supabase)")
        else:
            st.sidebar.error("❌ Erreur de base de données")
            jobs = []
    except Exception as e:
        jobs = []
        st.sidebar.warning(f"⚠️ Erreur de chargement : {e}")
        # Legacy Fallback to JSON if DB fails
        legacy_path = config.get("paths", {}).get("tracking_db", "data/jobs_db.json")
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    jobs = json.load(f)
                st.sidebar.info("💡 Données chargées depuis le backup local (JSON).")
            except:
                pass
        
    return config, jobs

# --- AUTHENTICATION LOGIC ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user' not in st.session_state:
    st.session_state.user = None

auth = AuthManager(db_manager=DBManager(init_db=True))

def show_login():
    # Centering container using streamlit columns as a wrapper
    _, col, _ = st.columns([1, 2, 1])
    
    with col:
        st.markdown('<div class="auth-wrapper">', unsafe_allow_html=True)
        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        with st.container():
            st.markdown('<div class="auth-header">', unsafe_allow_html=True)
            st.markdown('<h1>L\'Éclaireur</h1>', unsafe_allow_html=True)
            st.markdown('<p style="color: #94A3B8; margin-bottom: 2rem;">Plateforme de Recherche Intelligente</p>', unsafe_allow_html=True)
            
            tab_login, tab_reg = st.tabs(["Connexion", "Inscription"])
            
            with tab_login:
                with st.form("login_form", clear_on_submit=False):
                    u = st.text_input("Identifiant", placeholder="Nom d'utilisateur...")
                    p = st.text_input("Mot de passe", type="password", placeholder="••••••••")
                    if st.form_submit_button("Se Connecter", type="primary", use_container_width=True):
                        user = auth.login_user(u, p)
                        if user:
                            st.session_state.authenticated = True
                            st.session_state.user = user
                            st.toast(f"Bienvenue, {u} !", icon="👋")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Identifiants incorrects.")
                            
            with tab_reg:
                with st.form("reg_form"):
                    ru = st.text_input("Nom d'utilisateur", placeholder="Choisissez un identifiant")
                    re = st.text_input("Email", placeholder="Adresse email")
                    rp = st.text_input("Mot de passe", type="password", placeholder="Mot de passe sécurisé")
                    rf = st.text_input("Nom complet", placeholder="Prénom Nom")
                    if st.form_submit_button("Créer un compte", type="primary", use_container_width=True):
                        if auth.register_user(ru, rp, re, full_name=rf):
                            st.success("Compte créé avec succès ! Connectez-vous.")
                        else:
                            st.error("Cet identifiant est déjà pris.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state.authenticated:
    show_login()
    st.stop()

# Load User Data
user_data = st.session_state.user
config, jobs = load_data(user_id=user_data['id'])

st.title("🧭 L'Éclaireur - Tableau de Bord")

# --- SIDEBAR CONTROL ROOM ---
with st.sidebar:
    avatar_url = config.get("discord", {}).get("avatar_url", "")
    if avatar_url:
        st.image(avatar_url, width=100)
    st.markdown(f"**Agent:** {config.get('user_profile', {}).get('name', 'Opérateur')}")
    st.markdown("---")
    
    # NAVIGATION SYSTEM
    st.subheader("COMPASS")
    page = st.radio("Navigation", [
        "🏠 Vue d'ensemble",
        "🎯 Chasse en Direct",
        "🗃️ Base de données",
        "✉️ Suivi Emails",
        "⚙️ Réglages",
        "👤 Mon Profil"
    ], label_visibility="collapsed")
    
    st.markdown("---")
    if st.button("🔌 DÉCONNEXION", type="secondary", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()
    
    st.markdown("---")
    st.subheader("⚡ MOTEUR DE RECHERCHE")
    
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
            st.button("🟢 EN COURS", disabled=False, key="running_btn", width='stretch')
        else:
            if st.button("▶️ DÉMARRER", type="primary", width='stretch'):
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
                        st.toast("Recherche lancée !", icon="🚀")
                    except Exception as e:
                        st.error(f"Erreur: {e}")
                st.rerun()

    with col_b:
        if current_status == "stopped":
            st.button("🔴 ARRÊTÉ", disabled=False, key="stopped_btn", width='stretch')
        else:
            if st.button("⏹️ ARRÊTER", type="primary", width='stretch'):
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
        loc = j.get("lieu")
        loc_str = str(loc).split(",")[0] if loc else "Inconnu"

        df_data.append({
            "Titre": str(j.get("titre", "Sans Titre")),
            "Entreprise": str(j.get("entreprise", "Inconnue")),
            "Statut": str(j.get("statut", "NULL")),
            "Lieu": str(loc_str),
            "Score IA": j.get("score_ia", 0),
            "Lien": str(j.get("lien", "")),
            "Date": j.get("date", "1970-01-01"),
            "critique_ia": j.get("critique_ia")
        })
    df = pd.DataFrame(df_data)
    # Ensure Score IA is numeric for progress bar
    df["Score IA"] = pd.to_numeric(df["Score IA"], errors='coerce').fillna(0).astype(int)
    df["Date"] = pd.to_datetime(df["Date"], errors='coerce')

# --- ROUTER SYSTEM ---
if page == "🏠 Vue d'ensemble":
    st.markdown("### 📈 Entonnoir d'Acquisition")
    if not df.empty:
        total_analyzed = len(df)
        
        # Validated by AI (Score >= 80) or explicitly active
        validated_ai = len(df[(df["Score IA"] >= 80) | (df["Statut"].isin(["À postuler", "Postulé", "En cours", "Offre", "Refusé"]))])
        
        # Applications actually sent out
        applications_sent = len(df[df["Statut"].isin(["Postulé", "En cours", "Offre", "Refusé"])])
        
        # Interviews secured
        interviews = len(df[df["Statut"].isin(["En cours", "Offre"])])
        
        conversion_rate = (interviews / applications_sent * 100) if applications_sent > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Offres Analysées", total_analyzed)
        c2.metric("Validées par l'IA", validated_ai)
        c3.metric("Candidatures Envoyées", applications_sent)
        c4.metric("Entretiens", interviews, f"{conversion_rate:.1f}% Conv." if applications_sent else "0%")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Draw Funnel (Modern colors) -> Replaced with Horizontal Bar as requested
        fig_funnel = go.Figure(go.Bar(
            y=["Entretiens", "Candidatures", "Pertinentes (>80%)", "Offres Analysées"],
            x=[interviews, applications_sent, validated_ai, total_analyzed],
            orientation='h',
            text=[interviews, applications_sent, validated_ai, total_analyzed],
            textposition='auto',
            marker=dict(color=["#10B981", "#60A5FA", "#3B82F6", "#1E293B"])
        ))
        fig_funnel.update_layout(
            template="plotly_dark", 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            title="Pipeline de Candidatures",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False)
        )
        
        # Draw Donut Chart instead of pure pie
        active_status_df = df[df["Statut"] != "NULL"]
        status_counts = active_status_df["Statut"].value_counts()
        fig_pie = px.pie(
            values=status_counts.values, 
            names=status_counts.index, 
            color_discrete_sequence=px.colors.qualitative.Prism, 
            template="plotly_dark", 
            hole=0.6, 
            title="Répartition des Statuts"
        )
        fig_pie.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)'
        )
        
        r1, r2 = st.columns(2)
        r1.plotly_chart(fig_funnel, use_container_width=True)
        r2.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Aucune donnée dans la base pour le moment.")

elif page == "🎯 Chasse en Direct":
    st.markdown("### 🎯 Chasse en Direct")
    st.markdown("Suivez la réflexion de l'I.A. en temps réel.")
    
    if current_status == "running":
        import time
        try:
            with open("data/live_state.json", "r", encoding="utf-8") as f:
                state = json.load(f)
                
            st.info(f"**Statut Actuel:** {state.get('status', 'N/A')}")
            
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("#### 🔄 Statut de l'Agent")
                logs = state.get('logs', [])
                if logs:
                    # Clean display, no markdown code blocks
                    latest_log = logs[-1] if len(logs) > 0 else "Analyse en attente..."
                    st.info(f"**Action en cours :** {latest_log}")
                else:
                    st.info("Recherche imminente...")
                
            with c2:
                st.markdown("#### 🔍 Dernières découvertes")
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
    
elif page == "🗃️ Base de données":
    db_c1, db_c2 = st.columns([5, 1])
    with db_c1:
        st.markdown("### 🗃️ Base de Données Globale")
        st.markdown("L'historique complet et détaillé de chaque opportunité scannée.")
    with db_c2:
        if st.button("🔄 Rafraîchir"):
            st.rerun()
        
        # Excel Export Button
        if not df.empty:
            import io
            output = io.BytesIO()
            export_df = df.copy()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                export_df.to_excel(writer, index=False, sheet_name='Historique Jobs')
            
            st.download_button(
                label="📥 Télécharger Excel",
                data=output.getvalue(),
                file_name=f"stage_hunter_export_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch'
            )

    if not df.empty:
        # Mirror Notion design: Titre, Entreprise, Statut, Lieu, Score IA, Lien, Date
        display_df = df[["Titre", "Entreprise", "Statut", "Lieu", "Score IA", "Lien", "Date"]]
        
        def color_status_col(s):
            colors = []
            for val in s:
                if val == "À postuler":
                    colors.append("background-color: rgba(255, 215, 0, 0.15); color: #FFD700; font-weight: bold;") 
                elif val == "En cours":
                    colors.append("background-color: rgba(0, 255, 0, 0.15); color: #00FF00; font-weight: bold;")
                elif val == "Postulé":
                    colors.append("background-color: rgba(0, 191, 255, 0.15); color: #00BFFF; font-weight: bold;")
                elif val == "Entretien":
                    colors.append("background-color: rgba(218, 112, 214, 0.15); color: #DA70D6; font-weight: bold;")
                elif val in ["Refusé", "Rejected"]:
                    colors.append("background-color: rgba(255, 0, 0, 0.15); color: #FF4500; font-weight: bold;")
                else:
                    colors.append("")
            return colors
            
        styled_df = display_df.style.apply(color_status_col, subset=["Statut"])
        
        st.dataframe(
                styled_df,
                column_config={
                    "Lien": st.column_config.LinkColumn("📍 Lien", display_text="Ouvrir"),
                    "Score IA": st.column_config.ProgressColumn("⭐ Score IA", format="%d", min_value=0, max_value=100),
                    "Date": st.column_config.DatetimeColumn("📅 Date", format="DD/MM/YYYY"),
                    "Statut": st.column_config.TextColumn("📊 Statut")
                },
                width='stretch',
                hide_index=True,
                height=600
            )
            
        st.markdown("---")
        st.markdown("### 🔍 Inspecteur IA")
        st.markdown("Explorateur détaillé des analyses IA et documents générés métier par métier.")
        
        # Group jobs by company for the inspector
        companies = df["Entreprise"].unique()
        for company in companies:
            company_jobs = df[df["Entreprise"] == company]
            
            with st.expander(f"🏢 {company} ({len(company_jobs)} offre(s))"):
                for _, row in company_jobs.iterrows():
                    st.markdown(f"#### {row['Titre']} ({row['Lieu']} - {row['Score IA']}%)")
                    st.caption(f"[Ouvrir l'offre originale]({row['Lien']})")
                    
                    t_missions, t_company, t_pros_cons, t_lm, t_cv = st.tabs([
                        "📝 Missions", "🏢 À Propos", "⚖️ Avantages & Inconvénients", "✉️ Lettre de Motiv", "🛠️ Opti. CV"
                    ])
                    
                    # Parse JSON critique
                    crit = row.get("critique_ia")
                    if isinstance(crit, str):
                        try:
                            import json
                            crit = json.loads(crit)
                        except:
                            pass
                            
                    if not isinstance(crit, dict):
                        crit = {}
                        
                    with t_missions:
                        missions = crit.get("short_description") or crit.get("SHORT_DESCRIPTION") or "Aucune mission détaillée."
                        if isinstance(missions, list):
                            for m in missions:
                                st.markdown(f"- {m}")
                        else:
                            st.markdown(missions)
                            
                        missing = crit.get("missing_keywords") or crit.get("MISSING_KEYWORDS")
                        if missing and missing != "N/A" and str(missing).lower() != "aucun":
                            st.warning(f"**Mots-clés manquants au profil:** {missing}")
                            
                    with t_company:
                         st.markdown(crit.get("company_info") or crit.get("COMPANY_INFO") or "Aucune information supplémentaire.")
                         
                    with t_pros_cons:
                        pc_data = crit.get("pros_cons") or crit.get("PROS_CONS", {})
                        if isinstance(pc_data, dict):
                            c1, c2 = st.columns(2)
                            # Normalize internal keys just in case
                            pc_data = {k.lower(): v for k, v in pc_data.items()} if isinstance(pc_data, dict) else pc_data
                            
                            with c1:
                                st.success("✅ **Points Forts**")
                                for p in pc_data.get("pros", []):
                                    st.markdown(f"- {p}")
                            with c2:
                                st.error("❌ **Points Faibles**")
                                for c in pc_data.get("cons", []):
                                    st.markdown(f"- {c}")
                        else:
                            st.info(str(pc_data))
                        
                    # --- REJECTION BUTTON ---
                    if row['Statut'] != 'Refusé':
                        if st.button("🗑️ Refuser cette offre", key=f"rej_{row['Lien']}", use_container_width=True):
                            db_rej = DBManager()
                            if db_rej.update_job_status(row['Lien'], 'Refusé'):
                                st.toast("Offre refusée. Le moteur va apprendre de ce choix.", icon="🗑️")
                                time.sleep(0.5)
                                st.rerun()
                    else:
                        st.info("Cette offre a été refusée.")
                            
                    with t_lm:
                         lm_text = crit.get("cover_letter") or crit.get("COVER_LETTER", "Aucune lettre générée dans cette version.")
                         st.markdown("##### ✉️ Lettre de Motivation Générée")
                         st.write(lm_text)
                         if st.button("📋 Copier la lettre", key=f"btn_lm_{row['Lien']}"):
                             st.toast("Copié !", icon="✅")

                    with t_cv:
                         opti = crit.get("cv_optimization") or crit.get("CV_OPTIMIZATION") or crit.get("improvement_plan") or crit.get("IMPROVEMENT_PLAN") or "Aucun conseil d'optimisation disponible."
                         st.info(opti)
                            
                    st.divider()
    else:
        st.info("Aucune donnée dans la base pour le moment.")

elif page == "✉️ Suivi Emails":
    st.markdown("### ⏰ Relances Intelligentes (Follow-ups)")
    st.markdown("Cette interface vérifie ta boîte mail pour synchroniser l'avancement de tes candidatures.")
    
    if st.button("✉️ Lancer la Synchronisation Email"):
        try:
            subprocess.Popen([sys.executable, "main.py", "mail"], cwd=os.getcwd())
            st.toast("Synchronisation démarrée !", icon="✅")
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
                st.markdown("##### 🔄 État de la Synchronisation")
                
                latest_log = logs[-1] if len(logs) > 0 else "Analyse en attente..."
                st.info(f"**Vérification :** {latest_log}")
                
                with st.expander("Voir les détails techniques (Logs)"):
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

elif page == "⚙️ Réglages":
    st.markdown("### ⚙️ Centre de Configuration")
    st.markdown("Personnalise le comportement du bot, de la recherche et de la blacklist sans toucher au code.")
    
    # Reload config specifically for this page to have latest state
    current_config = {}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                current_config = yaml.safe_load(f) or {}
    except Exception as e:
        st.error(f"Erreur lors de la lecture de config.yaml : {e}")
        
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("#### 🎯 Ciblage de Recherche")
        
        st.write("**Mots-clés (Postes ciblés):**")
        kws = current_config.get("search", {}).get("keywords", [])
        df_kws = pd.DataFrame({"Mot-clé": kws})
        edited_kws = st.data_editor(df_kws, num_rows="dynamic", width='stretch', key="kws_editor")
        
        st.write("**Villes / Lieux:**")
        locs = current_config.get("search", {}).get("locations", [])
        df_locs = pd.DataFrame({"Lieu": locs})
        edited_locs = st.data_editor(df_locs, num_rows="dynamic", width='stretch', key="locs_editor")
        
    with c2:
        st.markdown("#### 🚫 Filtres & Apprentissage")
        st.write("**Entreprises à ignorer (Blacklist):**")
        bl_comp = current_config.get("blacklist", {}).get("companies", [])
        df_bl = pd.DataFrame({"Entreprise": bl_comp})
        edited_bl = st.data_editor(df_bl, num_rows="dynamic", width='stretch', key="bl_editor")
        
        st.divider()
        st.markdown("#### 🧠 Anti-Patterns (IA)")
        st.markdown("Scanne les entreprises marquées en `NULL` (Refus) dans Notion pour injecter de nouvelles règles d'exclusion dans le cerveau de l'I.A.")
        
        # Load current content of the file
        current_patterns = ""
        if os.path.exists(ANTI_PATTERNS_PATH):
            try:
                with open(ANTI_PATTERNS_PATH, "r", encoding="utf-8") as f:
                    current_patterns = f.read()
            except: pass
            
        # Display editable text area
        new_patterns = st.text_area("Règles d'exclusion apprises :", value=current_patterns, height=300, help="Ces règles sont utilisées par l'IA pour filtrer les offres. Tu peux les modifier manuellement.")
        
        col_la, col_lb = st.columns(2)
        with col_la:
            if st.button("🧠 Lancer l'Apprentissage", width='stretch'):
                try:
                    subprocess.Popen([sys.executable, "main.py", "learn"], cwd=os.getcwd())
                    st.toast("Apprentissage lancé...", icon="🧪")
                except Exception as e:
                    st.error(str(e))
        with col_lb:
            if st.button("💾 Sauvegarder Patterns", width='stretch'):
                try:
                    with open(ANTI_PATTERNS_PATH, "w", encoding="utf-8") as f:
                        f.write(new_patterns)
                    st.success("Patterns sauvegardés !")
                except Exception as e:
                    st.error(str(e))
                    
        # Simple status indicator for learning (removed auto-rerun logs to allow editing)
        if os.path.exists(LIVE_STATE_FILE):
            try:
                with open(LIVE_STATE_FILE, "r", encoding="utf-8") as f:
                    state_json = json.load(f)
                if state_json.get("status") == "Learning...":
                    st.info("L'IA est en train d'analyser Notion... Rafraîchis la page dans un instant pour voir les nouveaux patterns.")
            except: pass
                
    st.markdown("---")
    
    # Save Button
    if st.button("💾 Sauvegarder la Configuration", type="primary", width='stretch'):
        # Clean edited data
        new_kws = edited_kws["Mot-clé"].dropna().astype(str).str.strip().tolist()
        new_kws = [k for k in new_kws if k]
        
        new_locs = edited_locs["Lieu"].dropna().astype(str).str.strip().tolist()
        new_locs = [k for k in new_locs if k]
        
        new_bl = edited_bl["Entreprise"].dropna().astype(str).str.strip().tolist()
        new_bl = [k for k in new_bl if k]
        
        # Update current_config
        if "search" not in current_config:
            current_config["search"] = {}
        current_config["search"]["keywords"] = new_kws
        current_config["search"]["locations"] = new_locs
        
        if "blacklist" not in current_config:
            current_config["blacklist"] = {}
        current_config["blacklist"]["companies"] = new_bl
        
        # Dump back to yaml file
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(current_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            st.success("✅ Configuration sauvegardée avec succès !")
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde: {e}")

elif page == "👤 Mon Profil":
    st.markdown("### 👤 Identité & Profil Utilisateur")
    st.markdown("Configurez vos préférences personnelles, votre CV et vos critères de recherche.")
    
    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Nom Complet", value=user_data.get('full_name', ''))
            new_email = st.text_input("Email de contact", value=user_data.get('email', ''))
        with col2:
            new_phone = st.text_input("Téléphone", value=user_data.get('phone', ''))
            new_linkedin = st.text_input("URL LinkedIn", value=user_data.get('linkedin_url', ''))

        st.markdown("---")
        st.markdown("#### 🎯 Configuration de Recherche Personnelle")
        st.caption("Ces règles surchargent la configuration globale pour limiter la recherche à VOS besoins.")
        
        # Load existing search_config
        s_conf = user_data.get('search_config') or {}
        if isinstance(s_conf, str):
            try: s_conf = json.loads(s_conf)
            except: s_conf = {}
            
        current_kws = ", ".join(s_conf.get('keywords', []))
        current_locs = ", ".join(s_conf.get('locations', []))
        
        c_k1, c_k2 = st.columns(2)
        with c_k1:
            new_kws_str = st.text_input("Mes Mots-clés (séparés par des virgules)", value=current_kws)
        with c_k2:
            new_locs_str = st.text_input("Mes Lieux (séparés par des virgules)", value=current_locs)
            
        st.markdown("---")
        st.markdown("#### 📄 Master CV (Texte)")
        st.caption("Collez ici le contenu texte brut de votre CV. C'est la base pour toutes les analyses de l'I.A. et les lettres de motivation.")
        new_cv = st.text_area("Contenu du CV", value=user_data.get('cv_text', ''), height=400)
        
        if st.form_submit_button("💾 METTRE À JOUR LE PROFIL", type="primary", use_container_width=True):
            # Parse strings back to lists
            new_kws = [k.strip() for k in new_kws_str.split(",") if k.strip()]
            new_locs = [l.strip() for l in new_locs_str.split(",") if l.strip()]
            
            # Preserve existing config keys (like anti_patterns)
            new_s_conf = s_conf.copy() if isinstance(s_conf, dict) else {}
            new_s_conf["keywords"] = new_kws
            new_s_conf["locations"] = new_locs
            new_search_config = json.dumps(new_s_conf)

            conn = DBManager()._get_conn()
            cursor = conn.cursor()
            try:
                if DBManager().use_sqlite:
                    cursor.execute('''
                    UPDATE users 
                    SET full_name = ?, email = ?, phone = ?, linkedin_url = ?, cv_text = ?, search_config = ?
                    WHERE id = ?
                    ''', (new_name, new_email, new_phone, new_linkedin, new_cv, new_search_config, user_data['id']))
                else:
                    cursor.execute('''
                    UPDATE users 
                    SET full_name = %s, email = %s, phone = %s, linkedin_url = %s, cv_text = %s, search_config = %s
                    WHERE id = %s
                    ''', (new_name, new_email, new_phone, new_linkedin, new_cv, new_search_config, user_data['id']))
                conn.commit()
                st.session_state.user = auth.get_user_by_id(user_data['id'])
                st.success("✅ Profil et critères mis à jour !")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de la mise à jour : {e}")
            finally:
                cursor.close()
                conn.close()

    st.markdown("---")
    st.markdown("#### 🧠 Intelligence & Optimisation")
    st.caption("Le moteur apprend de vos refus pour affiner les prochaines offres. Cliquez ici pour forcer l'analyse de vos derniers choix.")
    
    if st.button("🚀 OPTIMISER MON PROFIL IA", use_container_width=True):
        from modules.job_search import JobSearch
        with st.spinner("Analyse des préférences en cours..."):
            js = JobSearch(user_id=user_data['id'])
            js.learn_from_rejections()
            st.success("Votre profil IA a été mis à jour via vos derniers refus !")
            time.sleep(1)
            st.rerun()
            
    if s_conf.get('anti_patterns'):
        with st.expander("👁️ Voir mes règles de filtrage actuelles"):
            st.info(s_conf['anti_patterns'])
