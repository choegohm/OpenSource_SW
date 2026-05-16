# test_llm.py
from services.llm import analyze_intent

result = analyze_intent("PyTorch GPU 환경 만들어줘")
print(result)