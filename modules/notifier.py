import requests
import yaml
import json
import os
import traceback
from datetime import datetime

from .config_loader import load_config

class Notifier:
    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        
        self.webhook_url = self.config["discord"].get("webhook_url")
        self.username = self.config["discord"].get("username", "Stage Hunter")
        self.avatar_url = self.config["discord"].get("avatar_url", "")

    def send_job_alert(self, job, file_paths=None, critique_summary=None, cl_preview=None):
        if not self.webhook_url:
            print("Warning: No Discord Webhook configured. Skipping notification.")
            return

        # ... (rest of the logic remains the same, but using the updated embed structure)

        # Determine color based on match score
        color = 5763719 # Green
        
        # Always prioritize the fast score which includes Anti-Pattern learning
        ai_score_val = job.get('ai_score')
        
        if ai_score_val is not None and str(ai_score_val) != "N/A":
            match_score = f"{ai_score_val}%"
            try:
                score_int = int(ai_score_val)
                if score_int < 50:
                    color = 15158332 # Red
                elif score_int < 80:
                    color = 16776960 # Yellow
            except:
                pass
        else:
            match_score = "N/A"

        short_desc = "N/A"
        company_info = "N/A"
        pros_cons = "N/A"
        missing_kw = "N/A"
        
        if isinstance(critique_summary, dict):
            if match_score == "N/A":
                ms = critique_summary.get("match_score", 0)
                match_score = f"{ms}%"
                try:
                    score_int = int(ms)
                    if score_int < 50:
                        color = 15158332 # Red
                    elif score_int < 80:
                        color = 16776960 # Yellow
                except:
                    pass
            
            short_desc = critique_summary.get("short_description", "N/A")
            if isinstance(short_desc, list):
                short_desc = "\n".join([f"- {item}" for item in short_desc])
                
            company_info = critique_summary.get("company_info", "N/A")
            pros_cons = critique_summary.get("pros_cons", "N/A")
            missing_kw = critique_summary.get("missing_keywords", "N/A")
            improvement_plan = critique_summary.get("improvement_plan", "N/A")

        # Location refinement: use city if possible, fallback to job location
        display_location = job.get('location', 'Unknown')

        # Build consolidated description for "main message" as requested
        consolidated_desc = f"**Company:** {job['company']}\n"
        consolidated_desc += f"**Location:** {display_location}\n"
        consolidated_desc += f"**Source:** {job['source']}\n\n"
        
        if short_desc != "N/A":
            consolidated_desc += f"📝 **Missions :**\n{short_desc}\n\n"
        if company_info != "N/A":
            consolidated_desc += f"🏢 **À propos :** {company_info}\n\n"
        if pros_cons != "N/A":
            consolidated_desc += f"⚖️ **Avantages/Inconvénients :**\n{pros_cons}\n\n"
            
        consolidated_desc += f"🎯 **Match Score**\n{match_score}\n"
        consolidated_desc += f"🔗 **Quick Link**\n[Apply Now]({job['link']})\n"
        
        if missing_kw != "N/A":
            consolidated_desc += f"❌ **Mots-clés manquants**\n{missing_kw}\n"
            
        consolidated_desc += f"📄 **Documents**\nLes fichiers (DOCX/TXT) sont jointes en bas de ce message.\n"

        embed = {
            "title": f"🎓 New Internship: {job['title']}",
            "description": consolidated_desc,
            "url": job['link'],
            "color": color,
            "footer": {
                "text": f"Stage Hunter 3000 • {datetime.now().strftime('%d/%m %H:%M')}",
            }
        }

        payload = {
            "username": self.username,
            "avatar_url": self.avatar_url,
            "embeds": [embed]
        }

        try:
            if file_paths:
                files = {}
                for i, path in enumerate(file_paths):
                    if os.path.exists(path):
                        filename = os.path.basename(path)
                        files[f"file{i}"] = (filename, open(path, "rb"))
                
                if files:
                    response = requests.post(
                        self.webhook_url, 
                        data={"payload_json": json.dumps(payload)}, 
                        files=files
                    )
                    # Close files
                    for _, file_tuple in files.items():
                        file_tuple[1].close()
                else:
                    response = requests.post(self.webhook_url, json=payload)
            else:
                response = requests.post(self.webhook_url, json=payload)
                
            if response.status_code >= 400:
                print(f"Error sending to Discord webhook: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Failed to send Discord alert: {e}")

    def send_empty_state_alert(self):
        """Sends a notification that no new matching jobs were found."""
        if not self.webhook_url:
            print("Warning: No Discord Webhook configured. Skipping empty state notification.")
            return

        embed = {
            "title": "🏜️ Aucune nouvelle offre détectée",
            "description": "Je viens d'analyser les dernières offres LinkedIn avec tes critères, mais rien de neuf sous le soleil. Je repars en veille ! 💤",
            "color": 8421504, # Gray
            "footer": {
                "text": f"Stage Hunter 3000 • {datetime.now().strftime('%H:%M')}",
            }
        }
        
        payload = {
            "username": self.username,
            "avatar_url": self.avatar_url,
            "embeds": [embed]
        }
        
        try:
            response = requests.post(self.webhook_url, json=payload)
            if response.status_code >= 400:
                print(f"Error sending empty state alert to Discord webhook: {response.status_code} - {response.text}")
            else:
                print("Empty state alert sent successfully.")
        except Exception as e:
            print(f"Failed to send empty state alert: {e}")

    def send_startup_alert(self):
        """Sends a notification that the bot has successfully started."""
        if not self.webhook_url:
            print("Warning: No Discord Webhook configured. Skipping startup notification.")
            return

        embed = {
            "title": "🟢 Initialisation Terminée",
            "description": "Le moteur de recherche Stage Hunter 3000 vient d'être lancé avec succès ! Je commence la veille. 🚀",
            "color": 3066993, # Green
            "footer": {
                "text": f"Stage Hunter 3000 • {datetime.now().strftime('%H:%M')}",
            }
        }
        
        payload = {
            "username": self.username,
            "avatar_url": self.avatar_url,
            "embeds": [embed]
        }
        
        try:
            response = requests.post(self.webhook_url, json=payload)
            if response.status_code >= 400:
                print(f"Error sending startup alert to Discord webhook: {response.status_code} - {response.text}")
            else:
                print("Startup alert sent successfully.")
        except Exception as e:
            print(f"Failed to send startup alert: {e}")
