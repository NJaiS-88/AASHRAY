import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Set style
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.sans-serif'] = 'Arial'
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['figure.dpi'] = 300

os.makedirs('results', exist_ok=True)

# Load deterministic metrics
df_det = pd.read_csv('results/deterministic_metrics.csv')
runs = [json.loads(l) for l in open('runs.jsonl', encoding='utf-8') if l.strip()]

# -------------------------------------------------------------
# CHART 1: DETERMINISTIC QUALITY METRICS COMPARISON
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 6))

metrics = ['Gold Coverage', 'Citation Validity', 'JSON Validity', 'Evidence Sufficiency']
jev_vals = [
    df_det[df_det['pipeline'] == 'jev_llm']['gold_resource_coverage'].mean() * 100,
    df_det[df_det['pipeline'] == 'jev_llm']['citation_validity'].mean() * 100,
    df_det[df_det['pipeline'] == 'jev_llm']['json_validity'].mean() * 100,
    df_det[df_det['pipeline'] == 'jev_llm']['evidence_sufficient_share'].mean() * 100,
]
llm_vals = [
    df_det[df_det['pipeline'] == 'llm_llm']['gold_resource_coverage'].mean() * 100,
    df_det[df_det['pipeline'] == 'llm_llm']['citation_validity'].mean() * 100,
    df_det[df_det['pipeline'] == 'llm_llm']['json_validity'].mean() * 100,
    df_det[df_det['pipeline'] == 'llm_llm']['evidence_sufficient_share'].mean() * 100,
]
ctrl_vals = [
    df_det[df_det['pipeline'] == 'llm_llm_control']['gold_resource_coverage'].mean() * 100,
    df_det[df_det['pipeline'] == 'llm_llm_control']['citation_validity'].mean() * 100,
    df_det[df_det['pipeline'] == 'llm_llm_control']['json_validity'].mean() * 100,
    df_det[df_det['pipeline'] == 'llm_llm_control']['evidence_sufficient_share'].mean() * 100,
]

x = np.arange(len(metrics))
width = 0.35

rects1 = ax.bar(x - width/2, jev_vals, width, label='Pipeline B (Jev + LLM)', color='#10b981', edgecolor='#059669', linewidth=1.2)
rects2 = ax.bar(x + width/2, llm_vals, width, label='Pipeline A (LLM + LLM)', color='#3b82f6', edgecolor='#1d4ed8', linewidth=1.2)

ax.set_ylabel('Score (%)', fontsize=12, fontweight='bold')
ax.set_title('Evaluation Metrics Comparison Across Benchmark Runs', fontsize=14, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(metrics, fontsize=11, fontweight='bold')
ax.set_ylim(0, 115)
ax.legend(frameon=True, facecolor='#f8fafc', edgecolor='#cbd5e1', fontsize=10)

def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold')

autolabel(rects1)
autolabel(rects2)

plt.tight_layout()
chart1_path = 'results/chart1_deterministic_metrics.png'
plt.savefig(chart1_path, dpi=300)
plt.close()
print(f"Saved {chart1_path}")

# -------------------------------------------------------------
# CHART 2: LATENCY & NORMALIZED EFFICIENCY COMPARISON
# -------------------------------------------------------------
lat_data = []
for r in runs:
    pipe = r['pipeline']
    lat = r['latency']
    tok = r['tokens']
    num_res = len(r.get('final_json', {}).get('resources', []))
    gen_comp = tok['generation']['completion_tokens']
    
    lat_data.append({
        'pipeline': pipe,
        'Stage 1 (Classification)': lat['classification_ms'],
        'Retrieval': lat['retrieval_ms'],
        'Stage 2 (Generation)': lat['generation_ms'],
        'End-to-End Total': lat['total_ms'],
        'num_resources': num_res,
        'completion_tokens': gen_comp,
        'stage2_per_resource': lat['generation_ms'] / max(num_res, 1) if num_res > 0 else np.nan,
        'total_per_resource': lat['total_ms'] / max(num_res, 1) if num_res > 0 else np.nan
    })

df_lat = pd.DataFrame(lat_data)

fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5.2))

