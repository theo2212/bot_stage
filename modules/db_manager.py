import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
import os
import json
import yaml
from datetime import datetime

from modules.config_loader import load_config

class DBManager:
    def __init__(self, config_path="config.yaml", init_db=False):
        self.config = load_config(config_path)
        
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
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                email TEXT,
                cv_text TEXT,
                full_name TEXT,
                phone TEXT,
                linkedin_url TEXT,
                search_config TEXT -- JSON string
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                lien TEXT,
                titre TEXT,
                entreprise TEXT,
                lieu TEXT,
                statut TEXT DEFAULT 'NULL',
                score_ia INTEGER DEFAULT 0,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                critique_ia TEXT, -- JSON string in SQLite
                user_id INTEGER,
                PRIMARY KEY (lien, user_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
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

            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                password_hash TEXT,
                email TEXT,
                cv_text TEXT,
                full_name TEXT,
                phone TEXT,
                linkedin_url TEXT,
                search_config JSONB
            );

            CREATE TABLE IF NOT EXISTS jobs (
                lien TEXT,
                titre TEXT,
                entreprise TEXT,
                lieu TEXT,
                statut job_status DEFAULT 'NULL',
                score_ia INTEGER DEFAULT 0,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                critique_ia JSONB,
                user_id INTEGER REFERENCES users(id),
                PRIMARY KEY (lien, user_id)
            );
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS critique_ia JSONB;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id INTEGER;
            ''')
            
            # Migration for V1.5: Drop old PK and add new composite PK in PG
            try:
                cursor.execute("""
                    DO $$ 
                    BEGIN 
                        IF EXISTS (
                            SELECT 1 FROM information_schema.table_constraints 
                            WHERE table_name='jobs' AND constraint_type='PRIMARY KEY'
                        ) THEN
                            IF (SELECT count(*) FROM information_schema.key_column_usage WHERE table_name='jobs' AND constraint_name=(
                                SELECT constraint_name FROM information_schema.table_constraints 
                                WHERE table_name='jobs' AND constraint_type='PRIMARY KEY' LIMIT 1
                            )) = 1 THEN
                                ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_pkey;
                                ALTER TABLE jobs ADD PRIMARY KEY (lien, user_id);
                            END IF;
                        END IF;
                    END $$;
                """)
            except: pass
            
            conn.commit()
            cursor.close()
            conn.close()

    def get_all_seen_links(self, user_id=None) -> set:
        """Loads all previously seen URLs for a specific user to prevent global deduplication."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if user_id:
            placeholder = "?" if self.use_sqlite else "%s"
            cursor.execute(f"SELECT lien FROM jobs WHERE user_id = {placeholder}", (user_id,))
        else:
            cursor.execute("SELECT lien FROM jobs")
            
        links = {row[0] for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return links

    def get_all_jobs(self, user_id=None) -> list:
        """Retrieves all jobs for the Dashboard, optionally filtered by user."""
        conn = self._get_conn()
        query = "SELECT * FROM jobs"
        params = []
        if user_id:
            query += " WHERE user_id = %s" if not self.use_sqlite else " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY date DESC"

        if self.use_sqlite:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
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

    def save_job(self, job_dict, user_id=None):
        """Saves or updates a job, linking it to a user."""
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
                INSERT INTO jobs (lien, titre, entreprise, lieu, statut, score_ia, date, critique_ia, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lien, user_id) DO UPDATE SET
                    titre=excluded.titre, entreprise=excluded.entreprise, lieu=excluded.lieu,
                    statut=excluded.statut, score_ia=excluded.score_ia, date=excluded.date, critique_ia=excluded.critique_ia
                ''', (job_dict.get('link', ''), job_dict.get('title', 'Inconnu'), job_dict.get('company', 'Inconnu'), job_dict.get('location', 'Inconnu'), status_val, score, date_val, critique_ia_val, user_id))
            else:
                cursor.execute('''
                INSERT INTO jobs (lien, titre, entreprise, lieu, statut, score_ia, date, critique_ia, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lien, user_id) DO UPDATE SET
                    titre=EXCLUDED.titre, entreprise=EXCLUDED.entreprise, lieu=EXCLUDED.lieu,
                    statut=EXCLUDED.statut, score_ia=EXCLUDED.score_ia, date=EXCLUDED.date, critique_ia=EXCLUDED.critique_ia
                ''', (job_dict.get('link', ''), job_dict.get('title', 'Inconnu'), job_dict.get('company', 'Inconnu'), job_dict.get('location', 'Inconnu'), status_val, score, date_val, critique_ia_val, user_id))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[DBManager] ERROR saving job: {e}")
            return False

    def get_active_applications(self, user_id=None) -> list:
        """Fetches active jobs for email sync."""
        conn = self._get_conn()
        query = "SELECT * FROM jobs WHERE statut IN ('À postuler', 'Postulé', 'En cours')"
        params = []
        if user_id:
            query += " AND user_id = %s" if not self.use_sqlite else " AND user_id = ?"
            params.append(user_id)
            
        if self.use_sqlite:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
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
        conn.commit()
        cursor.close()
        conn.close()
        return updated

    def update_job_status(self, lien: str, new_status: str) -> bool:
        """Updates the status of a specific job by its link."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        valid_statuses = ['À postuler', 'Postulé', 'En cours', 'NULL', 'Entretien', 'Refusé', 'Mise en relation']
        if new_status not in valid_statuses:
            return False
            
        placeholder = "?" if self.use_sqlite else "%s"
        cursor.execute(f"UPDATE jobs SET statut = {placeholder} WHERE lien = {placeholder}", (new_status, lien))
        
        updated = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        conn.close()
        return updated

    def get_rejected_jobs(self, user_id=None, limit=20) -> list:
        """Fetches recently rejected jobs for learning."""
        conn = self._get_conn()
        query = "SELECT titre, entreprise FROM jobs WHERE statut = 'Refusé'"
        params = []
        if user_id:
            query += " AND user_id = %s" if not self.use_sqlite else " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY date DESC LIMIT %s" if not self.use_sqlite else " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        
        if self.use_sqlite:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        return results

    def migrate_statuses(self):
        """Obsolete: Statuses are now enforced as ENUM upon insertion."""
        pass
