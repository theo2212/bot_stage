import yaml
import json
import os
from .scrapers.linkedin import LinkedInScraper
from .notifier import Notifier
from .analyzer import Analyzer
from .generator import Generator
from .utils import extract_text_from_pdf
from .notion_api import NotionAPI

class JobSearch:
    def __init__(self, config_path="config.yaml", dashboard=None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        
        self.dashboard = dashboard
        self.db_path = self.config["paths"]["tracking_db"]
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
        """Removes tracking tokens (like ?refId=) from LinkedIn URLs."""
        if not url: return ""
        return url.split('?')[0]

    def _load_db(self):
        """
        Loads the database of seen jobs directly from Notion.
        This establishes Notion as the Single Source of Truth.
        """
        seen_links = set()
        if hasattr(self, 'notion') and self.notion.token:
            if self.dashboard:
                self.dashboard.log("Loading previously seen jobs from Notion...")
            try:
                # Fetch all jobs to extract their links
                all_notion_jobs = self.notion.get_all_jobs()
                for job in all_notion_jobs:
                    if job.get("link"):
                        cleaned = self._clean_url(job["link"])
                        seen_links.add(cleaned)
                if self.dashboard:
                    self.dashboard.log(f"Loaded {len(seen_links)} jobs from Notion.")
            except Exception as e:
                print(f"Error loading from Notion: {e}")
                
        # Fallback to local DB ONLY if Notion fails or is not configured
        if not seen_links and os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    seen_links = {job["link"] for job in data}
            except Exception:
                pass
                
        return seen_links

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
                from .scrapers.linkedin import LinkedInScraper
                scraper = LinkedInScraper()
                job["description"] = scraper.get_job_description(job['link'])
                
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
            job["status"] = "applied_locally"
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

    def sync_emails(self):
        """Fetches recent emails, matches them to active Notion applications, and updates status."""
        if not hasattr(self, 'notion') or not self.notion.token:
            print("Notion not configured.")
            return

        try:
            from .mail_reader import MailReader
            reader = MailReader()
        except Exception as e:
            print(f"Could not initialize MailReader: {e}")
            return

        print("Fetching active applications from Notion...")
        active_jobs = self.notion.get_active_applications()
        if not active_jobs:
            print("No active applications found in Notion.")
            return
            
        print("Fetching latest unread emails...")
        emails = reader.get_latest_unread_emails(days_back=7, limit=30)
        if not emails:
            print("No new unread emails found.")
            return
            
        print(f"Analyzing {len(emails)} emails against {len(active_jobs)} active applications...")
        
        for job in active_jobs:
            company = job['company'].lower()
            
            for em in emails:
                sender = em['sender'].lower()
                subject = em['subject'].lower()
                
                # Check for mention of company name
                # (A more robust version might use fuzzy matching or extracting the sender domain)
                if company in sender or company in subject:
                    print(f"\nPotential match found for {job['company']}!")
                    print(f"Subject: {em['subject']}")
                    
                    # Ask LLM to classify
                    status_change = self.analyzer.analyze_email_response(em['subject'], em['body'], job['company'])
                    print(f"AI Classification: {status_change}")
                    
                    if status_change == "POSTULE" and job['status'] in ["À postuler", "En Attente"]:
                        self.notion.update_job_status(job['page_id'], "Postulé")
                        print(f"-> Marked as 'Postulé'")
                    elif status_change == "REFUS":
                        self.notion.update_job_status(job['page_id'], "NULL")
                        print(f"-> Marked as 'NULL' (Refus)")
                    elif status_change == "ENTRETIEN":
                        self.notion.update_job_status(job['page_id'], "Entretien")
                        print(f"-> Marked as 'Entretien'")
                    
                    # Assume one email per company for this sync cycle to save API
                    break
                    
        print("\nEmail sync complete.")
            
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
            job_desc_stub = f"Role: {job['title']} at {job['company']}. Source: {job['source']}."
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
        scraper = LinkedInScraper()
        keywords = self.config["search"]["keywords"]
        locations = self.config["search"]["locations"]
        
        if self.dashboard:
            self.dashboard.log(f"Starting Global Search: {len(keywords)} keys * {len(locations)} locs")
        
        import time
        import random

        total_found = 0
        target_limit = random.randint(3, 5)
        if self.dashboard:
            self.dashboard.log(f"Target validation for this run: {target_limit} offers")
        
        # Shuffle to avoid same pattern every time
        random.shuffle(keywords)
        
        stop_search = False
        for location in locations:
            if stop_search: break
            for keyword in keywords:
                if stop_search: break
                
                if self.dashboard:
                    self.dashboard.log(f"Searching: '{keyword}' in '{location}'")
                 
                try:
                    scraper.search(keyword, location)
                    results = scraper.get_results()
                    
                    if self.dashboard:
                        self.dashboard.log(f"  > Found {len(results)} raw results.")
                    
                    # 1. Gather all candidates first
                    job_pool = self._filter_candidates(results)

                    if self.dashboard and job_pool:
                        self.dashboard.update_stats(scanned=len(job_pool))

                    if not job_pool:
                        if self.dashboard: self.dashboard.log("No new valid internships in this batch.")
                        continue
                        
                    if self.dashboard: self.dashboard.log(f"Evaluating {len(job_pool)} candidate jobs with AI...")
                    
                    # 2 & 3. Score Candidates & Sort Descending by Score
                    scored_jobs = self._score_candidates(job_pool)
                    
                    # 4. Process the Top Matches
                    for job in scored_jobs:
                        self.new_jobs.append(job)
                        self.seen_links.add(job["link"])
                        
                        # Update Dashboard
                        if self.dashboard:
                            self.dashboard.add_job_row(job['source'], job['company'], job['title'], f"Match: {job['ai_score']}%")
                        
                        # PROCESS Heavy
                        success = self.process_job(job)
                        if success:
                            total_found += 1
                            
                        if total_found >= target_limit:
                            if self.dashboard:
                                self.dashboard.log(f"Target of {target_limit} top matches reached. Stopping batch.")
                            stop_search = True
                            break
                    
                    if not stop_search:
                        # Anti-Bot Safety Delay (5-10 seconds between searches)
                        time.sleep(random.uniform(5, 10))
                    
                except Exception as e:
                    if self.dashboard:
                        self.dashboard.log(f"Error searching {keyword}: {e}")

        if total_found > 0:
            self._save_db(self.new_jobs)
            
        return self.new_jobs