# Subplot 1: Raw Latency (p50)
stages = ['Stage 1\n(Classification)', 'Stage 2\n(Generation)', 'End-to-End\nTotal']
jev_p50 = [
    np.percentile(df_lat[df_lat['pipeline'] == 'jev_llm']['Stage 1 (Classification)'], 50),
    np.percentile(df_lat[df_lat['pipeline'] == 'jev_llm']['Stage 2 (Generation)'], 50),
    np.percentile(df_lat[df_lat['pipeline'] == 'jev_llm']['End-to-End Total'], 50)
]
llm_p50 = [
    np.percentile(df_lat[df_lat['pipeline'] == 'llm_llm']['Stage 1 (Classification)'], 50),
    np.percentile(df_lat[df_lat['pipeline'] == 'llm_llm']['Stage 2 (Generation)'], 50),
    np.percentile(df_lat[df_lat['pipeline'] == 'llm_llm']['End-to-End Total'], 50)
]

x1 = np.arange(len(stages))
w1 = 0.35
r1 = ax1.bar(x1 - w1/2, jev_p50, w1, label='Pipeline B (Jev + LLM)', color='#10b981', edgecolor='#059669')
r2 = ax1.bar(x1 + w1/2, llm_p50, w1, label='Pipeline A (LLM + LLM)', color='#3b82f6', edgecolor='#1d4ed8')

ax1.set_ylabel('Median Latency (ms)', fontsize=11, fontweight='bold')
ax1.set_title('A. Nominal Latency by Stage', fontsize=12, fontweight='bold', pad=12)
ax1.set_xticks(x1)
ax1.set_xticklabels(stages, fontsize=10, fontweight='bold')
ax1.legend(frameon=True, facecolor='#f8fafc', edgecolor='#cbd5e1', fontsize=9)

for rect in r1:
    h = rect.get_height()
    ax1.annotate(f'{h:.0f} ms', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                 textcoords="offset points", ha='center', va='bottom', fontsize=8.5, fontweight='bold')
for rect in r2:
    h = rect.get_height()
    ax1.annotate(f'{h:.0f} ms', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                 textcoords="offset points", ha='center', va='bottom', fontsize=8.5, fontweight='bold')

# Subplot 2: Normalized Stage 2 Latency per Dispatched Resource
pipes = ['jev_llm', 'llm_llm']
labels = ['Pipeline B\n(Jev + LLM)', 'Pipeline A\n(LLM + LLM)']
colors = ['#10b981', '#3b82f6']

s2_per_res = [
    df_lat[df_lat['pipeline'] == p]['stage2_per_resource'].dropna().mean() for p in pipes
]

bars2 = ax2.bar(labels, s2_per_res, color=colors, edgecolor='#334155', width=0.45)
ax2.set_ylabel('Stage 2 Latency / Resource (ms)', fontsize=11, fontweight='bold')
ax2.set_title('B. Normalized Stage 2 Latency\n(per Dispatched Resource)', fontsize=12, fontweight='bold', pad=12)
ax2.set_ylim(0, max(s2_per_res) * 1.3)

