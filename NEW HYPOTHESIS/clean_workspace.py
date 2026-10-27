import os
import glob

files_to_remove = [
    'runs.jsonl',
    'predictions_cache.json',
    'llm + llm/runs.jsonl',
    'jev + llm/runs.jsonl',
    'results/stage1_checkpoint.json',
    'results/ragas_eval_cache.json',
    'results/deterministic_metrics.csv',
    'results/deterministic_summary.csv',
    'results/paired_stats.csv',
    'results/paired_stats_deterministic.csv',
    'results/operational.csv',
    'results/ragas_scores.csv',
    'results/report.md',
    'results/rag_evaluation_report.pdf'
] + glob.glob('results/*')

removed = []
for f in files_to_remove:
    if os.path.exists(f):
        os.remove(f)
        removed.append(f)

print(f"Successfully cleaned {len(removed)} old artifacts/checkpoints:")
for r in removed:
    print(f"  - {r}")
