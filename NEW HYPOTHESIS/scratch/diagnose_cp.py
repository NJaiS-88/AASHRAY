import os
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from ragas.llms import LangchainLLMWrapper
from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference
from ragas.dataset_schema import SingleTurnSample
from evaluate_rag import flatten_response, extract_contexts

chat = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=os.getenv("GEMINI_API_KEY"), temperature=0.0)
judge_llm = LangchainLLMWrapper(chat)

c_metric = LLMContextPrecisionWithoutReference(llm=judge_llm)

runs = [json.loads(line) for line in open('runs.jsonl', encoding='utf-8')]
r = [r for r in runs if r['scenario_id'] == 'SCEN-DIS-01' and r['pipeline'] == 'llm_llm' and r['repeat_index'] == 1][0]

sample = SingleTurnSample(
    user_input=r['final_json']['scenario'],
    retrieved_contexts=extract_contexts(r),
    response=flatten_response(r['final_json'])
)

print("USER INPUT:", sample.user_input[:200])
print("\nRESPONSE:", sample.response[:200])
print(f"\nNUM CONTEXTS: {len(sample.retrieved_contexts)}")
for i, c in enumerate(sample.retrieved_contexts):
    print(f"\n--- CONTEXT {i+1} ({len(c)} chars) ---")
    print(c[:250])

print("\n--- RUNNING CONTEXT PRECISION SCORING ---")
# Let's inspect the internal calls or score
score = c_metric.single_turn_score(sample)
print(f"Context Precision Score: {score}")
