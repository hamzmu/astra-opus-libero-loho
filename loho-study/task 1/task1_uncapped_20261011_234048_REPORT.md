# Task 1 comparison without a spending guard

5 fresh Opus 5.5 max and 5 GPT-6 Astra max trials, each using state 0 and seed 0.

Each episode had limits of 80 model calls and 2000 action steps, with static plus wrist cameras, RGB + proprioception, absolute pose tools, append-only conversation/images, 10 Hz, 224x224 and 128000 output tokens per call. No dollar cap or request reservations were applied. Initial images, robot state, prompt and runtime matched the reference. All 20 videos were independently decoded. Only MP4s are retained as visual files; observation records include video frame references. Historical capped episodes are separate.

| Model | Full successes | Mean goal completion | Calls | Steps | Estimated USD | Mean API latency |
|---|---:|---:|---:|---:|---:|---:|
| claude-opus-5-5 | 3/5 | 80.0% | 290 | 4957 | $44.0601 | 43.77s |
| gpt-6-astra | 3/5 | 86.7% | 206 | 3339 | $14.4566 | 14.23s |

| Model | Trial | Completion | Stop | Calls | Steps | Estimated USD | Elapsed |
|---|---:|---:|---|---:|---:|---:|---:|
| claude-opus-5-5 | [1](opus55_task1_max_nocost_trial1_task1_uncapped_20261011_234048/run_result.json) | 33.3% | model_done | 64 | 1070 | $8.3283 | 41m 20s |
| claude-opus-5-5 | [2](opus55_task1_max_nocost_trial2_task1_uncapped_20261011_234048/run_result.json) | 100.0% | success | 55 | 990 | $10.2676 | 52m 07s |
| claude-opus-5-5 | [3](opus55_task1_max_nocost_trial3_task1_uncapped_20261011_234048/run_result.json) | 100.0% | success | 60 | 1025 | $8.9479 | 45m 59s |
| claude-opus-5-5 | [4](opus55_task1_max_nocost_trial4_task1_uncapped_20261011_234048/run_result.json) | 66.7% | give_up | 68 | 1181 | $10.5544 | 51m 02s |
| claude-opus-5-5 | [5](opus55_task1_max_nocost_trial5_task1_uncapped_20261011_234048/run_result.json) | 100.0% | success | 43 | 691 | $5.9619 | 30m 22s |
| gpt-6-astra | [1](astra_task1_max_nocost_trial1_task1_uncapped_20261011_234048/run_result.json) | 100.0% | success | 35 | 574 | $2.4760 | 10m 55s |
| gpt-6-astra | [2](astra_task1_max_nocost_trial2_task1_uncapped_20261011_234048/run_result.json) | 66.7% | model_done | 34 | 537 | $2.2939 | 9m 32s |
| gpt-6-astra | [3](astra_task1_max_nocost_trial3_task1_uncapped_20261011_234048/run_result.json) | 66.7% | model_done | 59 | 1044 | $4.3265 | 14m 19s |
| gpt-6-astra | [4](astra_task1_max_nocost_trial4_task1_uncapped_20261011_234048/run_result.json) | 100.0% | success | 43 | 633 | $3.1182 | 11m 35s |
| gpt-6-astra | [5](astra_task1_max_nocost_trial5_task1_uncapped_20261011_234048/run_result.json) | 100.0% | success | 35 | 551 | $2.2421 | 8m 55s |

| Model / trial | Static camera | Wrist camera | Steps and readbacks |
|---|---|---|---|
| claude-opus-5-5 / 1 | [MP4](opus55_task1_max_nocost_trial1_task1_uncapped_20261011_234048/episode.mp4) | [MP4](opus55_task1_max_nocost_trial1_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](opus55_task1_max_nocost_trial1_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 2 | [MP4](opus55_task1_max_nocost_trial2_task1_uncapped_20261011_234048/episode.mp4) | [MP4](opus55_task1_max_nocost_trial2_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](opus55_task1_max_nocost_trial2_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 3 | [MP4](opus55_task1_max_nocost_trial3_task1_uncapped_20261011_234048/episode.mp4) | [MP4](opus55_task1_max_nocost_trial3_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](opus55_task1_max_nocost_trial3_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 4 | [MP4](opus55_task1_max_nocost_trial4_task1_uncapped_20261011_234048/episode.mp4) | [MP4](opus55_task1_max_nocost_trial4_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](opus55_task1_max_nocost_trial4_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 5 | [MP4](opus55_task1_max_nocost_trial5_task1_uncapped_20261011_234048/episode.mp4) | [MP4](opus55_task1_max_nocost_trial5_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](opus55_task1_max_nocost_trial5_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| gpt-6-astra / 1 | [MP4](astra_task1_max_nocost_trial1_task1_uncapped_20261011_234048/episode.mp4) | [MP4](astra_task1_max_nocost_trial1_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](astra_task1_max_nocost_trial1_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| gpt-6-astra / 2 | [MP4](astra_task1_max_nocost_trial2_task1_uncapped_20261011_234048/episode.mp4) | [MP4](astra_task1_max_nocost_trial2_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](astra_task1_max_nocost_trial2_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| gpt-6-astra / 3 | [MP4](astra_task1_max_nocost_trial3_task1_uncapped_20261011_234048/episode.mp4) | [MP4](astra_task1_max_nocost_trial3_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](astra_task1_max_nocost_trial3_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| gpt-6-astra / 4 | [MP4](astra_task1_max_nocost_trial4_task1_uncapped_20261011_234048/episode.mp4) | [MP4](astra_task1_max_nocost_trial4_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](astra_task1_max_nocost_trial4_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |
| gpt-6-astra / 5 | [MP4](astra_task1_max_nocost_trial5_task1_uncapped_20261011_234048/episode.mp4) | [MP4](astra_task1_max_nocost_trial5_task1_uncapped_20261011_234048/wrist_episode.mp4) | [Steps](astra_task1_max_nocost_trial5_task1_uncapped_20261011_234048/STEPS_TAKEN.txt) |

API latency and elapsed time include reported request failures. Simulated movement time is separate; API waits pause the simulator. Costs use provider-reported tokens and actual cache reads/writes. Missing usage remains unresolved, never free. Provider caches were not forcibly cleared between trials.

Completion uses final simulator goal predicates. A model-declared `done` is not a full success unless all goals are satisfied. `give_up` records the model ending an incomplete attempt. Limits are caps, not required episode lengths.

- [Complete comparison JSON](task1_uncapped_20261011_234048_comparison.json)
- [Launch manifest and source hashes](task1_uncapped_20261011_234048.json)
