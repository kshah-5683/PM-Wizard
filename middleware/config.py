import os
import litellm

# Model configurations and global settings
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
LIGHTWEIGHT_MODEL = os.getenv("LIGHTWEIGHT_MODEL", "groq/llama-3.1-8b-instant")
CRITIC_MODEL = os.getenv("CRITIC_MODEL", "groq/llama-3.1-8b-instant")

# Embedding Config for RAG
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))  # Must match EMBEDDING_MODEL output

# Project Root for Codebase Inspector
PROJECT_ROOT = os.getenv("PROJECT_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Observability: Set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY
# in .env to enable LangSmith tracing for all LangGraph runs.

# Model Fallback and token guard limits
FALLBACK_PRIMARY_MODEL = os.getenv("FALLBACK_PRIMARY_MODEL", "github/meta-llama-3.3-70b-instruct")
FALLBACK_CRITIC_MODEL = os.getenv("FALLBACK_CRITIC_MODEL", "github/meta-llama-3.1-8b-instruct")
MODEL_MAX_TOKENS = int(os.getenv("MODEL_MAX_TOKENS", "128000"))

# LiteLLM Disk Cache for Development
LLM_CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "false").lower() == "true"
if LLM_CACHE_ENABLED:
    litellm.cache = litellm.Cache(type="disk", disk_cache_dir=".cache/litellm")

