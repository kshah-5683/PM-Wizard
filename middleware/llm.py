import os
from litellm import completion, acompletion
from middleware.config import (
    PRIMARY_MODEL,
    CRITIC_MODEL,
    FALLBACK_PRIMARY_MODEL,
    FALLBACK_CRITIC_MODEL
)

FALLBACK_MODELS = {
    PRIMARY_MODEL: FALLBACK_PRIMARY_MODEL,
    CRITIC_MODEL: FALLBACK_CRITIC_MODEL
}

def resilient_completion(model: str, **kwargs):
    """
    Synchronous LiteLLM wrapper with fallback support and cost logging.
    """
    try:
        response = completion(model=model, **kwargs)
        # Log cost
        try:
            cost = response._hidden_params.get("response_cost", 0)
            print(f"[LLM Cost] {model}: ${cost:.6f}")
        except Exception:
            pass
        return response
    except Exception as e:
        fallback = FALLBACK_MODELS.get(model)
        if fallback:
            print(f"[LLM Fallback] {model} failed ({e}). Retrying with {fallback}...")
            fallback_response = completion(model=fallback, **kwargs)
            try:
                cost = fallback_response._hidden_params.get("response_cost", 0)
                print(f"[LLM Cost] {fallback}: ${cost:.6f}")
            except Exception:
                pass
            return fallback_response
        raise

async def aresilient_completion(model: str, **kwargs):
    """
    Asynchronous LiteLLM wrapper with fallback support and cost logging.
    """
    try:
        response = await acompletion(model=model, **kwargs)
        # Log cost
        try:
            cost = response._hidden_params.get("response_cost", 0)
            print(f"[LLM Cost] {model}: ${cost:.6f}")
        except Exception:
            pass
        return response
    except Exception as e:
        fallback = FALLBACK_MODELS.get(model)
        if fallback:
            print(f"[LLM Fallback] {model} failed ({e}). Retrying with {fallback}...")
            fallback_response = await acompletion(model=fallback, **kwargs)
            try:
                cost = fallback_response._hidden_params.get("response_cost", 0)
                print(f"[LLM Cost] {fallback}: ${cost:.6f}")
            except Exception:
                pass
            return fallback_response
        raise
