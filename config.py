import os
from pathlib import Path
from dotenv import load_dotenv

# Find the root .env file and load it
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Retrieve variables
API_KEY = os.getenv("API_KEY")
VOICE_DEFAULT = os.getenv("VOICE_DEFAULT", "default")

# Validate critical configurations
if not API_KEY or not API_KEY.strip():
    raise RuntimeError(
        "Critical Error: 'API_KEY' environment variable is not defined or is empty in the .env file. "
        "Please check your .env configuration."
    )
