import os
import yaml

def load_config(config_path="config.yaml"):
    """
    Loads configuration from config.yaml or from Environment Variables.
    Prioritizes the file if it exists.
    """
    config = {}
    
    # 1. Try loading from file
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Config] Error reading {config_path}: {e}")

    # 2. Fallback / Merge with Environment Variables
    # Format: SECTION_KEY (e.g., LLM_GROQ_API_KEY)
    
    # LLM
    if "llm" not in config: config["llm"] = {}
    config["llm"]["groq_api_key"] = os.environ.get("GROQ_API_KEY", config["llm"].get("groq_api_key"))
    config["llm"]["model"] = os.environ.get("LLM_MODEL", config["llm"].get("model", "llama-3.3-70b-versatile"))
    
    # Postgres
    if "postgres" not in config: config["postgres"] = {}
    config["postgres"]["direct_url"] = os.environ.get("DIRECT_URL", config["postgres"].get("direct_url"))
    
    # Notion
    if "notion" not in config: config["notion"] = {}
    config["notion"]["token"] = os.environ.get("NOTION_TOKEN", config["notion"].get("token"))
    config["notion"]["database_id"] = os.environ.get("NOTION_DATABASE_ID", config["notion"].get("database_id"))
    
    # Email
    if "email" not in config: config["email"] = {}
    config["email"]["address"] = os.environ.get("EMAIL_ADDRESS", config["email"].get("address"))
    config["email"]["app_password"] = os.environ.get("EMAIL_PASSWORD", config["email"].get("app_password"))
    
    # Discord
    if "discord" not in config: config["discord"] = {}
    config["discord"]["webhook_url"] = os.environ.get("DISCORD_WEBHOOK_URL", config["discord"].get("webhook_url"))
    
    return config
