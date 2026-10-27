import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluate_resources import call_jev_decisions

key = os.getenv("OPENROUTER_API_KEY")
print("Key found:", bool(key))
res = call_jev_decisions("Please, we need tents and water. We are in Silo, Thank you!", api_key=key)
print("Success:", res.get("success"))
print("Probabilities:", res.get("probabilities"))
