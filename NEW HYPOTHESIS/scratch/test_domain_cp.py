import os
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from ragas.llms import LangchainLLMWrapper
from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference, QAC, Verification
from evaluate_rag import flatten_response, extract_contexts

chat = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=os.getenv("GEMINI_API_KEY"), temperature=0.0)
judge_llm = LangchainLLMWrapper(chat)
c_metric = LLMContextPrecisionWithoutReference(llm=judge_llm)

p = c_metric.get_prompts()['context_precision_prompt']
p.instruction = (
    "You are evaluating whether a retrieved context passage is useful for addressing an emergency scenario and informing the disaster response plan. "
    "Given the scenario incident (question), the generated response plan (answer), and a retrieved guideline passage (context): "
    "Return verdict as 1 if the context provides relevant operational guidance, sector procedures (e.g. water, medical, shelter, search & rescue), or domain standards that support the actions in the response. "
    "Return verdict as 0 only if the context is completely unrelated, off-topic, or provides no useful guidance for this disaster."
)

p.examples = [
    (
        QAC(
            question="Severe earthquake collapsed buildings in Sector 4, people trapped under debris.",
            context="NDMA Guidelines: Emergency Search and Rescue teams equipped with acoustic sensors and canine units should be mobilized immediately to collapsed structures to locate survivors.",
            answer="Resource: search_and_rescue\n- Mobilize specialized SAR teams with canine units and acoustic sensors to Sector 4."
        ),
        Verification(
            reason="The context provides operational guidelines and equipment protocols for search and rescue during building collapses, which directly informs the response plan.",
            verdict=1
        )
    ),
    (
        QAC(
            question="Flooding in urban districts has contaminated local drinking water wells.",
            context="Management of Urban Flooding: Supply of safe drinking water must be ensured by deploying vehicle-mounted water tankers and distributing chlorine tablets for residual disinfection.",
            answer="Resource: water\n- Dispatch drinking water tankers and distribute chlorine purification tablets to affected areas."
        ),
        Verification(
            reason="The context specifies exact protocols for safe water supply and chlorine tablet disinfection during urban floods, directly supporting the response.",
            verdict=1
        )
    ),
    (
        QAC(
            question="Severe flood inundating residential colonies, people need immediate drinking water.",
            context="National Cyclone Risk Mitigation Project: Construction of saline embankments along coastal zones to prevent tidal surge inundation.",
            answer="Resource: water\n- Deploy potable water tankers and chlorine purification tablets."
        ),
        Verification(
            reason="The context discusses coastal saline embankments for cyclones, which is unrelated to emergency drinking water supply for freshwater flood victims.",
            verdict=0
        )
    )
]
c_metric.set_prompts(context_precision_prompt=p)

runs = [json.loads(line) for line in open('runs.jsonl', encoding='utf-8')]
for scen_id in ['SCEN-DIS-01', 'SCEN-DIS-03', 'SCEN-DIS-05']:
    r = [r for r in runs if r['scenario_id'] == scen_id and r['pipeline'] == 'jev_llm' and r['repeat_index'] == 1][0]
    from ragas.dataset_schema import SingleTurnSample
    sample = SingleTurnSample(
        user_input=r['final_json']['scenario'],
        retrieved_contexts=extract_contexts(r),
        response=flatten_response(r['final_json'])
    )
    score = c_metric.single_turn_score(sample)
    print(f"[{scen_id} - Jev] Context Precision with domain few-shots: {score:.4f}")
