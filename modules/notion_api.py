import os
import requests
import yaml
from datetime import datetime

class NotionAPI:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.notion_config = self.config.get("notion", {})
        self.token = self.notion_config.get("token")
        self.database_id = self.notion_config.get("database_id")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def add_job_entry(self, job, ai_score, short_desc=""):
        """
        Adds a parsed job entry to the Notion Database.
        """
        if not self.token or not self.database_id:
            return False

        url = "https://api.notion.com/v1/pages"
        
        # Structure matching standard Notion Kanban columns
        data = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Titre": {
                    "title": [{"text": {"content": job.get("title", "Sans Titre")}}]
                },
                "Entreprise": {
                    "rich_text": [{"text": {"content": job.get("company", "Inconnue")}}]
                },
                "Score": {
                    "rich_text": [{"text": {"content": f"{ai_score}%"}}]
                },
                "Lieu": {
                    "rich_text": [{"text": {"content": job.get("location", "Inconnu")}}]
                },
                "Lien": {
                    "url": job.get("link", "")
                }
            }
        }
        
        # Optional: Add Status 'À postuler' if the user created a Select column named 'Statut'
        data["properties"]["Statut"] = {
            "select": {"name": "À postuler"}
        }

        try:
            response = requests.post(url, headers=self.headers, json=data)
            if response.status_code == 200:
                print(f"[Notion] Successfully added {job['company']}")
                return True
            else:
                print(f"[Notion] Error adding {job['company']}: {response.text}")
                return False
        except Exception as e:
            print(f"[Notion] Request failed: {e}")
            return False

    def get_pending_jobs(self):
        """Fetches jobs where 'Statut' is 'En Attente'"""
        if not self.token or not self.database_id:
            return []
            
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload = {
            "filter": {
                "property": "Statut",
                "select": {
                    "equals": "En Attente"
                }
            }
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                pending = []
                for p in results:
                    props = p.get("properties", {})
                    link = props.get("Lien", {}).get("url", "")
                    
                    title_arr = props.get("Titre", {}).get("title", [])
                    title = title_arr[0]["text"]["content"] if title_arr else "Sans Titre"
                    
                    company_arr = props.get("Entreprise", {}).get("rich_text", [])
                    company = company_arr[0]["text"]["content"] if company_arr else "Inconnue"
                    
                    if link:
                        pending.append({
                            "page_id": p["id"],
                            "title": title,
                            "company": company,
                            "link": link
                        })
                return pending
            else:
                print(f"[Notion] Query Error: {response.text}")
                return []
        except Exception as e:
            print(f"[Notion] Fetch failed: {e}")
            return []

    def get_rejected_jobs(self):
        """Fetches jobs where 'Statut' is 'NULL' to train the AI."""
        if not self.token or not self.database_id:
            return []
            
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload = {
            "filter": {
                "property": "Statut",
                "select": {
                    "equals": "NULL"
                }
            }
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                rejected = []
                for p in results:
                    props = p.get("properties", {})
                    
                    title_arr = props.get("Titre", {}).get("title", [])
                    title = title_arr[0]["text"]["content"] if title_arr else "Sans Titre"
                    
                    company_arr = props.get("Entreprise", {}).get("rich_text", [])
                    company = company_arr[0]["text"]["content"] if company_arr else "Inconnue"
                    
                    rejected.append({
                        "title": title,
                        "company": company
                    })
                return rejected
            else:
                print(f"[Notion] Query Error: {response.text}")
                return []
        except Exception as e:
            print(f"[Notion] Fetch failed: {e}")
            return []

    def get_active_applications(self):
        """Fetches jobs where 'Statut' is 'À postuler', 'En Attente', or 'Postulé'."""
        if not self.token or not self.database_id:
            return []
            
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload = {
            "filter": {
                "or": [
                    {"property": "Statut", "select": {"equals": "À postuler"}},
                    {"property": "Statut", "select": {"equals": "En Attente"}},
                    {"property": "Statut", "select": {"equals": "Postulé"}},
                    {"property": "Statut", "select": {"equals": "En cours"}}
                ]
            }
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                active = []
                for p in results:
                    props = p.get("properties", {})
                    
                    title_arr = props.get("Titre", {}).get("title", [])
                    title = title_arr[0]["text"]["content"] if title_arr else "Sans Titre"
                    
                    company_arr = props.get("Entreprise", {}).get("rich_text", [])
                    company = company_arr[0]["text"]["content"] if company_arr else "Inconnue"
                    
                    status = props.get("Statut", {}).get("select", {})
                    status_name = status.get("name") if status else "None"
                    
                    active.append({
                        "page_id": p["id"],
                        "title": title,
                        "company": company,
                        "status": status_name
                    })
                return active
            else:
                print(f"[Notion] Query Error: {response.text}")
                return []
        except Exception as e:
            print(f"[Notion] Fetch active failed: {e}")
            return []

    def get_all_jobs(self):
        """Fetches all jobs from the Notion database to display in the dashboard."""
        if not self.token or not self.database_id:
            return []
            
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload = {} # Empty filter fetches all
        all_jobs = []
        has_more = True
        next_cursor = None
        
        try:
            while has_more:
                if next_cursor:
                    payload["start_cursor"] = next_cursor
                    
                response = requests.post(url, headers=self.headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    
                    for p in results:
                        props = p.get("properties", {})
                        
                        title_arr = props.get("Titre", {}).get("title", [])
                        title = title_arr[0]["text"]["content"] if title_arr else "Sans Titre"
                        
                        company_arr = props.get("Entreprise", {}).get("rich_text", [])
                        company = company_arr[0]["text"]["content"] if company_arr else "Inconnue"
                        
                        loc_arr = props.get("Lieu", {}).get("rich_text", [])
                        location = loc_arr[0]["text"]["content"] if loc_arr else "Inconnue"
                        
                        score_arr = props.get("Score", {}).get("rich_text", [])
                        score_str = score_arr[0]["text"]["content"] if score_arr else "0%"
                        try:
                            score = int(score_str.replace('%', ''))
                        except:
                            score = 0
                        
                        link_obj = props.get("Lien", {}).get("url")
                        link = link_obj if link_obj else ""
                        
                        date_obj = props.get("Date", {}).get("date")
                        date_str = date_obj.get("start") if date_obj else "1970-01-01"
                        
                        status = props.get("Statut", {}).get("select", {})
                        status_name = status.get("name") if status else "None"
                        
                        critique_arr = props.get("Critique IA", {}).get("rich_text", [])
                        critique_text = ""
                        for part in critique_arr:
                            critique_text += part.get("text", {}).get("content", "")
                        
                        # Try to parse as JSON if possible, else keep as string
                        ai_critique_val = critique_text
                        if critique_text.startswith('{') and critique_text.endswith('}'):
                            try:
                                ai_critique_val = json.loads(critique_text)
                            except:
                                pass
                        
                        notion_url = p.get("url", "")
                        
                        all_jobs.append({
                            "page_id": p["id"],
                            "notion_url": notion_url,
                            "title": title,
                            "company": company,
                            "location": location,
                            "ai_score": score,
                            "link": link,
                            "timestamp": date_str,
                            "status": status_name,
                            "ai_critique": ai_critique_val
                        })
                    
                    has_more = data.get("has_more", False)
                    next_cursor = data.get("next_cursor", None)
                else:
                    print(f"[Notion] Query Error: {response.text}")
                    break
            return all_jobs
        except Exception as e:
            print(f"[Notion] Fetch all failed: {e}")
            return []

    def update_job_status(self, page_id, new_status):
        """Updates the 'Statut' column of a specific page/row."""
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {
            "properties": {
                "Statut": {
                    "select": {"name": new_status}
                }
            }
        }
        try:
            res = requests.patch(url, headers=self.headers, json=payload)
            return res.status_code == 200
        except Exception as e:
            print(f"[Notion] Update failed: {e}")
            return False

    def update_job_status_by_company(self, company_name, new_status):
        """
        Searches for a job by company name in the database and updates its status.
        Uses a case-insensitive search.
        """
        if not self.token or not self.database_id:
            return False
            
        # 1. Search for the page
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload = {
            "filter": {
                "property": "Entreprise",
                "rich_text": {
                    "contains": company_name
                }
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if not results:
                    # Try a fuzzy search by fetching active and matching manually 
                    # if simple 'contains' fails due to exact casing/naming.
                    return False
                
                # Take the most recent one (Notion returns in reverse chronological usually)
                page_id = results[0]["id"]
                return self.update_job_status(page_id, new_status)
            return False
        except Exception as e:
            print(f"[Notion] Status sync failed for {company_name}: {e}")
            return False
