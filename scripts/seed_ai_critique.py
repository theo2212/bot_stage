import sys
import os
import json
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from modules.db_manager import DBManager

def seed_db():
    db = DBManager()
    conn = db._get_conn()
    cur = conn.cursor()
    jobs = db.get_all_jobs()
    
    count = 0
    for job in jobs:
        company = str(job.get('entreprise', ''))
        # Do not strip spaces from the middle of the string!
        safe_company = "".join([c for c in company if c.isalnum() or c in (' ', '_')]).strip()
        analysis_path = os.path.join("data", "output", safe_company, "analysis.json")
        
        if os.path.exists(analysis_path):
            with open(analysis_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    json_str = json.dumps(data)
                    cur.execute("UPDATE jobs SET critique_ia = %s WHERE lien = %s", (json_str, job['lien']))
                    count += 1
                except Exception as e:
                    print(f"Error parsing json for {company}: {e}")
                    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"Successfully seeded {count} out of {len(jobs)} jobs with local AI Critique JSON.")

if __name__ == "__main__":
    seed_db()
