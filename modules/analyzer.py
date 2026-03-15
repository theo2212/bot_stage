import groq
import cerebras.cloud.sdk
import yaml
import json
import os

from modules.config_loader import load_config

class Analyzer:
    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        
        self.groq_api_key = self.config.get("llm", {}).get("groq_api_key")
        self.cerebras_api_key = self.config.get("llm", {}).get("cerebras_api_key")
        self.model_name = self.config.get("llm", {}).get("model", "llama-3.3-70b-versatile")
        
        self.groq_client = groq.Groq(api_key=self.groq_api_key) if self.groq_api_key else None
        self.cerebras_client = cerebras.cloud.sdk.Cerebras(api_key=self.cerebras_api_key) if self.cerebras_api_key else None

        if not self.groq_api_key and not self.cerebras_api_key:
            print("[Analyzer] CRITICAL: No API Keys found.")

    def analyze_job_match_json(self, cv_text, job_description, anti_patterns=""):
        """
        Analyzes the fit between CV and Job Description.
        Returns a structured JSON dictionary with score, summary, and details.
        """
        anti_patterns_section = ""
        if anti_patterns:
            anti_patterns_section = f"\nUSER DISLIKES (ANTI-PATTERNS):\n{anti_patterns}\nCRITICAL: If the job matches these anti-patterns, drastically lower the match_score (below 30).\n"
            
        prompt = f"""
        Role: Senior Tech Recruiter.
        Task: Analyze the following CV against the Job Description.
        Goal: Provide specific, actionable advice to make the CV a 90%+ match. Provide output in PERFECT JSON format.
        {anti_patterns_section}
        
        JOB DESCRIPTION:
        {job_description[:2000]} (truncated)
        
        CANDIDATE CV:
        {cv_text[:2000]} (truncated)
        
        OUTPUT FORMAT (Respond ONLY with valid JSON):
        {{
            "match_score": <integer 0-100>,
            "short_description": "<Une liste à puces riche et détaillée (5-8 points) résumant les missions exactes et les défis techniques mentionnés dans l'offre. Ne parle absolument pas du candidat ici.>",
            "company_info": "<Un paragraphe élégant et complet présentant l'entreprise, son secteur, sa culture et ses ambitions.>",
            "pros_cons": {{
                "pros": ["point fort 1", "point fort 2"],
                "cons": ["point faible 1", "point faible 2"]
            }},
            "missing_keywords": "<Mots-clés ou compétences critiques manquants.>",
            "improvement_plan": "<Plan d'action précis pour décrocher le poste.>"
        }}
        
        Keep text values in French. Do NOT include markdown blocks like ```json around the response, just the raw JSON text.
        """
        
        # Provider Selection & Fallback
        providers = []
        if self.cerebras_client:
            providers.append(("Cerebras", self.cerebras_client, "llama3.3-70b"))
        if self.groq_client:
            providers.append(("Groq", self.groq_client, self.model_name))
            
        for name, client, model in providers:
            try:
                # print(f"[Analyzer] Trying {name}...")
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content.strip()
                
                try:
                    # 1. Direct parse
                    result = json.loads(content)
                    if isinstance(result, dict):
                        result = {k.lower(): v for k, v in result.items()}
                    return result
                except json.JSONDecodeError:
                    # 2. Try cleaning markdown (fallback)
                    cleaned = content
                    if "```json" in content:
                        cleaned = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        cleaned = content.split("```")[1].split("```")[0].strip()
                    
                    try:
                        result = json.loads(cleaned)
                        if isinstance(result, dict):
                            result = {k.lower(): v for k, v in result.items()}
                        return result
                    except Exception as e2:
                        print(f"[Analyzer] Failed to parse JSON from {name}. Error: {e2}")
                        continue # Try next provider
            except Exception as e:
                print(f"[Analyzer] {name} API Error: {str(e)}")
                continue # Try next provider
                
        print("[Analyzer] CRITICAL: All AI providers failed.")
        return None

    def detect_language(self, text):
        """
        Simple heuristic to detect EN vs FR.
        """
        text = text.lower()
        # Common stop words
        fr_score = sum(1 for w in [" le ", " la ", " et ", " pour ", " avec "] if w in text)
        en_score = sum(1 for w in [" the ", " and ", " for ", " with ", " to "] if w in text)
        
        return "fr" if fr_score >= en_score else "en"

    def generate_cover_letter(self, cv_text, job_description, company_name, job_title, language="fr"):
        """
        Generates a custom cover letter body based on CV and Job Description.
        """
        if language == "fr":
            role_prompt = "Role: Expert Copywriter for Tech Jobs. Write in FRENCH."
            instructions = """
            - Intro: Mention specific excitement about {company_name}.
            - Body 1: Connect candidate's NLP/Data experience (Ecovelo, Projects) to the job requirements.
            - Body 2: Highlight soft skills (autonomy, teamwork) and academic background (ESIEA/Skema).
            - Closing: Call to action for an interview.
            """
        else:
            role_prompt = "Role: Expert Copywriter for Tech Jobs. Write in ENGLISH."
            instructions = """
            - Intro: Mention specific excitement about {company_name}.
            - Body 1: Connect candidate's NLP/Data experience (Ecovelo, Projects) to the job requirements.
            - Body 2: Highlight soft skills (autonomy, teamwork) and academic background (ESIEA/Skema).
            - Closing: Call to action for an interview.
            """

        prompt = f"""
        {role_prompt}
        Task: Write a compelling cover letter for a {job_title} position at {company_name}.
        
        CONTEXT:
        - Candidate CV: {cv_text[:3000]}
        - Job Description: {job_description[:2000]}
        
        INSTRUCTIONS:
        {instructions}
        3. Format: Return a JSON object with keys: 'intro_paragraph', 'body_paragraph_1', 'body_paragraph_2', 'closing_paragraph'.
        
        OUTPUT (JSON ONLY):
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            # If Groq wraps in markdown despite beign asked for JSON only
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return content
        except Exception as e:
            return f"{{\"error\": \"{str(e)}\"}}"

    def tailor_cv(self, cv_text, job_description, language="fr"):
        """
        Scans the ENTIRE CV and generates specific text replacements to optimize for the job.
        """
        if language == "fr":
            lang_instruction = "Write in French."
        else:
            lang_instruction = "Write in English."

        prompt = f"""
        Role: Expert Resume Strategist.
        Task: Analyze the user's Canva CV and provide a comprehensive list of textual changes to optimize it for the specific job. {lang_instruction}
        
        JOB DESCRIPTION:
        {job_description[:2500]}
        
        CANDIDATE CV TEXT:
        {cv_text[:3000]}
        
        INSTRUCTIONS:
        1. Scan EVERY section (Summary, Experience, Projects, Skills, Education).
        2. Identify parts that are "weak" or "generic" relative to the Job Description.
        3. Create specific "Search & Replace" instructions.
           - "Original": A UNIQUE, EXACT substring from the CV text. It must be copy-pasteable for Ctrl+F. Do not paraphrase.
           - "Replacement": The rewritten version (punchier, keywords included, KPI-focused).
           - "Reason": Brief explanation.
        4. Focus on:
           - Matching keywords (ATS).
           - Quantifying impact (numbers).
           - Aligning soft skills.
        
        OUTPUT FORMAT (JSON ONLY):
        {{
            "optimizations": [
                {{
                    "section": "Summary",
                    "original": "Je recherche un stage de 6 mois...",
                    "replacement": "Élève-ingénieur Data/IA (ESIEA/SKEMA) recherchant...",
                    "reason": "More specific hook."
                }},
                {{
                    "section": "Experience - Ecovelo",
                    "original": "Analyse de données...",
                    "replacement": "Analyse de données Python/Pandas réduisant le temps de diagnostic de 66%...",
                    "reason": "Added keywords and metric."
                }},
                ... (Add as many as needed)
            ],
            "missing_keywords": ["Keyword1", "Keyword2"]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            # Clean up Markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            if isinstance(result, dict):
                result = {k.lower(): v for k, v in result.items()}
            return result
        except Exception as e:
            print(f"Error generating CV blocks: {str(e)}")
            return {"optimizations": [], "missing_keywords": ["Error generating data"]}

    def analyze_rejections(self, rejected_jobs):
        """
        Analyzes a list of rejected jobs (title and company) to find common anti-patterns.
        """
        if not rejected_jobs:
            return ""
            
        jobs_text = "\n".join([f"- {j['title']} at {j['company']}" for j in rejected_jobs])
        
        prompt = f"""
        Role: Career Strategist.
        Task: The user has actively rejected the following list of job applications.
        Goal: Analyze this list and identify 2-3 short, clear anti-patterns (e.g. "Do not show consulting companies", "Do not show generic data analyst roles", etc.) that explain why the user disliked them.
        
        REJECTED JOBS:
        {jobs_text}
        
        OUTPUT FORMAT:
        Return ONLY a bulleted list of the identified anti-patterns. Keep it extremely concise.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error analyzing rejections: {e}")
            return ""

    def analyze_email_response(self, email_subject, email_body, company_name):
        """
        Reads an email and determines if it is a confirmation of application, 
        a rejection, or an interview request.
        Returns one of: "IGNORE", "POSTULE", "REFUS", "ENTRETIEN"
        """
        prompt = f"""
        Role: Recruitment Assistant.
        Task: Analyze the following email received from {company_name}.
        Goal: Classify the true intent of this email regarding a job application.
        
        EMAIL SUBJECT: {email_subject}
        EMAIL BODY:
        {email_body[:2000]}
        
        RULES:
        1. **PRIORITIZE THE SUBJECT**: Automated recruitment emails often have clear subjects like "Candidature reçue", "Confirmation", or "Your application". If the subject is definitive, follow its lead.
        2. "POSTULE" (Confirmation): If the email confirms an application was successfully received.
        3. "REFUS" (Rejection): Any decline, even polite/vague ones. Keywords: "Malheureusement", "Not moving forward", "Decided to pass", "Other candidates".
        4. "ENTRETIEN" (Interview/Test): Any request for a meeting or technical test.
        5. "IGNORE" (Unrelated): LinkedIn Job Alerts, generic invitations to apply, or marketing.
        
        CRITICAL: If it's just a LinkedIn job alert or an invite to apply for a *new* job, return "IGNORE".
        
        OUTPUT FORMAT:
        Return ONLY the single EXACT keyword ("POSTULE", "REFUS", "ENTRETIEN", or "IGNORE"). Absolutely no other text.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            result = response.choices[0].message.content.strip().upper()
            
            # Clean up the output just in case the LLM was chatty
            if "ENTRETIEN" in result: return "ENTRETIEN"
            if "REFUS" in result: return "REFUS"
            if "POSTULE" in result: return "POSTULE"
            return "IGNORE"
            
        except Exception as e:
            print(f"Error analyzing email: {e}")
            return "IGNORE"

    def analyze_unknown_email(self, email_subject, email_body):
        """
        Analyzes an email to determine if it is a job response.
        If it is, extracts the company name, status, and job title.
        Returns a JSON object.
        """
        prompt = f"""
        Role: Recruitment Extraction Assistant.
        Task: Analyze the following email to see if it's a direct response to a job application (Confirmation, Rejection, or Interview).
        
        EMAIL SUBJECT: {email_subject}
        EMAIL BODY:
        {email_body[:2000]}
        
        RULES:
        1. If it's a generic newsletter, LinkedIn job alert, or marketing email, it's NOT a job response.
        2. Status must be exactly one of: "POSTULE" (application received/confirmed), "REFUS" (rejected/not moving forward), or "ENTRETIEN" (interview requested/technical test).
        3. Extract the name of the company that sent the email.
        4. Extract the job title if mentioned, otherwise leave it empty.
        
        OUTPUT FORMAT (JSON ONLY):
        {{
            "is_job_response": true/false,
            "company_name": "Name of Company",
            "status": "POSTULE/REFUS/ENTRETIEN",
            "job_title": "Title of the job"
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(content)
            if isinstance(result, dict):
                result = {k.lower(): v for k, v in result.items()}
            return result
        except Exception as e:
            print(f"Error extracting unknown email: {e}")
            return {"is_job_response": False}

    def generate_interview_reply_draft(self, company_name, email_body, user_name="Théo Consigny"):
        """
        Generates a professional French response to an interview request.
        """
        prompt = f"""
        Rôle: Candidat motivé répondant à une offre d'entretien.
        Tâche: Rédiger une réponse à l'email suivant de {company_name} me proposant un entretien ou un test technique.
        
        SENDER'S EMAIL BODY:
        {email_body[:3000]}
        
        CONSIGNES :
        1. Rédige l'email en Français. Format formel mais moderne.
        2. Remercie d'abord l'entreprise pour cette opportunité.
        3. Confirme ton fort intérêt pour le poste.
        4. Pour la disponibilité, propose une phrase générique indiquant que tu es très flexible et de proposer des créneaux, ou utilise des variables type "[Insérer mes disponibilités ici]".
        5. Signe l'email avec le nom : {user_name}
        6. NE mets PAS de bloc d'objet (Subject), génère uniquement le CORPS de l'email texte.
        7. NE retourne AUCUN blabla (pas de "Voici l'email:"). UNIQUEMENT le texte de l'email.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating draft: {e}")
            return f"Bonjour,\n\nMerci beaucoup pour ce retour positif. Je vous confirme mon fort intérêt pour le poste.\nJe reste à votre disposition pour convenir d'un rendez-vous.\n\nBien à vous,\n{user_name}"


