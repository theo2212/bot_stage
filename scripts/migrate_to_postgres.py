import sys
import os
import json
import yaml
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from modules.notion_api import NotionAPI
from modules.db_manager import DBManager

def migrate():
    print("🚀 Starting Total Migration: Notion -> PostgreSQL")
    
    try:
        notion = NotionAPI()
        db = DBManager()
    except Exception as e:
        print(f"❌ Error initializing APIs: {e}")
        return

    print("📡 Fetching ALL jobs from Notion...")
    all_notion_jobs = notion.get_all_jobs()
    
    if not all_notion_jobs:
        print("📭 Notion database seems empty or check your token/ID.")
        return

    print(f"📦 Found {len(all_notion_jobs)} jobs. Importing to PostgreSQL...")
    
    success_count = 0
    for job in all_notion_jobs:
        try:
            # Map Notion fields to DBManager's save_job format
            # db_manager.save_job expects: link, title, company, location, status, ai_score, notion_url, etc.
            job_data = {
                "link": job.get("link", ""),
                "title": job.get("title", "Sans Titre"),
                "company": job.get("company", "Inconnue"),
                "location": job.get("location", "Inconnu"),
                "status": job.get("status", "NULL"),
                "ai_score": job.get("ai_score", 0),
                "ai_critique": job.get("ai_critique"),
                "date": job.get("timestamp", "1970-01-01")
            }
            
            db.save_job(job_data)
            success_count += 1
            if success_count % 10 == 0:
                print(f"✅ Processed {success_count}/{len(all_notion_jobs)}...")
                
        except Exception as e:
            print(f"⚠️ Error migrating {job.get('company')}: {e}")

    print(f"\n✨ Migration Complete!")
    print(f"📊 Total success: {success_count}/{len(all_notion_jobs)}")
    print("🐘 Your PostgreSQL database is now a mirror of your Notion.")

if __name__ == "__main__":
    migrate()
