# Astra and Opus bar plots

[Alternative figure and table gallery](options/README.md)

[Combined chart](astra_opus_tasks_0_1_4.png) · [PDF](astra_opus_tasks_0_1_4.pdf) · [SVG](astra_opus_tasks_0_1_4.svg)

The main figure has one column: goal completion score, total tokens plus estimated API cost, and wall-clock time. In the middle panel, bars use the left token axis and white diamonds use the right USD axis; both have sample-SD whiskers.

[Tokens and cost together](tokens_and_cost_tasks_0_1_4.png) · [PDF](tokens_and_cost_tasks_0_1_4.pdf) · [SVG](tokens_and_cost_tasks_0_1_4.svg)

[Calls and action steps](calls_and_steps_tasks_0_1_4.png) · [PDF](calls_and_steps_tasks_0_1_4.pdf) · [SVG](calls_and_steps_tasks_0_1_4.svg)

Blue is GPT-6 Astra max; orange is Opus 5.5 max. Each bar uses the mean of the current five saved runs for that task and model. Capped whiskers show plus/minus one sample standard deviation across those five run values (ddof=1). They are not standard errors or confidence intervals.

Completion score measures final native goals; full success counts only runs with all goals satisfied. Percentage whiskers can extend above 100% because they show a descriptive standard deviation. Task 4 uses the current retained set. All thirty runs use stored state 0 and seed 0.

Tokens are the sum of provider-reported input and output across requests, including cached context and reported reasoning. These are token volumes, not unique context lengths or tokens weighted by price. Costs use the run's recorded USD estimate with actual cache usage. Wall-clock is recorded episode duration; cumulative API time sums request latency, including network and provider waiting. Per-call latency averages the five run-level mean latencies equally. Calls include requests whose tools were rejected; action steps exclude the five initial settling steps and API waiting.

| Metric | Task | Astra mean ± sample SD | Opus mean ± sample SD |
|---|---|---:|---:|
| Goal completion score | 0 | 100.0% ± 0.0% | 100.0% ± 0.0% |
| Goal completion score | 1 | 86.7% ± 18.3% | 80.0% ± 29.8% |
| Goal completion score | 4 | 100.0% ± 0.0% | 100.0% ± 0.0% |
| Full-task success | 0 | 100.0% ± 0.0% | 100.0% ± 0.0% |
| Full-task success | 1 | 60.0% ± 54.8% | 60.0% ± 54.8% |
| Full-task success | 4 | 100.0% ± 0.0% | 100.0% ± 0.0% |
| Total tokens | 0 | 2.09M ± 0.52M | 4.56M ± 1.05M |
| Total tokens | 1 | 1.22M ± 0.61M | 11.08M ± 2.93M |
| Total tokens | 4 | 2.35M ± 0.62M | 5.92M ± 2.46M |
| Estimated API cost | 0 | $4.31 ± $0.90 | $5.53 ± $1.03 |
| Estimated API cost | 1 | $2.89 ± $0.87 | $8.81 ± $1.84 |
| Estimated API cost | 4 | $4.55 ± $0.99 | $5.92 ± $1.67 |
| Wall-clock time | 0 | 14.6 ± 2.4 | 29.1 ± 3.8 |
| Wall-clock time | 1 | 11.1 ± 2.1 | 44.2 ± 8.8 |
| Wall-clock time | 4 | 18.7 ± 3.2 | 29.3 ± 6.2 |
| Cumulative API inference time | 0 | 12.5 ± 2.1 | 27.9 ± 3.8 |
| Cumulative API inference time | 1 | 9.8 ± 1.8 | 42.3 ± 8.6 |
| Cumulative API inference time | 4 | 16.3 ± 3.0 | 27.9 ± 6.0 |
| Mean API latency per call | 0 | 13.2 ± 1.5 | 49.5 ± 7.6 |
| Mean API latency per call | 1 | 14.5 ± 1.6 | 43.9 ± 6.7 |
| Mean API latency per call | 4 | 15.8 ± 1.7 | 39.8 ± 3.7 |
| Model calls | 0 | 56.8 ± 7.7 | 34.0 ± 2.9 |
| Model calls | 1 | 41.2 ± 10.6 | 58.0 ± 9.7 |
| Model calls | 4 | 61.8 ± 7.7 | 42.0 ± 8.7 |
| Action steps | 0 | 1071.6 ± 131.3 | 612.0 ± 96.9 |
| Action steps | 1 | 667.8 ± 213.5 | 991.4 ± 182.7 |
| Action steps | 4 | 1204.4 ± 161.5 | 739.8 ± 130.3 |

Individual charts are available as PNG, PDF and SVG:

- [Goal completion score](completion_percent.png) · [PDF](completion_percent.pdf) · [SVG](completion_percent.svg)
- [Full-task success](full_success_percent.png) · [PDF](full_success_percent.pdf) · [SVG](full_success_percent.svg)
- [Total tokens](total_tokens.png) · [PDF](total_tokens.pdf) · [SVG](total_tokens.svg)
- [Estimated API cost](estimated_api_cost_usd.png) · [PDF](estimated_api_cost_usd.pdf) · [SVG](estimated_api_cost_usd.svg)
- [Wall-clock time](elapsed_seconds.png) · [PDF](elapsed_seconds.pdf) · [SVG](elapsed_seconds.svg)
- [Cumulative API inference time](total_api_latency_seconds.png) · [PDF](total_api_latency_seconds.pdf) · [SVG](total_api_latency_seconds.svg)
- [Mean API latency per call](mean_api_latency_seconds.png) · [PDF](mean_api_latency_seconds.pdf) · [SVG](mean_api_latency_seconds.svg)
- [Model calls](api_calls.png) · [PDF](api_calls.pdf) · [SVG](api_calls.svg)
- [Action steps](action_steps.png) · [PDF](action_steps.pdf) · [SVG](action_steps.svg)

[Exact statistics, per-run values and source hashes](comparison_statistics.json). Rebuild with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/plot_study_comparison.py` from the workspace.
