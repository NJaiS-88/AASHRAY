import os
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from evaluate_rag import evaluate_ragas_metrics

scenarios_df = pd.read_csv("scenarios.csv")
all_runs = [json.loads(line) for line in open("runs.jsonl", encoding="utf-8")][:5]

print("Running test evaluation of 5 runs...")
res = evaluate_ragas_metrics(all_runs, scenarios_df, output_cache="scratch/test_eval_cache.json")
print("Results preview:")
print(res[["pipeline", "scenario_id", "repeat_index", "faithfulness", "response_relevancy", "context_precision"]])
