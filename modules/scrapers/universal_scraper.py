import pandas as pd
from jobspy import scrape_jobs
import time
import random
from modules.utils.text_cleaner import TextCleaner

class UniversalScraper:
    def __init__(self, config, dashboard=None):
        """
        Initializes the Universal Scraper using python-jobspy.
        """
        self.config = config
        self.dashboard = dashboard
        self.keywords = config.get('search', {}).get('keywords', ["NLP Engineer"])
        self.locations = config.get('search', {}).get('locations', ["Paris, France"])
        self.site_names = ["linkedin", "indeed"]

    def search_jobs(self, single_keyword, single_location) -> list:
        """
        Queries jobspy for a specific keyword and location, and returns 
        a harmonized list of job dictionaries matching the old format.
        """
        all_jobs_harmonized = []

        msg = f"[JobSpy] Querying '{single_keyword}' in '{single_location}'..."
        if self.dashboard: self.dashboard.log(msg)
        else: print(msg)
        
        # Force JobSpy to look for internships
        search_query = single_keyword
        if "stage" not in single_keyword.lower() and "intern" not in single_keyword.lower() and "alternance" not in single_keyword.lower():
            search_query = f"{single_keyword} stage"
        
        try:
            # JobSpy Call
            jobs_df = scrape_jobs(
                site_name=self.site_names,
                search_term=search_query,
                location=single_location,
                results_wanted=15, 
                hours_old=72, # Expanded to find more items if recent are scarce
                job_type="internship", 
                country_indeed="france", # Correct parameter for European sites
                linkedin_fetch_description=True # Crucial for accurate AI filtering
            )
                    
            msg_found = f"   -> Found {len(jobs_df)} raw jobs for this query."
            if self.dashboard: self.dashboard.log(msg_found)
            else: print(msg_found)
            
            if not jobs_df.empty:
                # Harmonize row by row
                for index, row in jobs_df.iterrows():
                    # Extract what we need for Notion + LLM
                    job_url = row.get("job_url", "")
                    job_url_direct = row.get("job_url_direct", "")
                    
                    # Clean the URL (prefer direct if available)
                    final_url = str(job_url_direct) if pd.notna(job_url_direct) else str(job_url)
                    
                    # Description cleanup & optimization
                    desc = str(row.get("description", ""))
                    desc = TextCleaner.clean_description(desc)
                    
                    harmonized_job = {
                        "title": str(row.get("title", "Titre inconnu")),
                        "company": str(row.get("company", "Entreprise inconnue")),
                        "location": str(row.get("location", single_location)),
                        "description": desc,
                        "link": final_url,
                        "date": str(row.get("date_posted", "Aujourd'hui")),
                        "source": str(row.get("site", "JobSpy"))
                    }
                    
                    all_jobs_harmonized.append(harmonized_job)
                            
        except Exception as e:
            err_msg = f"[UniversalScraper] Error scraping '{single_keyword}': {e}"
            if self.dashboard: self.dashboard.log(err_msg)
            else: print(err_msg)
            
        # Anti-ban sleep - reduced if we have more work to do
        sleep_time = random.uniform(1.5, 3.5) 
        sleep_msg = f"   -> Politeness sleep: {sleep_time:.1f}s..."
        if self.dashboard: self.dashboard.log(sleep_msg)
        else: print(sleep_msg)
        time.sleep(sleep_time)
                
        # Deduplicate based on link before returning
        unique_jobs = {job["link"]: job for job in all_jobs_harmonized if job.get("link")}
        
        fin_msg = f"\n[JobSpy] Finished full scan. {len(unique_jobs)} unique jobs extracted."
        if self.dashboard: self.dashboard.log(fin_msg)
        else: print(fin_msg)
        
        return list(unique_jobs.values())
