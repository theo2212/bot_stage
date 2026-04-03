import yaml
from modules.config_loader import load_config
import sys
import os
import traceback
from datetime import datetime

# Add current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Absolute path constants - shared with dashboard.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "data", "scraper_status.json")

from modules.analyzer import Analyzer
from modules.utils import extract_text_from_pdf

def init_config():
    # Placeholder for backward compatibility if needed, but we use load_config directly
    return load_config("config.yaml")

def run_cron_search(fresh=False):
    """Headless single-pass execution for GitHub Actions / Cron jobs"""
    print("--- 🤖 RUNNING IN HEADLESS CRON MODE ---")
    from modules.job_search import JobSearch
    from modules.auth import AuthManager
    
    auth = AuthManager()
    user_ids = auth.get_all_user_ids()
    
    if not user_ids:
        print("[CRON] No users found in database. Searching with default generic config (No User).")
        searcher = JobSearch()
        searcher.run()
    else:
        print(f"[CRON] Proceeding for {len(user_ids)} registered users.")
        for uid in user_ids:
            try:
                user_data = auth.get_user_by_id(uid)
                print(f"\n[CRON] Starting extraction for User: {user_data.get('username', uid)}")
                searcher = JobSearch(user_id=uid)
                searcher.run()
                print(f"[CRON] Completed for {user_data.get('username', uid)}")
            except Exception as e:
                print(f"[CRON] Error for user {uid}: {e}")
                
    print("\n--- ✅ HEADLESS CRON SEARCH COMPLETE ---")

