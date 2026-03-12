import yaml
import json
import os
from .scrapers.universal_scraper import UniversalScraper
from .notifier import Notifier
from .analyzer import Analyzer
from .generator import Generator
from .utils import extract_text_from_pdf
from .notion_api import NotionAPI
from .db_manager import DBManager
from concurrent.futures import ThreadPoolExecutor

from .config_loader import load_config

class JobSearch:
    def __init__(self, config_path="config.yaml", dashboard=None):
        self.config = load_config(config_path)
        
        self.dashboard = dashboard
        self.db_path = self.config.get("paths", {}).get("tracking_db", "data/jobs_db.json")
        self.db = DBManager(init_db=True)
        self.db.migrate_statuses() # One-time migration to standardize statuses
        self.seen_links = self._load_db()
        self.new_jobs = []
        self.notifier = Notifier(config_path)
        self.analyzer = Analyzer(config_path)
        self.generator = Generator(config_path)
        self.notion = NotionAPI(config_path)
        
        self.anti_patterns_file = "data/anti_patterns.txt"
        self.anti_patterns = ""
        if os.path.exists(self.anti_patterns_file):
            with open(self.anti_patterns_file, "r", encoding="utf-8") as f:
                self.anti_patterns = f.read().strip()
        
        # Load CV
        cv_path = self.config.get("paths", {}).get("master_cv", "data/cv.pdf")
        try:
            self.cv_text = extract_text_from_pdf(cv_path)
        except:
            print("Warning: Could not load CV for generation.")
            self.cv_text = ""

    # ... (load_db and save_db remain same)
    
    def _clean_url(self, url):
        """Removes tracking tokens while preserving unique Job IDs (e.g., Indeed jk)."""
        if not url: return ""
        try:
            if "indeed" in url.lower():
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)
                if 'jk' in qs:
                    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?jk={qs['jk'][0]}"
        except Exception:
            pass
            
        return url.split('?')[0]

    def _load_db(self):
        """
        Loads the database of seen jobs directly from PostgreSQL.
        This provides instant local state restoration without Notion API latency.
        """
        if self.dashboard:
            self.dashboard.log("Loading previously seen jobs from PostgreSQL Database...")
        try:
            seen_links = self.db.get_all_seen_links()
            if self.dashboard:
                self.dashboard.log(f"Loaded {len(seen_links)} jobs instantly.")
            return seen_links
        except Exception as e:
            print(f"Error loading from DB: {e}")
            return set()

    def _save_db(self, all_jobs):
        """
        Deprecated. Data is now saved directly to Notion per-job.
        Kept for backward-compatibility only for extreme local fallbacks.
        """
        pass

    def process_job(self, job):
        """
        Runs the full analysis and generation pipeline for a single job.
        """
        try:
            if not job.get("description"):
                job["description"] = "Description manquante."
                
            base_stub = f"Role: {job['title']} at {job['company']}. Source: {job['source']}.\n\n"
            job_desc_stub = base_stub + (job.get("description") or "No further description available.")
            
            # Language Detection
            language = "fr"
            if "intern" in job['title'].lower() or "internship" in job['title'].lower():
                language = "en"
            
            if self.dashboard:
                self.dashboard.log(f"Processing {job['company']} ({language.upper()})")

            # A. Extract CV Critique (Cached from earlier JSON analysis)
            critique_dict = job.get('ai_critique')
            if not critique_dict:
                # Fallback if somehow not cached
                critique_dict = self.analyzer.analyze_job_match_json(self.cv_text, job_desc_stub, anti_patterns=self.anti_patterns)
                if not critique_dict:
                    return False
            
            real_score = critique_dict.get("match_score", 0)
            job['ai_score'] = real_score

            if real_score < 80:
                if self.dashboard:
                    self.dashboard.log(f"Skipping {job['company']}: Match {real_score}% < 80%")
                return False

            # B. Generate Application (Cover Letter)
            json_content = self.analyzer.generate_cover_letter(
                self.cv_text, job_desc_stub, job['company'], job['title'], language=language
            )
            folder_path = self.generator.create_application_package(
                job['company'], job['title'], json_content, language=language
            )
            job["status"] = "À postuler"
            app_path = os.path.join(folder_path, "Cover_Letter.txt")
            
            # C. Generate CV Optimization Blocks (Hybrid Mode)
            # Full Scan "CV_Optimization.txt"
            injection_blocks = self.analyzer.tailor_cv(self.cv_text, job_desc_stub, language=language)
            cv_path = self.generator.create_injection_file(job['company'], injection_blocks)
            
            if self.dashboard:
                self.dashboard.log(f"Generated docs for {job['company']}")
            
            # Send Notification
            files_to_send = []
            if app_path: files_to_send.append(app_path)
            if cv_path: files_to_send.append(cv_path)
            
            # Extract cover letter intro for preview
            cl_preview = ""
            try:
                import json as pyjson
                cl_data = pyjson.loads(json_content.replace('```json', '').replace('```', '').strip())
                cl_preview = cl_data.get("intro_paragraph", "")
            except:
                pass

            self.notifier.send_job_alert(job, file_paths=files_to_send, critique_summary=critique_dict, cl_preview=cl_preview)
            
            # Sync to Notion
            if hasattr(self, 'notion') and self.notion.token:
                score_str = str(job.get('ai_score', 'N/A'))
                # Extract short description from JSON array 
                short_desc = critique_dict.get("SHORT_DESCRIPTION", "")
                
                self.notion.add_job_entry(job, score_str, short_desc=short_desc)
                if self.dashboard:
                    self.dashboard.log(f"Synced {job['company']} to Notion.")
            
            return True

        except Exception as e:
            if self.dashboard:
                self.dashboard.log(f"Failed to process {job['company']}: {e}")
            return False

    def regenerate_from_db(self):
        """
        Reloads the Jobs DB and re-runs generation/notification for ALL jobs found.
        Useful when the user updates their CV and wants to re-test without scraping.
        """
        if self.dashboard:
            self.dashboard.log("--- REGENERATION MODE ---")
        
        # Load DB manually from PostgreSQL
        try:
            db_jobs = self.db.get_all_jobs()
            jobs = []
            for j in db_jobs:
                # Map PostgreSQL french columns back to English expected by process_job()
                mapped_job = {
                    "company": j.get("entreprise", ""),
                    "title": j.get("titre", ""),
                    "location": j.get("lieu", ""),
                    "status": j.get("statut", "NULL"),
                    "ai_score": j.get("score_ia", 0),
                    "link": j.get("lien", ""),
                    "ai_critique": j.get("critique_ia"),
                    "source": "PostgreSQL"
                }
                jobs.append(mapped_job)
        except Exception as e:
            if self.dashboard: self.dashboard.log(f"Error loading from DB: {e}")
            jobs = []

        if self.dashboard:
             self.dashboard.log(f"Loaded {len(jobs)} jobs from PostgreSQL DB.")

        for job in jobs:
            self.process_job(job)

    def learn_from_rejections(self):
        """Fetches 'NULL' jobs from Notion, analyzes patterns, and updates anti_patterns.txt"""
        if not hasattr(self, 'notion') or not self.notion.token:
            print("Notion not configured.")
            return

        print("Fetching rejected 'NULL' applications from Notion...")
        rejected_jobs = self.notion.get_rejected_jobs()
        if not rejected_jobs:
            print("No rejected jobs found. Set some jobs to 'NULL' in Notion to teach the AI.")
            return

        print(f"Found {len(rejected_jobs)} rejected jobs. Analyzing common anti-patterns...")
        new_patterns = self.analyzer.analyze_rejections(rejected_jobs)
        
        if new_patterns:
            print("\n--- NEW AI ANTI-PATTERNS LEARNED ---")
            print(new_patterns)
            print("------------------------------------\n")
            
            import os
            os.makedirs("data", exist_ok=True)
            with open(self.anti_patterns_file, "w", encoding="utf-8") as f:
                f.write(new_patterns)
            
            print(f"Successfully saved to {self.anti_patterns_file}. Future searches will avoid these.")
        else:
            print("Failed to deduce clear patterns.")

    def _normalize_company_name(self, name):
        """Standardizes company names for better matching (removes S.A.S, LLC, etc.)"""
        import re
        if not name: return ""
        n = name.lower()
        # Remove common suffixes and punctuation
        n = re.sub(r'(\bs\.?a\.?s\.?\b|\bs\.?a\.?\b|\bl\.?l\.?c\.?\b|\bi\.?n\.?c\.?\b|\bg?mbh\b|\bgroup\b|\bgroupe\b)', '', n)
        n = re.sub(r'[^\w\s]', '', n)
        return n.strip()

    def sync_emails(self):
        """Fetches recent emails, matches them to active DB applications, and manages Gmail."""
        print("--- ✉️  AUTO-MAILING SYNC ---")
        try:
            from .mail_reader import MailReader
            reader = MailReader()
        except Exception as e:
            print(f"Could not initialize MailReader: {e}")
            if self.dashboard: self.dashboard.log(f"MailReader Error: {e}")
            return

        print("Fetching active applications from local Database...")
        active_jobs = self.db.get_active_applications()
        if not active_jobs:
            print("No active applications found awaiting response.")
            if self.dashboard: self.dashboard.log("No active applications to sync.")
            return
            
        print(f"Fetching latest unread emails (up to 30 from past 7 days)...")
        emails = reader.get_latest_unread_emails(days_back=7, limit=30)
        if not emails:
            print("Inbox is clean. No new unread emails.")
            if self.dashboard: self.dashboard.log("Inbox is clean.")
            return
            
        print(f"Analyzing {len(emails)} unread emails against {len(active_jobs)} active applications...")
        if self.dashboard: self.dashboard.log(f"Correlating {len(emails)} emails...")
        
        processed_email_ids = set()
        
        for job in active_jobs:
            raw_company = job['entreprise']
            norm_company = self._normalize_company_name(raw_company)
            
            if self.dashboard: self.dashboard.log(f"Searching for feedback from: {raw_company}...")
            
            for em in emails:
                if em['id'] in processed_email_ids:
                    continue
                    
                sender = em['sender'].lower()
                subject = em['subject'].lower()
                body = em.get('body', '').lower()
                
                # Check for mention of company name
                match_found = False
                if norm_company and (norm_company in sender or norm_company in subject or norm_company in body):
                    match_found = True
                    match_type = "Normalized"
                elif raw_company and raw_company.strip() and (raw_company.lower() in sender or raw_company.lower() in subject or raw_company.lower() in body):
                    match_found = True
                    match_type = "Raw"

                if match_found:
                    msg = f"Match ({match_type}) for {raw_company} in email: '{em['subject'][:50]}...'"
                    msg = f"Match found for {raw_company} in email!"
                    print(f"\n{msg}")
                    if self.dashboard: self.dashboard.log(msg)
                    
                    # Ask LLM to classify
                    status_change = self.analyzer.analyze_email_response(em['subject'], em['body'], raw_company)
                    log_msg = f"AI Classified as: {status_change}"
                    print(f"🧠 {log_msg}")
                    if self.dashboard: self.dashboard.log(log_msg)
                    
                    processed_email_ids.add(em['id'])
                    
                    if status_change == "POSTULE":
                        # Mark as read/processed (not delete, to keep history)
                        if job['statut'] != "Postulé":
                            self.db.update_job_status_by_company(job['entreprise'], "Postulé")
                            if hasattr(self, 'notion') and self.notion.token:
                                self.notion.update_job_status_by_company(job['entreprise'], "Postulé")
                            if self.dashboard: self.dashboard.log(f"Confirmation for {job['entreprise']} -> DB/Notion: Postulé")
                    elif status_change == "REFUS":
                        if job['statut'] != "NULL":
                            self.db.update_job_status_by_company(job['entreprise'], "NULL")
                            if hasattr(self, 'notion') and self.notion.token:
                                self.notion.update_job_status_by_company(job['entreprise'], "NULL")
                            if self.dashboard: self.dashboard.log(f"Rejection detected for {job['entreprise']} -> DB/Notion: NULL")
                    elif status_change == "ENTRETIEN":
                        reader.mark_unread(em['id']) # Keep unread so user sees it in Gmail
                        if job['statut'] != "En cours":
                            self.db.update_job_status_by_company(job['entreprise'], "En cours")
                            if hasattr(self, 'notion') and self.notion.token:
                                self.notion.update_job_status_by_company(job['entreprise'], "En cours")
                            if self.dashboard: self.dashboard.log(f"ENTRETIEN detected for {job['entreprise']} -> DB/Notion: En cours")
                            
                        # AUTO-DRAFT REPLY
                        draft_text = self.analyzer.generate_interview_reply_draft(job['entreprise'], em['body'])
                        if reader.create_draft_reply(em['sender'], em['subject'], draft_text, em.get('message_id'), em.get('references')):
                            draft_msg = f"✍️ Auto-Draft reply created for {job['entreprise']}!"
                            print(draft_msg)
                            if self.dashboard: self.dashboard.log(draft_msg)
                    else:
                        # AI says IGNORE
                        reader.mark_unread(em['id'])
                        if self.dashboard: self.dashboard.log(f"Email from {job['entreprise']} ignored (AI). Keeping unread.")
                    
                    # Stop looking for this job in other emails for now (or continue if multiple emails? usually one is enough for a status update)
                    break
        
        # FINAL STEP: Process unmatched emails utilizing the LLM to discover unknown companies
        unmatched_count = 0
        discovered_count = 0
        import datetime
        
        for em in emails:
            if em['id'] not in processed_email_ids:
                if self.dashboard: self.dashboard.log(f"Analyzing unmatched email with AI: {em['subject'][:30]}...")
                
                analysis = self.analyzer.analyze_unknown_email(em['subject'], em.get('body', ''))
                
                if analysis.get("is_job_response") and analysis.get("company_name") and analysis.get("status") in ["POSTULE", "REFUS", "ENTRETIEN"]:
                    new_company = analysis["company_name"]
                    new_status = analysis["status"]
                    job_title = analysis.get("job_title", "Candidature Spontanée / Inconnue")
                    
                    # Convert AI string back to PostgreSQL strict Enums based on your mapping
                    db_status = "NULL"
                    if new_status == "POSTULE": db_status = "Postulé"
                    elif new_status == "ENTRETIEN": db_status = "En cours"
                    elif new_status == "REFUS": db_status = "NULL"
                    
                    msg = f"🌟 AI DISCOVERY: {new_status} from {new_company} for {job_title}"
                    print(msg)
                    if self.dashboard: self.dashboard.log(msg)
                    
                    # Add to tracking database
                    new_job = {
                        "titre": job_title,
                        "entreprise": new_company,
                        "lieu": "Inconnu (Via Email)",
                        "lien": f"email://{em['id']}",
                        "source": "Gmail Scraper",
                        "statut": db_status,
                        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                        "score_ia": 0
                    }
                    self.db.save_job(new_job)
                    discovered_count += 1
                    
                    # Push critical statuses to Notion so User sees them on the board
                    if db_status in ["En cours", "Postulé"] and hasattr(self, 'notion') and self.notion.token:
                        self.notion.add_job_entry(new_job, "0", short_desc="Auto-discovered from Gmail.")
                        if self.dashboard: self.dashboard.log(f"Created Notion card for {new_company}.")
                        
                    # Auto-Drafting for discovered interviews
                    if db_status == "En cours":
                        reader.mark_unread(em['id']) # Keep unread so user sees the interview request!
                        draft_text = self.analyzer.generate_interview_reply_draft(new_company, em.get('body', ''))
                        if reader.create_draft_reply(em['sender'], em['subject'], draft_text, em.get('message_id'), em.get('references')):
                            draft_msg = f"✍️ Auto-Draft reply created for {new_company}!"
                            print(draft_msg)
                            if self.dashboard: self.dashboard.log(draft_msg)
                else:
                    reader.mark_unread(em['id']) # Restore truly irrelevant emails
                    unmatched_count += 1
        
        if unmatched_count > 0:
            msg = f"Restored {unmatched_count} unrelated emails to 'Unread' status."
            print(msg)
            if self.dashboard: self.dashboard.log(msg)
            
        if discovered_count > 0:
            msg = f"🎉 Discovery Mode extracted {discovered_count} new interactions from emails!"
            print(msg)
            if self.dashboard: self.dashboard.log(msg)
                    
        print("\n--- ✅ Email sync complete ---")
        if self.dashboard: self.dashboard.log("Email sync complete.")
            
    def _filter_candidates(self, results):
        job_pool = []
        blacklist = self.config.get("blacklist", {}).get("companies", [])
        
        # Backward compatibility check for old config key
        if not blacklist:
            blacklist = self.config.get("search", {}).get("exclude_companies", [])
            
        blacklist_lower = [c.lower().strip() for c in blacklist if c]
            
        for job in results:
            # 1. Company Blacklist Filter
            company = str(job.get('company', '')).lower().strip()
            if any(b in company for b in blacklist_lower) and company:
                if self.dashboard: self.dashboard.log(f"Ignoring blacklisted company: {job['company']}")
                continue
                
            # 2. Key Term Filter (relaxed: handled by _passes_quick_filter)
            if not self._passes_quick_filter(job):
                continue
            cleaned_link = self._clean_url(job.get("link", ""))
            if cleaned_link and cleaned_link not in self.seen_links:
                job["link"] = cleaned_link # Normalize right away
                job_pool.append(job)
                if len(job_pool) >= 15: # Cap pool at 15 to save API tokens and time
                    break
        return job_pool

    def _passes_quick_filter(self, job):
        """Fast keyword-based filter to avoid calling LLM for obvious garbage."""
        if not self.config.get("performance", {}).get("quick_filter", True):
            return True
            
        title = job.get("title", "").lower()
        desc = job.get("description", "").lower()
        
        # Mandatory positive keywords (for internships)
        positives = ["stage", "intern", "stagiaire", "alternance", "apprenti", "co-op"]
        if not any(p in title or p in desc for p in positives):
            return False
            
        # Hard negative keywords (e.g. CDD/CDI/Senior if not also mentioning stage)
        negatives = ["senior engineer", "lead engineer", "directeur", "vp of"]
        if any(n in title for n in negatives):
            return False
            
        return True

    def _score_single_candidate(self, job):
        """Worker function for parallel scoring."""
        try:
            if not self._passes_quick_filter(job):
                return None
                
            base_stub = f"Role: {job['title']} at {job['company']}. Source: {job['source']}.\n\n"
            job_desc_stub = base_stub + (job.get("description") or "No description provided.")
            
            json_match = self.analyzer.analyze_job_match_json(self.cv_text, job_desc_stub, anti_patterns=self.anti_patterns)
            
            if json_match:
                score = json_match.get("match_score", 0)
                job['ai_score'] = score
                job['ai_critique'] = json_match
                
                if self.dashboard:
                    self.dashboard.log(f"  - [{score:02d}/100] {job['title']} @ {job['company']}")
                    if score >= 80:
                        self.dashboard.update_stats(matches=1)
                return job
        except Exception as e:
            if self.dashboard:
                self.dashboard.log(f"Error scoring {job.get('company')}: {e}")
        return None

    def _score_candidates(self, job_pool):
        max_threads = self.config.get("performance", {}).get("max_threads", 4)
        scored_jobs = []
        
        if self.dashboard:
            self.dashboard.log(f"Starting parallel evaluation (Threads: {max_threads})...")
            
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            results = list(executor.map(self._score_single_candidate, job_pool))
            
        scored_jobs = [r for r in results if r is not None]
        
        # Sort Descending by Score
        scored_jobs.sort(key=lambda x: x.get('ai_score', 0), reverse=True)
        return scored_jobs

    def run(self):
        scraper = UniversalScraper(self.config, dashboard=self.dashboard)
        keywords = self.config["search"]["keywords"]
        locations = self.config["search"]["locations"]
        
        if self.dashboard:
            self.dashboard.log(f"Starting Multi-Platform Global Search...")
        
        import time
        import random

        total_found = 0
        target_limit = 5
        if self.dashboard:
            self.dashboard.log(f"Target validation for this run: {target_limit} offers")
            
        random.shuffle(keywords)
        max_threads = self.config.get("performance", {}).get("max_threads", 4)
        
        stop_search = False
        for location in locations:
            if stop_search: break
            for keyword in keywords:
                if stop_search: break
                
                try:
                    results = scraper.search_jobs(keyword, location)
                    
                    if self.dashboard:
                        self.dashboard.log(f"  > Found {len(results)} raw results across platforms.")
                    
                    # 1. Gather all candidates
                    job_pool = self._filter_candidates(results)

                    if not job_pool:
                        if self.dashboard: self.dashboard.log("No new valid internships here.")
                        continue
                    
                    # ✅ PRE-SAVE: Immediately write every candidate to PostgreSQL
                    for job in job_pool:
                        job['status'] = 'NULL'
                        self.seen_links.add(job["link"])
                        self.db.save_job(job)
                    
                    if self.dashboard:
                        self.dashboard.update_stats(scanned=len(job_pool))
                        self.dashboard.log(f"Evaluating {len(job_pool)} candidate jobs with AI...")
                    
                    # 2 & 3. Score Candidates & Sort Descending by Score
                    scored_jobs = self._score_candidates(job_pool)
                    
                    # 4. Process the Top Matches in Parallel
                    high_score_jobs = [j for j in scored_jobs if j.get('ai_score', 0) >= 80]
                    
                    if high_score_jobs:
                        if self.dashboard:
                            self.dashboard.log(f"Processing {len(high_score_jobs)} top matches in parallel...")
                        
                        with ThreadPoolExecutor(max_workers=max_threads) as process_executor:
                            # Map process_job to the top jobs
                            # We filter success results later
                            results = list(process_executor.map(self.process_job, high_score_jobs))
                            
                            for job, success in zip(high_score_jobs, results):
                                # Update Dashboard Visuals for top matches
                                if self.dashboard:
                                    self.dashboard.add_job_row(job['source'], job['company'], job['title'], f"Match: {job['ai_score']}%")
                                
                                self.new_jobs.append(job)
                                if success:
                                    job['status'] = "À postuler"
                                    self.db.save_job(job)
                                    total_found += 1
                                else:
                                    job['status'] = "NULL"
                                    self.db.save_job(job)
                                    
                                if total_found >= target_limit:
                                    stop_search = True
                                    break
                                    
                    # Still add the low-score jobs to new_jobs list for dashboard visibility if needed
                    for job in scored_jobs:
                        if job.get('ai_score', 0) < 80:
                            self.new_jobs.append(job)
                            job['status'] = "NULL"
                            self.db.save_job(job)
                            
                except Exception as e:
                    if self.dashboard:
                        self.dashboard.log(f"Error during Universal Search: {e}")
                    import traceback
                    traceback.print_exc()

        return self.new_jobs

