import json
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def analyze_intent(user_input: str) -> dict:
    
    with open("prompt/system.txt", "r", encoding="utf-8") as f:
        system = f.read()
    with open("prompt/few_shot.json", "r", encoding="utf-8") as f:
        examples = json.load(f)
    
    example_text = ""
    for ex in examples:
        example_text += f"입력: {ex['input']}\n출력: {ex['output']}\n\n"
    
    prompt = f"{system}\n\n{example_text}입력: {user_input}\n출력:"
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    
    raw = response.text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    return json.loads(raw)