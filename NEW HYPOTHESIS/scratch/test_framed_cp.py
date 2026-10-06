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

raw_scenario = r['final_json']['scenario']
response = flatten_response(r['final_json'])
ctx = extract_contexts(r)[0] # first retrieved chunk (water/medical from floods.pdf)

prompt = c_metric.context_precision_prompt

import asyncio

async def test_comparison():
    # 1. Unframed (raw tweet)
    qac_raw = QAC(question=raw_scenario, context=ctx, answer=response)
    v_raw = await prompt.generate_multiple(data=qac_raw, llm=judge_llm)
    print("--- 1. RAW TWEET AS QUESTION ---")
    print(f"Verdict: {v_raw[0].verdict} | Reason: {v_raw[0].reason}\n")
    
    # 2. Framed query
    framed_query = f"Given the following disaster emergency situation, determine the required relief resources and operational action plan:\n{raw_scenario}"
    qac_framed = QAC(question=framed_query, context=ctx, answer=response)
    v_framed = await prompt.generate_multiple(data=qac_framed, llm=judge_llm)
    print("--- 2. FRAMED DISASTER QUERY AS QUESTION ---")
    print(f"Verdict: {v_framed[0].verdict} | Reason: {v_framed[0].reason}\n")

asyncio.run(test_comparison())
