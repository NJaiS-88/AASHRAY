import os
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from ragas.llms import LangchainLLMWrapper
from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference, QAC
from evaluate_rag import flatten_response, extract_contexts

chat = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=os.getenv("GEMINI_API_KEY"), temperature=0.0)
judge_llm = LangchainLLMWrapper(chat)
c_metric = LLMContextPrecisionWithoutReference(llm=judge_llm)

runs = [json.loads(line) for line in open('runs.jsonl', encoding='utf-8')]
r = [r for r in runs if r['scenario_id'] == 'SCEN-DIS-01' and r['pipeline'] == 'jev_llm' and r['repeat_index'] == 1][0]

user_input = r['final_json']['scenario']
response = flatten_response(r['final_json'])
contexts = extract_contexts(r)

print(f"Scenario: {user_input[:100]}...\n")
prompt = c_metric.context_precision_prompt

import asyncio

async def test_verdicts():
    for i, ctx in enumerate(contexts[:3]):
        qac = QAC(question=user_input, context=ctx, answer=response)
        verdicts = await prompt.generate_multiple(data=qac, llm=judge_llm)
        print(f"--- Chunk {i+1} ---")
        for v in verdicts:
            print(f"Verdict: {v.verdict} | Reason: {v.reason}")

asyncio.run(test_verdicts())
