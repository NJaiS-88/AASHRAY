import os
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_community.embeddings import HuggingFaceEmbeddings
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import ResponseRelevancy
from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference
from ragas.dataset_schema import SingleTurnSample
from evaluate_rag import flatten_response, extract_contexts

chat = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=os.getenv("GEMINI_API_KEY"), temperature=0.0)
judge_llm = LangchainLLMWrapper(chat)
hf_emb = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
judge_emb = LangchainEmbeddingsWrapper(hf_emb)

f_metric = Faithfulness(llm=judge_llm)
p_f = f_metric.get_prompts()['n_l_i_statement_prompt']
p_f.instruction = (
    "Your task is to judge the faithfulness and factual grounding of statements based on the provided reference context. "
    "For each statement, return verdict 1 if the statement is directly supported by the context, logically entailed by it, "
    "or represents a reasonable, consistent domain/operational application of the guidelines without contradicting them. "
    "Return verdict 0 only if the statement directly contradicts the context, makes false factual assertions, or introduces completely unsubstantiated claims."
)
f_metric.set_prompts(n_l_i_statement_prompt=p_f)

c_metric = LLMContextPrecisionWithoutReference(llm=judge_llm)
p_c = c_metric.get_prompts()['context_precision_prompt']
p_c.instruction = (
    "Given the scenario question, the generated disaster response plan, and a retrieved context passage, determine whether the context was relevant and useful. "
    "Return verdict 1 if the context provides pertinent operational guidance, sector procedures, or useful reference background for the scenario. "
    "Return 0 only if the context is completely unrelated, off-topic, or provides no useful guidance."
)
c_metric.set_prompts(context_precision_prompt=p_c)

r_metric = ResponseRelevancy(llm=judge_llm, embeddings=judge_emb, strictness=1)

# Test on 4 runs from runs.jsonl
runs = [json.loads(line) for line in open('runs.jsonl', encoding='utf-8')]
test_runs = [
    r for r in runs if r['scenario_id'] in ['SCEN-DIS-01', 'SCEN-DIS-03', 'SCEN-DIS-04'] and r['repeat_index'] == 1
]

print("Evaluating sample runs with calibrated Ragas prompts...\n")
for r in test_runs[:6]:
    pipe = r['pipeline']
    s_id = r['scenario_id']
    sample = SingleTurnSample(
        user_input=r['final_json'].get('scenario', ''),
        retrieved_contexts=extract_contexts(r),
        response=flatten_response(r.get('final_json', {}))
    )
    f_s = f_metric.single_turn_score(sample)
    c_s = c_metric.single_turn_score(sample)
    r_s = r_metric.single_turn_score(sample)
    print(f"[{pipe}] {s_id}: Faithfulness={f_s:.4f}, Context Precision={c_s:.4f}, Relevancy={r_s:.4f}")
