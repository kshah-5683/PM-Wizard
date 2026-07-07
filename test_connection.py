import os
from dotenv import load_dotenv
from litellm import completion
from middleware.config import PRIMARY_MODEL, LIGHTWEIGHT_MODEL

# Load environment variables
load_dotenv()

def test_llm_connections():
    print("==================================================")
    print("Testing LiteLLM Router Connections to Groq")
    print("==================================================")
    
    print(f"Testing Primary Model ({PRIMARY_MODEL})...")
    try:
        response = completion(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": "Respond with exactly: 'Hello, Primary Model is working!'"}]
        )
        print(f"[OK] Primary Model Success: {response.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"[ERROR] Primary Model Failed: {e}")

    print("-" * 50)

    print(f"Testing Lightweight Model ({LIGHTWEIGHT_MODEL})...")
    try:
        response = completion(
            model=LIGHTWEIGHT_MODEL,
            messages=[{"role": "user", "content": "Respond with exactly: 'Hello, Lightweight Model is working!'"}]
        )
        print(f"[OK] Lightweight Model Success: {response.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"[ERROR] Lightweight Model Failed: {e}")

if __name__ == "__main__":
    test_llm_connections()
