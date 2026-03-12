import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
import os
import json
import yaml
from datetime import datetime

class DBManager:
    def __init__(self, config_path="config.yaml", init_db=False):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        
        self.pg_config = self.config.get("postgres", {})
        self.sqlite_path = "data/jobs_local.db"
        os.makedirs("data", exist_ok=True)
        
        # Priority 1: Direct Connection URL (Supabase friendly)
        self.conn_str = self.pg_config.get('direct_url')
        
        # Standardize connection string
        if self.conn_str:
            if self.conn_str.startswith("postgres://") or self.conn_str.startswith("postgresql://"):
                if "?" in self.conn_str: self.conn_str += "&connect_timeout=3"
                else: self.conn_str += "?connect_timeout=3"
        
        self.use_sqlite = False
        self.connected = False
        
        # Attempt PG connection
        try:
            conn = psycopg2.connect(self.conn_str)
            conn.close()
            self.connected = True
            print("[DBManager] Connected to PostgreSQL (Supabase)")
        except Exception as e:
            print(f"[DBManager] PostgreSQL Connection failed ({e}). Falling back to SQLite.")
            self.use_sqlite = True
            self.connected = True # SQLite is always "connected" locally
            
        if init_db:
            self._init_db()

    def _get_conn(self):
        if self.use_sqlite:
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            return conn
        else:
            return psycopg2.connect(self.conn_str)

    def _init_db(self):
        """Creates the tables if they do not exist."""
        if self.use_sqlite:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                lien TEXT PRIMARY KEY,
                titre TEXT,
                entreprise TEXT,
                lieu TEXT,
                statut TEXT DEFAULT 'NULL',
                score_ia INTEGER DEFAULT 0,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                critique_ia TEXT -- JSON string in SQLite
            )
            ''')
            conn.commit()
            cursor.close()
            conn.close()
        else:
            conn = self._get_conn()
            cursor = conn.cursor()
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
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS critique_ia JSONB;
            ''')
            conn.commit()
            cursor.close()
            conn.close()

    def get_all_seen_links(self) -> set:
        """Loads all previously seen URLs."""
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
        if self.use_sqlite:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs ORDER BY date DESC")
            results = [dict(row) for row in cursor.fetchall()]
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM jobs ORDER BY date DESC")
            results = [dict(row) for row in cursor.fetchall()]
            
        # Parse JSON string from SQLite
        if self.use_sqlite:
            for r in results:
                if r.get('critique_ia') and isinstance(r['critique_ia'], str):
                    try: r['critique_ia'] = json.loads(r['critique_ia'])
                    except: pass

        cursor.close()
        conn.close()
        return results

    def save_job(self, job_dict):
        """Saves or updates a job."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            score = job_dict.get('ai_score', 0)
            try: score = int(score) if score is not None else 0
            except: score = 0
                
            status_val = job_dict.get('status', 'NULL')
            status_mapping = {'En Cours': 'En cours', 'En Attente': 'À postuler', 'applied_locally': 'À postuler', 'Sent to Notion': 'À postuler', 'Rejected': 'Refusé', 'Scraped': 'NULL'}
            status_val = status_mapping.get(status_val, status_val)
            
            valid_statuses = ['À postuler', 'Postulé', 'En cours', 'NULL', 'Entretien', 'Refusé', 'Mise en relation']
            if status_val not in valid_statuses: status_val = 'NULL'
                
            date_val = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            critique_ia_val = job_dict.get('ai_critique')
            if critique_ia_val in ["", " ", None]: critique_ia_val = None
            else:
                if not isinstance(critique_ia_val, str):
                    critique_ia_val = json.dumps(critique_ia_val, ensure_ascii=False)

            if self.use_sqlite:
                cursor.execute('''
                INSERT INTO jobs (lien, titre, entreprise, lieu, statut, score_ia, date, critique_ia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lien) DO UPDATE SET
                    titre=excluded.titre, entreprise=excluded.entreprise, lieu=excluded.lieu,
                    statut=excluded.statut, score_ia=excluded.score_ia, date=excluded.date, critique_ia=excluded.critique_ia
                ''', (job_dict.get('link', ''), job_dict.get('title', 'Inconnu'), job_dict.get('company', 'Inconnu'), job_dict.get('location', 'Inconnu'), status_val, score, date_val, critique_ia_val))
            else:
                cursor.execute('''
                INSERT INTO jobs (lien, titre, entreprise, lieu, statut, score_ia, date, critique_ia)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lien) DO UPDATE SET
                    titre=EXCLUDED.titre, entreprise=EXCLUDED.entreprise, lieu=EXCLUDED.lieu,
                    statut=EXCLUDED.statut, score_ia=EXCLUDED.score_ia, date=EXCLUDED.date, critique_ia=EXCLUDED.critique_ia
                ''', (job_dict.get('link', ''), job_dict.get('title', 'Inconnu'), job_dict.get('company', 'Inconnu'), job_dict.get('location', 'Inconnu'), status_val, score, date_val, critique_ia_val))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBManager] ERROR saving job: {e}")
            return False

    def get_active_applications(self) -> list:
        """Fetches active jobs for email sync."""
        conn = self._get_conn()
        if self.use_sqlite:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE statut IN ('À postuler', 'Postulé', 'En cours')")
            results = [dict(row) for row in cursor.fetchall()]
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM jobs WHERE statut IN ('À postuler', 'Postulé', 'En cours')")
            results = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        return results

    def update_job_status_by_company(self, company_name: str, new_status: str) -> bool:
        """Updates the status of the most recent job matching the company name."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        placeholder = "?" if self.use_sqlite else "%s"
        like_op = "LIKE" if self.use_sqlite else "ILIKE"
        
        cursor.execute(f'''
        UPDATE jobs SET statut = {placeholder}
        WHERE lien = (
            SELECT lien FROM jobs WHERE entreprise {like_op} {placeholder}
            ORDER BY date DESC LIMIT 1
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
