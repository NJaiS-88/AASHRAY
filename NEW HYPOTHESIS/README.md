# Disaster Resource Requirement Benchmark: TypeSafe JEV vs. Groq LLM (gpt-oss-120b)

A publication-grade comparative benchmark evaluating **TypeSafe JEV** (accessed via OpenRouter's Decisions API) against a state-of-the-art open-weight LLM (**openai/gpt-oss-120b** on Groq) on emergency disaster resource classification.

---

## 🎯 Benchmark Objectives & Protocol

The system evaluates both models on multi-label classification across the exact 9 resource categories present in [`resource_dataset.csv`](file:///c:/NEW%20HYPOTHESIS/resource_dataset.csv):
1. `water`
2. `food`
3. `shelter`
4. `clothing`
5. `money`
6. `medical_help`
7. `medical_products`
8. `search_and_rescue`
9. `tools`

### Scientific Protocol
- **Dev/Test Split**: Default 30% development split and 70% test split (stratified by disaster genre: `direct`, `news`, `social`).
- **Threshold Tuning on Dev**: JEV outputs continuous probability decisions (`noul` $\in [0, 1]$). The decision threshold $\tau^*$ is swept across $\tau \in [0.10, 0.90]$ (step 0.05) **strictly on the Dev set** to maximize Micro F1.
- **Headline Numbers on Test**: All headline evaluation metrics, statistical significance tests, and winner determinations are evaluated on the untouched **Test Set** using the tuned threshold $\tau^*$.

---

## 🚀 Quick Start

### 1. Configure API Keys
Copy `.env.example` to `.env` and paste your API keys:
```bash
# In .env:
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```
*(If no `.env` file is present or keys are empty, the script will offer to run in Simulation / Mock Mode so you can inspect the full pipeline, statistics, charts, and PDF immediately.)*

### 2. Run the Benchmark
Run the script interactively:
```bash
python evaluate_resources.py
```
You will be prompted:
```text
[PROMPT] How many rows would you like to classify? [Press Enter for 50, 'all' for 3075, or enter number]:
```
Type any number of rows (e.g. `100`, `500`, or `all`), and the script handles the rest!

### CLI Options
You can also run non-interactively with custom parameters:
```bash
# Classify 100 rows using live APIs
python evaluate_resources.py --rows 100

# Classify the entire dataset (3,075 rows)
python evaluate_resources.py --rows 3075

# Run in simulation/mock mode without spending API credits
python evaluate_resources.py --mock --rows 60

# Custom dev split (e.g., 20% dev, 80% test)
python evaluate_resources.py --rows 150 --dev-split 0.2
```

---

## 📊 Comprehensive Metric Coverage

| Category | Evaluated Metrics |
| :--- | :--- |
| **Classification** | Per-resource Precision, Recall, F1, Specificity; Micro/Macro/Weighted Precision, Recall, F1; Subset Accuracy (Exact Match Ratio); Hamming Loss; Sample-averaged Jaccard similarity; Any-resource-required P/R/F1; Any-miss rate; Complete-miss rate |
| **Reliability** | Response parse-failure rate; Invalid (hallucinated) resource name count and rate |
| **Ranking & Calibration** | Mean Average Precision (mAP); Micro & Macro ROC-AUC; Brier score loss; Expected Calibration Error (ECE, 10 bins); Reliability Diagram calibration curves; Dev threshold sweep curves |
| **Operational Efficiency** | Latency percentiles (mean, p50 median, p95, p99); Prompt & Completion tokens per message; Estimated USD cost per 1,000 messages |
| **Statistical Rigor** | Paired Bootstrap 95% Confidence Intervals ($B=1,000$ iterations) for Micro P/R/F1 and paired differences $(\Delta = \text{JEV} - \text{LLM})$; Non-inferiority test on Recall ($\delta_0 = 0.05$ margin); McNemar exact-match contingency test; Genre stratification (`direct`, `news`, `social`) |

---

## 🏆 Deliverables Generated

1. **Master Scoreboard Infographic** (`benchmark_artifacts/comparison_scoreboard_summary.png`):
   - Standalone high-DPI image displaying all 5 evaluation categories, side-by-side metric cards, winner badges for each category, and the Overall Final Winner.
2. **Executive Multi-Page PDF Report** (`jev_vs_llm_benchmark_report.pdf`):
   - **Page 1**: Executive Summary, Scoreboard Summary, Overall Winner Banner, and Category Winners table.
   - **Page 2**: Multi-Label Classification Performance (Per-resource table, Aggregate table, Any-miss & Complete-miss rates, embedded comparison chart).
   - **Page 3**: Ranking, Calibration & Threshold Sweep (mAP, ROC-AUC, Brier score, ECE, reliability diagram, ROC/PR curves).
   - **Page 4**: Operational Efficiency & Reliability (Latency percentiles table, token usage, cost per 1k messages, schema reliability, efficiency chart).
   - **Page 5**: Statistical Significance & Genre Breakdown (Paired bootstrap 95% CIs, McNemar exact-match test, Non-inferiority test on recall, Genre stratification chart).
3. **Publication-Grade Chart Suite** (`benchmark_artifacts/`):
   - `classification_comparison.png`
   - `reliability_calibration.png`
   - `efficiency_latency_cost.png`
   - `statistical_bootstrap_diff.png`
   - `genre_breakdown.png`
   - `roc_pr_curves.png`
   - `comparison_scoreboard_summary.png`
