# Task 4 comparison without a spending guard

5 retained Opus 5.5 max and 5 retained GPT-6 Astra max trials, each using state 0 and seed 0.

Each episode had limits of 80 model calls and 2000 action steps, with static plus wrist cameras, RGB + proprioception, absolute pose tools, append-only conversation/images, 10 Hz, 224x224 and 128000 output tokens per call. No dollar cap or request reservations were applied. Initial images, robot state, prompt and runtime matched the reference. All 20 videos were independently decoded. Only MP4s are retained as visual files; observation records include video frame references. Historical capped episodes are separate.

| Model | Full successes | Mean goal completion | Calls | Steps | Estimated USD | Mean API latency |
|---|---:|---:|---:|---:|---:|---:|
| claude-opus-5-5 | 5/5 | 100.0% | 210 | 3699 | $29.5999 | 39.80s |
| gpt-6-astra | 5/5 | 100.0% | 309 | 6022 | $22.7303 | 15.84s |

| Model | Trial | Completion | Stop | Calls | Steps | Estimated USD | Elapsed |
|---|---:|---:|---|---:|---:|---:|---:|
| claude-opus-5-5 | [1](opus55_task4_max_nocost_trial1_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 45 | 738 | $6.5199 | 32m 46s |
| claude-opus-5-5 | [2](opus55_task4_max_nocost_trial2_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 37 | 631 | $5.7710 | 29m 11s |
| claude-opus-5-5 | [3](opus55_task4_max_nocost_trial3_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 56 | 962 | $8.4429 | 37m 49s |
| claude-opus-5-5 | [4](opus55_task4_max_nocost_trial4_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 36 | 700 | $4.4506 | 23m 49s |
| claude-opus-5-5 | [5](opus55_task4_max_nocost_trial5_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 36 | 668 | $4.4154 | 22m 57s |
| gpt-6-astra | [1](astra_task4_max_nocost_trial1_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 51 | 938 | $3.5352 | 16m 00s |
| gpt-6-astra | [2](astra_task4_max_nocost_trial2_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 70 | 1351 | $6.0452 | 23m 52s |
| gpt-6-astra | [3](astra_task4_max_nocost_trial3_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 67 | 1273 | $4.6434 | 18m 08s |
| gpt-6-astra | [4](astra_task4_max_nocost_trial4_task4_uncapped_20261012_110427/run_result.json) | 100.0% | success | 64 | 1284 | $4.7582 | 19m 10s |
| gpt-6-astra | [5](astra_task4_max_nocost_trial5_task4_20261012_132742/run_result.json) | 100.0% | success | 57 | 1176 | $3.7483 | 16m 07s |

| Model / trial | Static camera | Wrist camera | Steps and readbacks |
|---|---|---|---|
| claude-opus-5-5 / 1 | [MP4](opus55_task4_max_nocost_trial1_task4_uncapped_20261012_110427/episode.mp4) | [MP4](opus55_task4_max_nocost_trial1_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](opus55_task4_max_nocost_trial1_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 2 | [MP4](opus55_task4_max_nocost_trial2_task4_uncapped_20261012_110427/episode.mp4) | [MP4](opus55_task4_max_nocost_trial2_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](opus55_task4_max_nocost_trial2_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 3 | [MP4](opus55_task4_max_nocost_trial3_task4_uncapped_20261012_110427/episode.mp4) | [MP4](opus55_task4_max_nocost_trial3_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](opus55_task4_max_nocost_trial3_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 4 | [MP4](opus55_task4_max_nocost_trial4_task4_uncapped_20261012_110427/episode.mp4) | [MP4](opus55_task4_max_nocost_trial4_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](opus55_task4_max_nocost_trial4_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 5 | [MP4](opus55_task4_max_nocost_trial5_task4_uncapped_20261012_110427/episode.mp4) | [MP4](opus55_task4_max_nocost_trial5_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](opus55_task4_max_nocost_trial5_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| gpt-6-astra / 1 | [MP4](astra_task4_max_nocost_trial1_task4_uncapped_20261012_110427/episode.mp4) | [MP4](astra_task4_max_nocost_trial1_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](astra_task4_max_nocost_trial1_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| gpt-6-astra / 2 | [MP4](astra_task4_max_nocost_trial2_task4_uncapped_20261012_110427/episode.mp4) | [MP4](astra_task4_max_nocost_trial2_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](astra_task4_max_nocost_trial2_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| gpt-6-astra / 3 | [MP4](astra_task4_max_nocost_trial3_task4_uncapped_20261012_110427/episode.mp4) | [MP4](astra_task4_max_nocost_trial3_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](astra_task4_max_nocost_trial3_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| gpt-6-astra / 4 | [MP4](astra_task4_max_nocost_trial4_task4_uncapped_20261012_110427/episode.mp4) | [MP4](astra_task4_max_nocost_trial4_task4_uncapped_20261012_110427/wrist_episode.mp4) | [Steps](astra_task4_max_nocost_trial4_task4_uncapped_20261012_110427/STEPS_TAKEN.txt) |
| gpt-6-astra / 5 | [MP4](astra_task4_max_nocost_trial5_task4_20261012_132742/episode.mp4) | [MP4](astra_task4_max_nocost_trial5_task4_20261012_132742/wrist_episode.mp4) | [Steps](astra_task4_max_nocost_trial5_task4_20261012_132742/STEPS_TAKEN.txt) |

API latency and elapsed time include reported request failures. Simulated movement time is separate; API waits pause the simulator. Costs use provider-reported tokens and actual cache reads/writes. Missing usage remains unresolved, never free. Provider caches were not forcibly cleared between trials.

Completion uses final simulator goal predicates. A model-declared `done` is not a full success unless all goals are satisfied. `give_up` records the model ending an incomplete attempt. Limits are caps, not required episode lengths.

- [Complete comparison JSON](task4_retained_20261012_135134_comparison.json)
- [Launch manifest and source hashes](task4_retained_20261012_135134.json)
