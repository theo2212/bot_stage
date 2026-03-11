import sqlite3
import os
import json
from datetime import datetime

class DBManager:
    def __init__(self, db_path="data/jobs_db.sqlite"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Creates the tables if they do not exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table of Jobs
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            link TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            location TEXT,
            description TEXT,
            source TEXT,
            date_posted TEXT,
            date_scraped TEXT,
            status TEXT,
            ai_score INTEGER,
            ai_critique JSON,
            notion_url TEXT
        )
        ''')
        
        # Check if notion_url exists (for schema migration of existing db)
        cursor.execute('PRAGMA table_info(jobs)')
        columns = [info[1] for info in cursor.fetchall()]
        if 'notion_url' not in columns:
            cursor.execute('ALTER TABLE jobs ADD COLUMN notion_url TEXT')
            
        conn.commit()
        conn.close()

    def get_all_seen_links(self) -> set:
        """Instantly loads all previously seen URLs to avoid duplicate scraping."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT link FROM jobs")
        links = {row[0] for row in cursor.fetchall()}
        conn.close()
        return links

    def get_all_jobs(self) -> list:
        """Retrieves all jobs with their full AI critiques for the Dashboard."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # To return dict-like objects
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY date_scraped DESC")
        
        results = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            # Parse JSON critique if it exists
            if row_dict['ai_critique']:
                try:
                    row_dict['ai_critique'] = json.loads(row_dict['ai_critique'])
                except:
                    pass
            results.append(row_dict)
            
        conn.close()
        return results

    def save_job(self, job_dict):
        """Saves or updates a job in the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Serialize critique
        critique = job_dict.get('ai_critique', None)
        critique_json = json.dumps(critique, ensure_ascii=False) if critique else None
        
        # Handle empty/missing scores
        try:
            score = int(job_dict.get('ai_score', 0))
        except:
            score = 0
            
        cursor.execute('''
        INSERT OR REPLACE INTO jobs 
        (link, title, company, location, description, source, date_posted, date_scraped, status, ai_score, ai_critique, notion_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_dict.get('link', ''),
            job_dict.get('title', 'Titre Inconnu'),
            job_dict.get('company', 'Entreprise Inconnue'),
            job_dict.get('location', 'Inconnu'),
            job_dict.get('description', ''),
            job_dict.get('source', 'JobSpy'),
            job_dict.get('date', 'Aujourd\'hui'),
            job_dict.get('date_scraped', datetime.now().isoformat()),
            job_dict.get('status', 'NULL'),
            score,
            critique_json,
            job_dict.get('notion_url', '')
        ))
        
        conn.commit()
        conn.close()

    def get_active_applications(self) -> list:
        """Fetches jobs where 'status' is 'À postuler', 'En Attente', 'Postulé', 'Sent to Notion', or 'applied_locally'."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM jobs 
        WHERE status IN ('À postuler', 'Postulé', 'En cours')
        ''')
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def update_job_status_by_company(self, company_name: str, new_status: str) -> bool:
        """Updates the status of the most recent job matching the company name."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE jobs 
        SET status = ? 
        WHERE link = (
            SELECT link FROM jobs 
            WHERE company LIKE ? 
            ORDER BY date_scraped DESC 
            LIMIT 1
        )
        ''', (new_status, f"%{company_name}%"))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def migrate_statuses(self):
        """Standardizes all existing statuses in the DB to the new set: À postuler, Postulé, NULL."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. Map all local/notion sent or waiting states to "À postuler"
        cursor.execute("UPDATE jobs SET status = 'À postuler' WHERE status IN ('applied_locally', 'Sent to Notion', 'En Attente')")
        
        # 2. Map all email-detected rejections or raw scrapes to "NULL"
        cursor.execute("UPDATE jobs SET status = 'NULL' WHERE status IN ('Scraped', 'Refusé') OR status LIKE 'Rejected%'")
        
        # 3. Map interviews to "En cours"
        cursor.execute("UPDATE jobs SET status = 'En cours' WHERE status = 'Entretien'")
        
        conn.commit()
        conn.close()