for rect in bars2:
    h = rect.get_height()
    ratio = h / s2_per_res[0]
    subtext = " (1.0x Ref)" if ratio == 1.0 else f" ({ratio:.1f}x slower)"
    ax2.annotate(f'{h:.0f} ms\n{subtext}', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                 textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')

# Subplot 3: End-to-End Latency per Dispatched Resource
tot_per_res = [
    df_lat[df_lat['pipeline'] == p]['total_per_resource'].dropna().mean() for p in pipes
]

bars3 = ax3.bar(labels, tot_per_res, color=colors, edgecolor='#334155', width=0.45)
ax3.set_ylabel('Total End-to-End Latency / Resource (ms)', fontsize=11, fontweight='bold')
ax3.set_title('C. Effective End-to-End Latency\n(per Dispatched Resource)', fontsize=12, fontweight='bold', pad=12)
ax3.set_ylim(0, max(tot_per_res) * 1.3)

for rect in bars3:
    h = rect.get_height()
    ratio = h / tot_per_res[0]
    subtext = " (1.0x Ref)" if ratio == 1.0 else f" ({ratio:.1f}x slower)"
    ax3.annotate(f'{h:.0f} ms\n{subtext}', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                 textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')

plt.tight_layout()
chart2_path = 'results/chart2_latency_comparison.png'
plt.savefig(chart2_path, dpi=300)
plt.close()
print(f"Saved {chart2_path}")

# -------------------------------------------------------------
# CHART 3: PER-SCENARIO GOLD COVERAGE COMPARISON
# -------------------------------------------------------------
scen_grp = df_det.groupby(['scenario_id', 'pipeline'])['gold_resource_coverage'].mean().unstack()
scen_grp = scen_grp.sort_values(by='jev_llm', ascending=False)

fig, ax3 = plt.subplots(figsize=(14, 6))
ind = np.arange(len(scen_grp))
w3 = 0.38

ax3.bar(ind - w3/2, scen_grp['jev_llm'] * 100, w3, label='Pipeline B (Jev + LLM)', color='#10b981', alpha=0.9)
ax3.bar(ind + w3/2, scen_grp['llm_llm'] * 100, w3, label='Pipeline A (LLM + LLM)', color='#3b82f6', alpha=0.9)

ax3.set_ylabel('Gold Resource Coverage (%)', fontsize=12, fontweight='bold')
jev_mean = scen_grp['jev_llm'].mean() * 100 if 'jev_llm' in scen_grp else 0.0
llm_mean = scen_grp['llm_llm'].mean() * 100 if 'llm_llm' in scen_grp else 0.0
ax3.set_title(f'Per-Scenario Gold Resource Coverage: Jev ({jev_mean:.1f}% avg) vs LLM ({llm_mean:.1f}% avg)', fontsize=14, fontweight='bold', pad=12)
ax3.set_xticks(ind)
ax3.set_xticklabels(scen_grp.index, rotation=70, ha='right', fontsize=8)
ax3.set_ylim(0, 115)
ax3.legend(frameon=True, facecolor='#f8fafc', edgecolor='#cbd5e1', fontsize=11)

plt.tight_layout()
chart3_path = 'results/chart3_gold_coverage_distribution.png'
plt.savefig(chart3_path, dpi=300)
plt.close()
print(f"Saved {chart3_path}")

# -------------------------------------------------------------
# CHART 4: COST & TOKEN PROFILE PER 1,000 SCENARIOS
# -------------------------------------------------------------
# Pricing: Jev $0.04/1M prompt, LLM $0.15/1M prompt + $0.75/1M completion
# Stage 2: $0.15/1M prompt + $0.75/1M completion
costs = []
for r in runs:
    pipe = r['pipeline']
    tok = r['tokens']
    if pipe == 'jev_llm':
        c_stage1 = (tok['classification']['prompt_tokens'] / 1e6) * 0.04
        c_stage2 = (tok['generation']['prompt_tokens'] / 1e6) * 0.15 + (tok['generation']['completion_tokens'] / 1e6) * 0.75
    else:
        c_stage1 = (tok['classification']['prompt_tokens'] / 1e6) * 0.15 + (tok['classification']['completion_tokens'] / 1e6) * 0.75
        c_stage2 = (tok['generation']['prompt_tokens'] / 1e6) * 0.15 + (tok['generation']['completion_tokens'] / 1e6) * 0.75
    costs.append({
        'pipeline': pipe,
        'cost_usd_1k': (c_stage1 + c_stage2) * 1000
    })
df_cost = pd.DataFrame(costs)

fig, (ax4_1, ax4_2) = plt.subplots(1, 2, figsize=(13, 5))

c_summary = df_cost.groupby('pipeline')['cost_usd_1k'].mean()
pipes = ['jev_llm', 'llm_llm']
labels = ['Pipeline B\n(Jev + LLM)', 'Pipeline A\n(LLM + LLM)']
cost_vals = [c_summary.get(p, 0.0) for p in pipes]
colors = ['#10b981', '#3b82f6']

# Subplot 1: Raw Scenario Cost
bars4_1 = ax4_1.bar(labels, cost_vals, color=colors, edgecolor='#334155', width=0.45)
ax4_1.set_ylabel('Total Cost per 1,000 Scenarios (USD)', fontsize=11, fontweight='bold')
ax4_1.set_title('A. Nominal Cost per 1k Invocations', fontsize=12, fontweight='bold', pad=12)
ax4_1.set_ylim(0, max(cost_vals) * 1.3)

for rect in bars4_1:
    h = rect.get_height()
    ax4_1.annotate(f'${h:.3f}', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 4),
                   textcoords="offset points", ha='center', va='bottom', fontsize=10, fontweight='bold')

# Subplot 2: Effective Cost per Dispatched Resource
# Average resources dispatched: Jev = 1.381, LLM = 0.286
res_avg = {
    'jev_llm': 1.38095,
    'llm_llm': 0.28571
}
cost_per_res = [cost_vals[i] / res_avg[p] for i, p in enumerate(pipes)]

bars4_2 = ax4_2.bar(labels, cost_per_res, color=colors, edgecolor='#334155', width=0.45)
ax4_2.set_ylabel('Cost per 1,000 Resources Dispatched (USD)', fontsize=11, fontweight='bold')
ax4_2.set_title('B. Cost per 1,000 Resources Successfully Dispatched', fontsize=12, fontweight='bold', pad=12)
ax4_2.set_ylim(0, max(cost_per_res) * 1.25)

for rect in bars4_2:
    h = rect.get_height()
    ax4_2.annotate(f'${h:.3f}\n({h/cost_per_res[0]:.1f}x higher)', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 4),
                   textcoords="offset points", ha='center', va='bottom', fontsize=9.5, fontweight='bold')

