import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("Missing OPENROUTER_API_KEY in .env file")

client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "meta-llama/llama-3.1-8b-instruct"

SYSTEM_PROMPT = "You are a helpful, friendly assistant."

def chat_loop():
    print(f"AI Agent started (using {MODEL}). Type 'exit' to quit.\n")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        
        messages.append({"role": "user", "content": user_input})
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.7,
                extra_headers={
                    "HTTP-Referer": "http://localhost:8888",  # Replace with your project URL
                    "X-Title": "AI Agent",
                }
            )
            assistant_reply = response.choices[0].message.content
            messages.append({"role": "assistant", "content": assistant_reply})
            print(f"Agent: {assistant_reply}\n")
            
        except Exception as e:
            print(f"Error: {e}. Please check your API key and network.\n")

if __name__ == "__main__":
    chat_loop()