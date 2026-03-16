import os
import json
import yaml
from datetime import datetime
from docx import Document

from .config_loader import load_config

class Generator:
    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        
        self.output_dir = self.config["paths"].get("output", "data/output")
        self.user_profile = self.config["user_profile"]

    def create_application_package(self, company_name, job_title, cover_letter_json_str, language="fr"):
        """
        Creates a folder for the company and saves the Cover Letter.
        """
        # specialized folder
        safe_company = "".join([c for c in company_name if c.isalnum() or c in (' ', '_')]).strip()
        target_dir = os.path.join(self.output_dir, safe_company)
        os.makedirs(target_dir, exist_ok=True)
        
        # Clean up Markdown code blocks if present
        if "```json" in cover_letter_json_str:
            cover_letter_json_str = cover_letter_json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in cover_letter_json_str:
            cover_letter_json_str = cover_letter_json_str.split("```")[1].split("```")[0].strip()
            
        # Parse content
        try:
            content = json.loads(cover_letter_json_str)
        except json.JSONDecodeError:
            print("Error decoding JSON from LLM. Saving raw text.")
            content = {"body_paragraph_1": cover_letter_json_str}

        # Localized Strings
        if language == "fr":
            subject_line = f"Objet : Candidature pour le poste de {job_title} chez {company_name}"
            salutation = "Madame, Monsieur,"
            closing = "Cordialement,"
            date_format = "%d/%m/%Y"
        else:
            subject_line = f"Subject: Application for {job_title} at {company_name}"
            salutation = "Dear Hiring Manager,"
            closing = "Sincerely,"
            date_format = "%Y-%m-%d"

        # Prepare variables
        vars = {
            "user_name": self.user_profile["name"],
            "user_email": self.user_profile["email"],
            "user_phone": self.user_profile["phone"],
            "user_linkedin": self.user_profile["linkedin"],
            "job_title": job_title,
            "company_name": company_name,
            "date": datetime.now().strftime(date_format),
            "intro_paragraph": content.get("intro_paragraph", ""),
            "body_paragraph_1": content.get("body_paragraph_1", ""),
            "body_paragraph_2": content.get("body_paragraph_2", ""),
            "closing_paragraph": content.get("closing_paragraph", ""),
        }
        
        # 1. Generate Markdown
        md_content = f"""# {vars['user_name']}
{vars['user_email']} | {vars['user_phone']} | {vars['user_linkedin']}

**Date:** {vars['date']}

**{subject_line}**

{salutation}

{vars['intro_paragraph']}

{vars['body_paragraph_1']}

{vars['body_paragraph_2']}

{vars['closing_paragraph']}

{closing}

{vars['user_name']}
"""
        md_file = os.path.join(target_dir, "Cover_Letter.md")
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        # 2. Generate TXT
        txt_content = f"""{vars['user_name']}
{vars['user_email']} | {vars['user_phone']} | {vars['user_linkedin']}

Date: {vars['date']}

{subject_line}

{salutation}

{vars['intro_paragraph']}

{vars['body_paragraph_1']}

{vars['body_paragraph_2']}

{vars['closing_paragraph']}

{closing}

{vars['user_name']}
"""
        txt_file = os.path.join(target_dir, "Cover_Letter.txt")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(txt_content)
        
        return target_dir

    def create_injection_file(self, company_name, injection_data):
        """
        Creates a comprehensive "Optimization Report" for the user to copy-paste into Canva.
        """
        if not injection_data:
            return None

        safe_company = "".join([c for c in company_name if c.isalnum() or c in (' ', '_')]).strip()
        target_dir = os.path.join(self.output_dir, safe_company)
        os.makedirs(target_dir, exist_ok=True)
        txt_file = os.path.join(target_dir, "CV_Optimization.txt")
        
        
        # Header
        content = [
            "=" * 80,
            f"🚀 OPTIMISATION CV : {company_name.upper()}",
            "=" * 80,
            "",
            "MISSING KEYWORDS:",
            f"{', '.join(injection_data.get('missing_keywords', []))}",
            "",
            "-" * 80,
            "INSTRUCTIONS DE MODIFICATION",
            "-" * 80,
            ""
        ]
        
        # Optimizations Loop
        opts = injection_data.get("optimizations", [])
        if not opts:
            content.append("Aucune optimisation spécifique détectée.")
        else:
            for i, opt in enumerate(opts, 1):
                section = opt.get('section', 'Section Inconnue')
                original = opt.get('original', '').strip()
                replacement = opt.get('replacement', '').strip()
                reason = opt.get('reason', '')
                
                block = f"""
# {i}. SECTION : {section.upper()}
(Pourquoi : {reason})

🔍 RECHERCHER (CTRL+F) :
{original}

📋 REMPLACER PAR :
{replacement}

--------------------------------------------------------------------------------
"""
                content.append(block)

        content.append("\nAstuce : Utilise CTRL+F dans Canva pour trouver le texte à remplacer rapidement.")

        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("\n".join(content))
        
        return txt_file
