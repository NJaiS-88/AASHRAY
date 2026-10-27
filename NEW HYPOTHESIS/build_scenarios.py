import os
import json
import random
import pandas as pd
import numpy as np

RESOURCE_COLUMNS = [
    'water', 'food', 'shelter', 'clothing', 'money',
    'medical_help', 'medical_products', 'search_and_rescue', 'tools'
]

df = pd.read_csv('resource_dataset.csv')
num_rows = 150
rng = random.Random(42)
sampled_indices = []

for col in RESOURCE_COLUMNS:
    pos_indices = df[df[col] == 1].index.difference(sampled_indices).tolist()
    if pos_indices:
        sampled_indices.append(rng.choice(pos_indices))

for genre, g in df.groupby('genre'):
    if not any(df.loc[idx, 'genre'] == genre for idx in sampled_indices):
        genre_indices = g.index.difference(sampled_indices).tolist()
        if genre_indices:
            sampled_indices.append(rng.choice(genre_indices))

if len(sampled_indices) < num_rows:
    remaining = df.index.difference(sampled_indices).tolist()
    diff_count = num_rows - len(sampled_indices)
    sampled_indices.extend(rng.sample(remaining, min(diff_count, len(remaining))))

with open('predictions_cache.json', 'r', encoding='utf-8') as f:
    cache = json.load(f)

# Dev split was 30% (45 rows), test set is remaining 105 rows
n_dev = max(4, int(num_rows * 0.3))
test_indices = sampled_indices[n_dev:]

tau_decision = 0.15  # Tuned dev threshold from benchmark

disagree_candidates = []
agree_candidates = []

for idx in test_indices:
    entry = cache[str(idx)]
    j_probs = entry['jev']['probabilities']
    j_list = sorted([r for r in RESOURCE_COLUMNS if j_probs.get(r, 0) >= tau_decision])
    
    l_bin = entry['llm']['binary']
    l_list = sorted([r for r in RESOURCE_COLUMNS if l_bin.get(r, 0) == 1])
    
    text = str(df.loc[idx, 'text_clean']).strip()
    gold = {r: int(df.loc[idx, r]) for r in RESOURCE_COLUMNS}
    gold_list = [r for r in RESOURCE_COLUMNS if gold[r] == 1]
    
    # Must have some relevant context/signal
    if len(gold_list) == 0 and len(j_list) == 0 and len(l_list) == 0:
        continue

    item = {
        'orig_idx': idx,
        'text': text,
        'gold': gold,
        'gold_list': gold_list,
        'jev_list': j_list,
        'llm_list': l_list
    }

    if j_list != l_list:
        disagree_candidates.append(item)
    else:
        agree_candidates.append(item)

print(f"Candidate pools: {len(disagree_candidates)} disagree, {len(agree_candidates)} agree")

# We want 35 scenarios total: 12 disagree (~34.3%), 23 agree
# Ensure all 9 resources have gold representation if present in candidate pools
rng_select = random.Random(42)

# Select disagree
selected_disagree = []
# Ensure diverse resource coverage in disagree
for col in RESOURCE_COLUMNS:
    matching = [it for it in disagree_candidates if (it['gold'][col] == 1 or col in it['jev_list'] or col in it['llm_list']) and it not in selected_disagree]
    if matching and len(selected_disagree) < 12:
        selected_disagree.append(rng_select.choice(matching))

remaining_dis = [it for it in disagree_candidates if it not in selected_disagree]
needed_dis = 12 - len(selected_disagree)
if needed_dis > 0:
    selected_disagree.extend(rng_select.sample(remaining_dis, min(needed_dis, len(remaining_dis))))

# Select agree
selected_agree = []
for col in RESOURCE_COLUMNS:
    matching = [it for it in agree_candidates if it['gold'][col] == 1 and it not in selected_agree]
    if matching and len(selected_agree) < 23:
        selected_agree.append(rng_select.choice(matching))

remaining_agr = [it for it in agree_candidates if it not in selected_agree]
needed_agr = 23 - len(selected_agree)
if needed_agr > 0:
    selected_agree.extend(rng_select.sample(remaining_agr, min(needed_agr, len(remaining_agr))))

selected_all = []
for i, item in enumerate(selected_disagree):
    scen_id = f"SCEN-DIS-{i+1:02d}"
    selected_all.append((scen_id, item, 1))

for i, item in enumerate(selected_agree):
    scen_id = f"SCEN-AGR-{i+1:02d}"
    selected_all.append((scen_id, item, 0))

# Build DataFrame
rows = []
for scen_id, item, dis_flag in selected_all:
    row_dict = {
        'id': scen_id,
        'orig_dataset_id': item['orig_idx'],
        'text': item['text'],
        'disagree': dis_flag
    }
    for r in RESOURCE_COLUMNS:
        row_dict[r] = item['gold'][r]
    rows.append(row_dict)

scenarios_df = pd.DataFrame(rows)
cols_order = ['id', 'text'] + RESOURCE_COLUMNS + ['disagree', 'orig_dataset_id']
scenarios_df = scenarios_df[cols_order]

scenarios_df.to_csv('scenarios.csv', index=False)
print(f"Successfully wrote scenarios.csv with {len(scenarios_df)} scenarios.")
print(f"Disagree count: {scenarios_df['disagree'].sum()} ({scenarios_df['disagree'].mean()*100:.1f}%)")
print(f"Agree count: {(1 - scenarios_df['disagree']).sum()}")
print("\nResource distribution in selected scenarios:")
print(scenarios_df[RESOURCE_COLUMNS].sum())
