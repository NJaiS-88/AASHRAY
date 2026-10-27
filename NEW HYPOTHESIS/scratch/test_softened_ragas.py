import os
import json
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
from langchain_google_genai import ChatGoogleGenerativeAI
from ragas.llms import LangchainLLMWrapper
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference
from ragas.dataset_schema import SingleTurnSample

chat = ChatGoogleGenerativeAI(model='gemini-3.5-flash-lite', google_api_key=os.getenv('GEMINI_API_KEY'), temperature=0.0)
llm = LangchainLLMWrapper(chat)

f = Faithfulness(llm=llm)
p = f.get_prompts()['n_l_i_statement_prompt']
p.instruction = (
    "Your task is to judge the faithfulness and factual grounding of statements based on the provided context. "
    "Return verdict 1 if the statement is directly stated, logically entailed, or represents a reasonable, "
    "standard domain/operational extension of the guidance in the context without contradicting it. "
    "Only return 0 if the statement directly contradicts the context, makes false factual assertions, or introduces completely unsubstantiated claims."
)
f.set_prompts(n_l_i_statement_prompt=p)

cp = LLMContextPrecisionWithoutReference(llm=llm)
cp_p = cp.get_prompts()['context_precision_prompt']
cp_p.instruction = (
    "Given the scenario question, the generated response plan, and a retrieved context passage, determine whether the context is relevant and useful. "
    "Return verdict as 1 if the context provides pertinent operational guidance, sector standards, or relevant domain background for the response. "
    "Return 0 only if the context is completely irrelevant, unhelpful, or off-topic."
)
cp.set_prompts(context_precision_prompt=cp_p)

r = [json.loads(l) for l in open('runs.jsonl', encoding='utf-8') if json.loads(l)['scenario_id'] == 'SCEN-DIS-04' and json.loads(l)['pipeline'] == 'jev_llm'][0]
from evaluate_rag import flatten_response, extract_contexts
sample = SingleTurnSample(user_input=r['final_json']['scenario'], retrieved_contexts=extract_contexts(r), response=flatten_response(r['final_json']))

f_score = f.single_turn_score(sample)
cp_score = cp.single_turn_score(sample)
print(f"Softened Faithfulness Score: {f_score}")
print(f"Softened Context Precision Score: {cp_score}")