def run_search(fresh=False):
    import time
    from rich.live import Live
    from modules.job_search import JobSearch
    from modules.auth import AuthManager
    from modules.db_manager import DBManager
    from modules.dashboard import Dashboard

    if fresh:
        try:
            from modules.db_manager import DBManager
            db = DBManager()
            conn = db._get_conn()
            cursor = conn.cursor()
            cursor.execute("TRUNCATE TABLE jobs")
            conn.commit()
            cursor.close()
            conn.close()
            print("Successfully cleared PostgreSQL 'jobs' table for a fresh start.")
        except Exception as e:
            print(f"Warning: Could not clear PostgreSQL table: {e}")

    is_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    
    db = DBManager()
    auth = AuthManager(db_manager=db)
    
    # In Multi-User mode, we run for ALL users in the DB
    conn = db._get_conn()
    cursor = conn.cursor()
    if db.use_sqlite:
        cursor.execute("SELECT id FROM users")
    else:
        cursor.execute("SELECT id FROM users")
    user_ids = [r[0] for r in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not user_ids:
        print("No users found in database. Please register via dashboard first.")
        return

    dashboard = Dashboard()
    
    for uid in user_ids:
        user_data = auth.get_user_by_id(uid)
        print(f"--- Running search for user: {user_data['username']} ---")
        
        searcher = JobSearch(dashboard=dashboard, user_id=uid)

        if is_ci:
            dashboard.log(f"CI Mode Active for {user_data['username']}.")
            # ... existing CI alert logic ...
            new_jobs = searcher.run()
            print(f"Found {len(new_jobs)} new jobs for {user_data['username']}!")
            continue

    with Live(dashboard.generate_layout(), refresh_per_second=4, screen=True) as live:
        dashboard.live_context = live
        dashboard.log("System initialized.")
        dashboard.set_status("Idle")
        
        try:
            searcher.notifier.send_startup_alert()
        except Exception as e:
            print(f"Startup alert failed: {e}")
        
        import json
        import threading
        
        def heartbeat_loop():
            while True:
                try:
                    os.makedirs("data", exist_ok=True)
                    current_data = {}
                    if os.path.exists(STATUS_FILE):
                        with open(STATUS_FILE, "r", encoding="utf-8") as f:
                            current_data = json.load(f)
                    current_data["heartbeat"] = time.time()
                    current_data["pid"] = os.getpid()
                    with open(STATUS_FILE, "w", encoding="utf-8") as f:
                        json.dump(current_data, f)
                except:
                    pass
                time.sleep(5)
                
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        
        def get_scraper_status():
            try:
                if os.path.exists(STATUS_FILE):
                    with open(STATUS_FILE, "r", encoding="utf-8") as f:
                        return json.load(f).get("status", "stopped")
            except:
                pass
            return "stopped"

        def force_status_running():
            try:
                os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
                current_data = {}
                if os.path.exists(STATUS_FILE):
                    with open(STATUS_FILE, "r", encoding="utf-8") as f:
                        current_data = json.load(f)
                current_data["status"] = "running"
                with open(STATUS_FILE, "w", encoding="utf-8") as f:
                    json.dump(current_data, f)
            except:
                pass
                
        # Automatically begin running when launched from CLI!
        force_status_running()

        while True:
            try:
                current_status = get_scraper_status()
                
                if current_status == "running":
                    live.update(dashboard.generate_layout())
                    
                    # Refresh user list each cycle to pick up new registrations
                    user_ids = auth.get_all_user_ids()
                    
                    for uid in user_ids:
                        try:
                            user_data = auth.get_user_by_id(uid)
                            if not user_data: continue
                            
                            searcher = JobSearch(dashboard=dashboard, user_id=uid)
                            
                            dashboard.set_status(f"[{user_data['username']}] Recherche en cours...")
                            dashboard.log(f"Starting cycle for {user_data['username']}...")
                            
                            new_jobs = searcher.run()
                            
                            if new_jobs:
                                dashboard.log(f"[{user_data['username']}] Found {len(new_jobs)} matches!")
                            else:
                                dashboard.log(f"[{user_data['username']}] No results found.")
                        except Exception as user_err:
                            dashboard.log(f"❌ Error for user {uid}: {user_err}")
                            continue
                    
                    dashboard.set_status("Sleeping (10min)")
                    
                    # Sleep loop with update and status check
                    for i in range(600): # 10 minutes
                        if get_scraper_status() == "stopped":
                            dashboard.log("Scraping stopped by user.")
                            dashboard.set_status("Idle")
                            break
                        live.update(dashboard.generate_layout())
                        time.sleep(1)
                else:
                    # Stopped mode
                    dashboard.set_status("Idle")
                    live.update(dashboard.generate_layout())
                    time.sleep(5) # Check status every 5 seconds
                    
            except KeyboardInterrupt as ki:
                dashboard.log("KeyboardInterrupt caught!")
                with open("error.log", "a", encoding="utf-8") as f:
                    f.write(f"\n--- {datetime.now()} ---\nKeyboardInterrupt!")
                    traceback.print_exc(file=f)
                break
            except BaseException as be:
                error_msg = traceback.format_exc()
                dashboard.log(f"BaseException: {be}")
                with open("error.log", "a", encoding="utf-8") as f:
                    f.write(f"\n--- {datetime.now()} ---\n{error_msg}")
                time.sleep(5)
                break

def run_cron_search(fresh=False):
    """Headless single-pass execution for GitHub Actions / Cron jobs"""
    print("--- 🤖 RUNNING IN HEADLESS CRON MODE ---")
    from modules.job_search import JobSearch
    from modules.auth import AuthManager
    
    auth = AuthManager()
    uid = auth.get_next_user_for_rotation()
    
    if not uid:
        print("[CRON] No users found in database to process.")
        return
    
    try:
        user_data = auth.get_user_by_id(uid)
        username = user_data.get('username', f'ID:{uid}')
        
        print(f"\n[CRON] 🔄 ROTATION: Starting search for User: {username}")
        searcher = JobSearch(user_id=uid)
        searcher.run()
        
        # Mark as searched only IF it didn't crash
        auth.mark_user_as_searched(uid)
        print(f"[CRON] ✅ Successfully completed and rotated for {username}")
        
    except Exception as e:
        print(f"[CRON] ❌ Error during rotation for user {uid}: {e}")
        import traceback
        traceback.print_exc()
                
    print("\n--- ✅ HEADLESS CRON SEARCH COMPLETE ---")

def main():
    print("--- Stage Hunter 3000 ---")

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        fresh = "--fresh" in sys.argv
        cron = "--cron" in sys.argv
        
        if cmd == "search":
            print("Launching Scraper...")
            try:
                if cron:
                    run_cron_search(fresh=fresh)
                else:
                    run_search(fresh=fresh)
            except Exception as e:
                traceback.print_exc()
                print(f"CRITICAL ERROR IN SEARCH: {e}")
                
        elif cmd == "regenerate":
            print("--- Mode: Regenerate from DB ---")
            try:
                from modules.job_search import JobSearch
                from modules.dashboard import Dashboard
                db_dash = Dashboard()
                db_dash.set_status("Regenerating...")
                searcher = JobSearch(dashboard=db_dash)
                searcher.regenerate_from_db()
                db_dash.set_status("Terminé")
                print("Regeneration complete.")
            except Exception as e:
                traceback.print_exc()
                print(f"CRITICAL ERROR IN REGENERATE: {e}")

        elif cmd == "learn":
            print("--- AI Feedback Loop: Learning from Notion 'NULL' Jobs ---")
            try:
                from modules.job_search import JobSearch
                from modules.dashboard import Dashboard
                learn_dash = Dashboard()
                learn_dash.set_status("Learning...")
                searcher = JobSearch(dashboard=learn_dash)
                searcher.learn_from_rejections()
                learn_dash.set_status("Terminé")
                print("Learning complete.")
            except Exception as e:
                traceback.print_exc()
                print(f"CRITICAL ERROR IN LEARN: {e}")

        elif cmd == "mail":
            print("--- Two-Way Sync: Checking Gmail for Responses ---")
            try:
                from modules.job_search import JobSearch
                from modules.dashboard import Dashboard
                mail_dash = Dashboard()
                mail_dash.set_status("Syncing Emails...")
                searcher = JobSearch(dashboard=mail_dash)
                searcher.sync_emails()
                mail_dash.set_status("Prêt")
                print("Email sync complete.")
            except Exception as e:
                traceback.print_exc()
                print(f"CRITICAL ERROR IN MAIL SYNC: {e}")
                


        elif cmd == "generate":
            print("--- Testing Generator ---")
            try:
                from modules.generator import Generator
                from modules.analyzer import Analyzer
                
                config = load_config()
                cv_path = config.get("paths", {}).get("master_cv", "data/resumes/master_cv.pdf")
                cv_text = ""
                if os.path.exists(cv_path):
                    cv_text = extract_text_from_pdf(cv_path)
                desc = "We need an NLP Engineer..."
                
                analyzer = Analyzer(config_path="config.yaml")
                print("Generating Content with LLM...")
                json_content = analyzer.generate_cover_letter(cv_text, desc, "TechCorp", "NLP Intern")
                
                gen = Generator()
                path = gen.create_application_package("TechCorp", "NLP Intern", json_content)
                print(f"Generated application in: {path}")
            except Exception as e:
                print(f"Generator Error: {e}")
    else:
        print("\nUsage:")
        print("python main.py search [--fresh]      -> Run LinkedIn Scraper & Analysis")
        print("python main.py mail                  -> Read Gmail to auto-update Notion statuses")
        print("python main.py learn                 -> Analyze 'NULL' jobs on Notion to avoid them")
        print("python main.py regenerate            -> Re-run Analysis on existing DB (No scraping)")
        print("python main.py generate              -> Run basic CV Analyzer Test\n")

if __name__ == "__main__":
    main()
