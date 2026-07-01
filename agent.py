import os
import json
from datetime import datetime
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

SYSTEM_PROMPT = "You are a helpful assistant. You have access to tools to help answer questions."

# ---------- DUMMY TOOL ----------
def get_current_time():
    """Returns the current date and time as a formatted string."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time in the local timezone.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

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
                tools=tools,
                tool_choice="auto",
                temperature=0.7,
                extra_headers={
                    "HTTP-Referer": "http://localhost:8888",
                    "X-Title": "AI Agent",
                }
            )
            
            assistant_message = response.choices[0].message
            messages.append(assistant_message.to_dict())
            if assistant_message.tool_calls:
                print("🔧 Agent is using a tool...")
                
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    if tool_name == "get_current_time":
                        result = get_current_time()
                    else:
                        result = f"Unknown tool: {tool_name}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result)
                    })
                
                second_response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=0.7,
                    extra_headers={
                        "HTTP-Referer": "http://localhost:8888",
                        "X-Title": "AI Agent",
                    }
                )
                final_reply = second_response.choices[0].message.content
                messages.append({"role": "assistant", "content": final_reply})
                print(f"Agent: {final_reply}\n")
            else:
                assistant_reply = assistant_message.content
                print(f"Agent: {assistant_reply}\n")
                
        except Exception as e:
            print(f"Error: {e}. Please check your API key and network.\n")

if __name__ == "__main__":
    chat_loop()