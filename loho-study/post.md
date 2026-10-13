# Astra vs Opus on LIBERO-LoHo

*Five saved runs per model on Tasks 0, 1 and 4; max effort; stored state 0 and seed 0; current retained Task 4 results.*

> Astra matched or exceeded mean goal completion on all three tasks while using about 88% fewer output tokens overall, including reasoning.

> Astra averaged 42% [Astra $3.91 vs Opus $6.75 per run] lower estimated API cost and 57% [Astra 14.8 vs Opus 34.2 minutes per run] shorter wall-clock time.

> Opus averaged 16% fewer calls and 20% fewer action steps, while Task 1 reversed this pattern and both models fully completed three of five trials.

[Scores, tokens, cost and time](plots/astra_opus_tasks_0_1_4.png) · [Calls and steps](plots/calls_and_steps_tasks_0_1_4.png) · [Source data and statistics](plots/comparison_statistics.json)

[Waiting-aware static-camera overview at 40x](videos/astra_opus_tasks_0_1_4_wait_aware_40x.mp4) · [4x replay](videos/astra_opus_tasks_0_1_4_wait_aware_4x.mp4)
