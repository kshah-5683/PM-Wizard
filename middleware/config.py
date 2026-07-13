import os

# Model configurations and global settings
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
LIGHTWEIGHT_MODEL = os.getenv("LIGHTWEIGHT_MODEL", "groq/llama-3.1-8b-instant")
CRITIC_MODEL = os.getenv("CRITIC_MODEL", "groq/llama-3.1-8b-instant")
