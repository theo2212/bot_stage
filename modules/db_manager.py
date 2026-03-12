import psycopg2
from psycopg2.extras import RealDictCursor
import os
import json
import yaml
from datetime import datetime

class DBManager:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        
        self.pg_config = self.config.get("postgres", {})
        
        # Priority 1: Direct Connection URL (Supabase friendly)
        self.conn_str = self.pg_config.get('direct_url')
        
        # Priority 2: Individual Parameters
        if not self.conn_str or self.conn_str == "":
            self.conn_str = (
                f"host={self.pg_config.get('host', 'localhost')} "
                f"port={self.pg_config.get('port', 5432)} "
                f"user={self.pg_config.get('user', 'postgres')} "
                f"password={self.pg_config.get('password', 'password')} "
                f"dbname={self.pg_config.get('dbname', 'stage_hunter')}"
            )
        self._init_db()

    def _get_conn(self):
        return psycopg2.connect(self.conn_str)

    def _init_db(self):
        """Creates the tables if they do not exist in PostgreSQL."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Create type and table if they do not exist
        cursor.execute('''
        DO $$ BEGIN
            CREATE TYPE job_status AS ENUM ('À postuler', 'Postulé', 'En cours', 'NULL', 'Entretien', 'Refusé', 'Mise en relation');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;

        CREATE TABLE IF NOT EXISTS jobs (
            lien TEXT PRIMARY KEY,
            titre TEXT,
            entreprise TEXT,
            lieu TEXT,
            statut job_status DEFAULT 'NULL',
            score_ia INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            critique_ia JSONB
        );
        
        -- Safely add column if the table already existed before this update
        ALTER TABLE jobs ADD COLUMN IF NOT EXISTS critique_ia JSONB;
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()

    def get_all_seen_links(self) -> set:
        """Instantly loads all previously seen URLs."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT lien FROM jobs")
        links = {row[0] for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return links

    def get_all_jobs(self) -> list:
        """Retrieves all jobs for the Dashboard."""
        conn = self._get_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM jobs ORDER BY date DESC")
        
        results = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            # PostgreSQL RealDictCursor/JSONB already handles dict conversion
            results.append(row_dict)
            
        cursor.close()
        conn.close()
        return results

    def save_job(self, job_dict):
        """Saves or updates a job in PostgreSQL."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Mapping to local names
        score = job_dict.get('ai_score', 0)
        try:
            score = int(score) if score is not None else 0
        except:
            score = 0
            
        # Ensure status falls within ENUM, clean up Notion capitalizations
        status_val = job_dict.get('status', 'NULL')
        status_mapping = {
            'En Cours': 'En cours',
            'En Attente': 'À postuler',
            'applied_locally': 'À postuler',
            'Sent to Notion': 'À postuler',
            'Rejected': 'Refusé',
            'Scraped': 'NULL'
        }
        
        # Apply mapping if it exists
        status_val = status_mapping.get(status_val, status_val)
        
        valid_statuses = ['À postuler', 'Postulé', 'En cours', 'NULL', 'Entretien', 'Refusé', 'Mise en relation']
        if status_val not in valid_statuses:
            status_val = 'NULL'
            
        # Try to parse date or fallback to current
        date_val = job_dict.get('date')
        if not date_val or date_val == "1970-01-01":
            date_val = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Convert dict to JSON string for JSONB column if present
        critique_ia_val = job_dict.get('ai_critique')
        if critique_ia_val == "" or critique_ia_val == " ":
            critique_ia_val = None
            
        if critique_ia_val is not None:
            import json
            if not isinstance(critique_ia_val, str):
                critique_ia_val = json.dumps(critique_ia_val, ensure_ascii=False)
        else:
            critique_ia_val = None

        cursor.execute('''
        INSERT INTO jobs 
        (lien, titre, entreprise, lieu, statut, score_ia, date, critique_ia)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (lien) DO UPDATE SET
            titre = EXCLUDED.titre,
            entreprise = EXCLUDED.entreprise,
            lieu = EXCLUDED.lieu,
            statut = EXCLUDED.statut,
            score_ia = EXCLUDED.score_ia,
            date = EXCLUDED.date,
            critique_ia = EXCLUDED.critique_ia
        ''', (
            job_dict.get('link', ''),
            job_dict.get('title', 'Titre Inconnu'),
            job_dict.get('company', 'Entreprise Inconnue'),
            job_dict.get('location', 'Inconnu'),
            status_val,
            score,
            date_val,
            critique_ia_val
        ))
        
        conn.commit()
        cursor.close()
        conn.close()

    def get_active_applications(self) -> list:
        """Fetches active jobs for email sync."""
        conn = self._get_conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
        SELECT * FROM jobs 
        WHERE statut IN ('À postuler', 'Postulé', 'En cours')
        ''')
        
        results = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return results

    def update_job_status_by_company(self, company_name: str, new_status: str) -> bool:
        """Updates the status of the most recent job matching the company name."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE jobs 
        SET statut = %s 
        WHERE lien = (
            SELECT lien FROM jobs 
            WHERE entreprise ILIKE %s 
            ORDER BY date DESC 
            LIMIT 1
        )
        ''', (new_status, f"%{company_name}%"))
        
        updated = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        conn.close()
        return updated

    def migrate_statuses(self):
        """Obsolete: Statuses are now enforced as ENUM upon insertion."""
        pass