plt.tight_layout()
chart4_path = 'results/chart4_cost_and_tokens.png'
plt.savefig(chart4_path, dpi=300)
plt.close()
print(f"Saved {chart4_path}")

# -------------------------------------------------------------
# CHART 5: RAGAS QUALITY METRICS COMPARISON
# -------------------------------------------------------------
ragas_csv = 'results/ragas_scores.csv'
cache_file = 'results/ragas_eval_cache.json'

records = []
if os.path.exists(ragas_csv):
    df_ragas = pd.read_csv(ragas_csv)
elif os.path.exists(cache_file):
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        for k, v in cache.items():
            parts = k.split('___')
            if len(parts) >= 3:
                pipe, s_id = parts[0], parts[1]
                records.append({
                    'pipeline': pipe,
                    'scenario_id': s_id,
                    'faithfulness': v.get('faithfulness', np.nan),
                    'response_relevancy': v.get('response_relevancy', v.get('answer_relevancy', np.nan)),
                    'context_precision': v.get('context_precision', v.get('llm_context_precision_without_reference', np.nan))
                })
        df_ragas = pd.DataFrame(records)
    except Exception:
        df_ragas = pd.DataFrame()
else:
    df_ragas = pd.DataFrame()

if not df_ragas.empty and 'pipeline' in df_ragas.columns:
    summary_r = df_ragas.groupby('pipeline')[['faithfulness', 'response_relevancy', 'context_precision']].mean()
    
    fig, ax5 = plt.subplots(figsize=(10, 5.8))
    metrics_r = ['Faithfulness', 'Response Relevancy', 'Context Precision']
    cols_r = ['faithfulness', 'response_relevancy', 'context_precision']
    
    jev_r = [summary_r.loc['jev_llm', c] * 100 if 'jev_llm' in summary_r.index else 0.0 for c in cols_r]
    llm_r = [summary_r.loc['llm_llm', c] * 100 if 'llm_llm' in summary_r.index else 0.0 for c in cols_r]
    
    x_r = np.arange(len(metrics_r))
    width_r = 0.35
    
    r1 = ax5.bar(x_r - width_r/2, jev_r, width_r, label='Pipeline B (Jev + LLM)', color='#10b981', edgecolor='#059669', linewidth=1.2)
    r2 = ax5.bar(x_r + width_r/2, llm_r, width_r, label='Pipeline A (LLM + LLM)', color='#3b82f6', edgecolor='#1d4ed8', linewidth=1.2)
    
    ax5.set_ylabel('Score (%)', fontsize=12, fontweight='bold')
    ax5.set_title('RAGAS Semantic Quality Metrics Comparison', fontsize=14, fontweight='bold', pad=15)
    ax5.set_xticks(x_r)
    ax5.set_xticklabels(metrics_r, fontsize=11, fontweight='bold')
    ax5.set_ylim(0, 115)
    ax5.legend(frameon=True, facecolor='#f8fafc', edgecolor='#cbd5e1', fontsize=10)
    
    for rects_set in [r1, r2]:
        for rect in rects_set:
            h = rect.get_height()
            ax5.annotate(f'{h:.1f}%',
                        xy=(rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, 4),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9.5, fontweight='bold')
    
    plt.tight_layout()
    chart5_path = 'results/chart5_ragas_metrics.png'
    plt.savefig(chart5_path, dpi=300)
    plt.close()
    print(f"Saved {chart5_path}")

