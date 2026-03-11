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

class JobSearch:
    def __init__(self, config_path="config.yaml", dashboard=None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        
        self.dashboard = dashboard
        self.db_path = self.config["paths"]["tracking_db"]
        self.db = DBManager()
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
        cv_path = self.config["paths"]["master_cv"]
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
        Loads the database of seen jobs directly from SQLite.
        This provides instant local state restoration without Notion API latency.
        """
        if self.dashboard:
            self.dashboard.log("Loading previously seen jobs from SQLite Database...")
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
            
            real_score = critique_dict.get("MATCH_SCORE", 0)
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
        
        # Load DB manually
        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                jobs = json.load(f)
        else:
            jobs = []

        if self.dashboard:
             self.dashboard.log(f"Loaded {len(jobs)} jobs from DB.")

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
            raw_company = job['company']
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
                elif raw_company.lower() in sender or raw_company.lower() in subject or raw_company.lower() in body:
                    match_found = True
                    match_type = "Raw"

                if match_found:
                    msg = f"Match ({match_type}) for {raw_company} in email: '{em['subject'][:50]}...'"
                    msg = f"Match found for {raw_company} in email!"
                    print(f"\n{msg}")
                    if self.dashboard: self.dashboard.log(msg)
                    
                    # Ask LLM to classify
                    status_change = self.analyzer.analyze_email_response(em['subject'], em['body'], job['company'])
                    log_msg = f"AI Classified as: {status_change}"
                    print(f"🧠 {log_msg}")
                    if self.dashboard: self.dashboard.log(log_msg)
                    
                    processed_email_ids.add(em['id'])
                    
                    if status_change == "POSTULE":
                        # Mark as read/processed (not delete, to keep history)
                        if job['status'] != "Postulé":
                            self.db.update_job_status_by_company(job['company'], "Postulé")
                            if hasattr(self, 'notion') and self.notion.token:
                                self.notion.update_job_status_by_company(job['company'], "Postulé")
                            if self.dashboard: self.dashboard.log(f"Confirmation for {job['company']} -> DB/Notion: Postulé")
                    elif status_change == "REFUS":
                        if job['status'] != "NULL":
                            self.db.update_job_status_by_company(job['company'], "NULL")
                            if hasattr(self, 'notion') and self.notion.token:
                                self.notion.update_job_status_by_company(job['company'], "NULL")
                            if self.dashboard: self.dashboard.log(f"Rejection detected for {job['company']} -> DB/Notion: NULL")
                    elif status_change == "ENTRETIEN":
                        reader.mark_unread(em['id']) # Keep unread so user sees it in Gmail
                        if job['status'] != "En cours":
                            self.db.update_job_status_by_company(job['company'], "En cours")
                            if hasattr(self, 'notion') and self.notion.token:
                                self.notion.update_job_status_by_company(job['company'], "En cours")
                            if self.dashboard: self.dashboard.log(f"ENTRETIEN detected for {job['company']} -> DB/Notion: En cours")
                    else:
                        # AI says IGNORE
                        reader.mark_unread(em['id'])
                        if self.dashboard: self.dashboard.log(f"Email from {job['company']} ignored (AI). Keeping unread.")
                    
                    # Stop looking for this job in other emails for now (or continue if multiple emails? usually one is enough for a status update)
                    break
        
        # FINAL STEP: Any email that was fetched but NOT matched must be marked as unread
        unmatched_count = 0
        for em in emails:
            if em['id'] not in processed_email_ids:
                reader.mark_unread(em['id'])
                unmatched_count += 1
        
        if unmatched_count > 0:
            msg = f"Restored {unmatched_count} unrelated emails to 'Unread' status."
            print(msg)
            if self.dashboard: self.dashboard.log(msg)
                    
        print("\n--- ✅ Email sync complete ---")
        if self.dashboard: self.dashboard.log("Email sync complete.")
            
    def _filter_candidates(self, results):
        job_pool = []
        for job in results:
            title_lower = job['title'].lower()
            if "stage" not in title_lower and "intern" not in title_lower and "stagiaire" not in title_lower:
                continue
            
            cleaned_link = self._clean_url(job.get("link", ""))
            if cleaned_link and cleaned_link not in self.seen_links:
                job["link"] = cleaned_link # Normalize right away
                job_pool.append(job)
                if len(job_pool) >= 15: # Cap pool at 15 to save API tokens and time
                    break
        return job_pool

    def _score_candidates(self, job_pool):
        scored_jobs = []
        for job in job_pool:
            base_stub = f"Role: {job['title']} at {job['company']}. Source: {job['source']}.\n\n"
            job_desc_stub = base_stub + (job.get("description") or "No description provided.")
            
            json_match = self.analyzer.analyze_job_match_json(self.cv_text, job_desc_stub, anti_patterns=self.anti_patterns)
            
            if json_match:
                score = json_match.get("MATCH_SCORE", 0)
                job['ai_score'] = score
                job['ai_critique'] = json_match
                scored_jobs.append(job)
                if score >= 80 and self.dashboard:
                    self.dashboard.update_stats(matches=1)
            
            if self.dashboard:
                display_score = job.get('ai_score', 0)
                self.dashboard.log(f"  - [{display_score:02d}/100] {job['title']} @ {job['company']}")
                
        # Sort Descending by Score
        scored_jobs.sort(key=lambda x: x['ai_score'], reverse=True)
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
                    
                    # ✅ PRE-SAVE: Immediately write every candidate to SQLite
                    for job in job_pool:
                        job['status'] = 'NULL'
                        self.seen_links.add(job["link"])
                        self.db.save_job(job)
                    
                    if self.dashboard:
                        self.dashboard.update_stats(scanned=len(job_pool))
                        self.dashboard.log(f"Evaluating {len(job_pool)} candidate jobs with AI...")
                    
                    # 2 & 3. Score Candidates & Sort Descending by Score
                    scored_jobs = self._score_candidates(job_pool)
                    
                    # 4. Process the Top Matches
                    for job in scored_jobs:
                        self.new_jobs.append(job)
                        
                        # Use standard NULL for low scores
                        job['status'] = "NULL"
                        self.db.save_job(job)
                        
                        # Update Dashboard Visuals
                        if self.dashboard and job.get('ai_score', 0) >= 80:
                            self.dashboard.add_job_row(job['source'], job['company'], job['title'], f"Match: {job['ai_score']}%")
                        
                        # PROCESS Heavy (Discord, Notion, CV Generation)
                        success = self.process_job(job)
                        if success:
                            job['status'] = "À postuler"
                            self.db.save_job(job)
                            total_found += 1
                            
                        if total_found >= target_limit:
                            if self.dashboard:
                                self.dashboard.log(f"Target of {target_limit} top matches reached. Sleeping for 10 min.")
                            stop_search = True
                            break
                            
                except Exception as e:
                    if self.dashboard:
                        self.dashboard.log(f"Error during Universal Search: {e}")
                    import traceback
                    traceback.print_exc()

        return self.new_jobs

