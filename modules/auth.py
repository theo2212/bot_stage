import bcrypt
import json
from modules.db_manager import DBManager

class AuthManager:
    def __init__(self, db_manager=None):
        self.db = db_manager or DBManager()

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def register_user(self, username, password, email, full_name="", phone="", linkedin="", cv_text=""):
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            hashed = self.hash_password(password)
            if self.db.use_sqlite:
                cursor.execute('''
                INSERT INTO users (username, password_hash, email, full_name, phone, linkedin_url, cv_text, search_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (username, hashed, email, full_name, phone, linkedin, cv_text, '{}'))
            else:
                cursor.execute('''
                INSERT INTO users (username, password_hash, email, full_name, phone, linkedin_url, cv_text, search_config)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (username, hashed, email, full_name, phone, linkedin, cv_text, '{}'))
            conn.commit()
            return True
        except Exception as e:
            print(f"Registration error: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def login_user(self, username, password):
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            if self.db.use_sqlite:
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            else:
                from psycopg2.extras import RealDictCursor
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            
            user = cursor.fetchone()
            if user:
                user_dict = dict(user)
                if self.check_password(password, user_dict['password_hash']):
                    return user_dict
            return None
        finally:
            cursor.close()
            conn.close()

    def update_user_config(self, user_id, config_dict):
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            config_json = json.dumps(config_dict)
            if self.db.use_sqlite:
                cursor.execute("UPDATE users SET search_config = ? WHERE id = ?", (config_json, user_id))
            else:
                cursor.execute("UPDATE users SET search_config = %s WHERE id = %s", (config_json, user_id))
            conn.commit()
            return True
        except:
            return False
        finally:
            cursor.close()
            conn.close()

    def get_user_by_id(self, user_id):
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            if self.db.use_sqlite:
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            else:
                from psycopg2.extras import RealDictCursor
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            return dict(user) if user else None
        finally:
            cursor.close()
            conn.close()

    def get_all_user_ids(self):
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM users")
            return [r[0] for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()
