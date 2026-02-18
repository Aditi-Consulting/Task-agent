import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_CLASSIFY = "gpt-4o-mini"
OPENAI_MODEL_AGENT = "gpt-4o-mini"

# MySQL
# DB_HOST = os.getenv("MYSQL_HOST", "localhost")
# DB_USER = os.getenv("MYSQL_USER", "root")
# DB_PASS = os.getenv("MYSQL_PASS", "root")
# DB_NAME = os.getenv("MYSQL_DB", "alert_system")
# Docker MySQL
DB_HOST = os.getenv("DB_HOST", "mysql_container")
DB_USER = os.getenv("DB_USER", "alert_user")
DB_PASS = os.getenv("DB_PASSWORD", "alert_pass")
DB_NAME = os.getenv("DB_NAME", "alert_system")

if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY environment variable.")
