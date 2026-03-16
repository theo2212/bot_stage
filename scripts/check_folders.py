import os
import sys
sys.path.append('.')
from modules.db_manager import DBManager

db = DBManager()
jobs = db.get_all_jobs()
comps_in_db = sorted(list(set([j['entreprise'] for j in jobs])))

print(f"Total Unique Companies in DB: {len(comps_in_db)}")
print(f"Total output directories: {len(os.listdir('data/output'))}")
matched = 0
out_dirs = {d.lower(): d for d in os.listdir('data/output')}

for c in comps_in_db:
    if not c.strip():
        continue
    safe_company = "".join([ch for ch in c if ch.isalnum() or ch in (' ', '_')]).strip()
    
    # Check lowercase mapping
    matched_dir = out_dirs.get(safe_company.lower())
    
    if matched_dir:
        pth = os.path.join(os.path.abspath('data/output'), matched_dir, 'analysis.json')
        if os.path.exists(pth):
            matched += 1
            # print(f"DB: '{c}' -> Matched: '{matched_dir}' -> json_exists: True")
        else:
            print(f"DB: '{c}' -> Matched: '{matched_dir}' -> NO JSON INSIDE")
    else:
        print(f"DB: '{c}' -> Expected: '{safe_company}' -> FOLDER NOT FOUND")

print(f"\nMatched {matched} / {len([c for c in comps_in_db if c.strip()])} valid unique companies.")
