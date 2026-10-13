# Figure options

[Gallery preview](00_gallery.png)

All figures use the current five saved runs per model on Tasks 0, 1 and 4: 30 episodes, max effort, state 0, seed 0. Task 4 uses its retained set. Blue is Astra and orange is Opus. Mean/variability summaries use sample SD (ddof=1).

| Option | PNG | Best use |
|---|---|---|
| 1 | [Individual-run dot plots](01_individual_run_dots.png) | Best for seeing all five observations, their variability and outliers across the four headline metrics. |
| 2 | [API request time](02_wallclock_breakdown.png) | Compares measured API request time per episode, with mean and sample SD; other episode time is excluded. |
| 3 | [Goal-progress curves](03_goal_progress_curves.png) | Shows observed subtask progress, recoveries and final partial outcomes against executed action steps. |
| 4 | [Cost versus completion](04_cost_completion_scatter.png) | Shows cost/performance trade-offs and whether expensive episodes also achieved their goals. |
| 5 | [Subtask completion heatmap](05_subtask_heatmap.png) | Best for explaining the partial Task 1 outcomes by object/condition rather than only a percentage. |
| 6 | [Per-run results table](06_per_run_table.png) | Best for inspecting individual calls, steps, resource use and termination outcomes. |
| 7 | [Compact summary table](07_summary_table.png) | Best single reference for the requested metrics, with full success counts and exact mean ± SD values. |

The requested headline metrics are goal completion, output tokens (including reasoning), estimated API cost and measured episode wall-clock time. Individual dots and the summary table present all four. Other figures focus on the relationships or recorded conditions best suited to their layout.

API request time includes network/provider waiting. The API time figure excludes other episode time, and its whiskers use the sample SD of API time across five runs. Goal-progress curves use observed decision-end scores against action steps, with no reconstructed wall-clock timing. Cost/completion points show exact recorded values. The heatmap shows final native conditions, including any conditions lost during a run.

## Individual run tables

- [Task 0 table](06_task0_run_table.png)
- [Task 1 table](06_task1_run_table.png)
- [Task 4 table](06_task4_run_table.png)

Each primary figure/table also has PDF and SVG exports with the same filename stem. [Source manifest](figure_sources.json).

Rebuild with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_figure_options.py` from the workspace.

[Total tokens and estimated cost: alternative layouts](tokens_cost/README.md).
