# Task 0 comparison without a spending guard

Three fresh Opus 5.5 max and three GPT-6 Astra max trials, each using state 0 and seed 0.

Every episode used 80 model calls, 2000 action steps, static plus wrist cameras, RGB + proprioception, absolute pose tools, append-only conversation/images, 10 Hz, 224x224 and 128000 output tokens per call. No dollar cap or request reservations were applied. Initial images, robot state, prompt and runtime matched the reference. All 12 videos were independently decoded. Historical capped episodes are separate.

| Model | Full successes | Mean goal completion | Calls | Steps | Estimated USD | Mean API latency |
|---|---:|---:|---:|---:|---:|---:|
| claude-opus-5-5 | 3/3 | 100.0% | 100 | 1711 | $14.5173 | 46.13s |
| gpt-6-astra | 3/3 | 100.0% | 185 | 3466 | $14.4341 | 12.90s |

| Model | Trial | Completion | Stop | Calls | Steps | Estimated USD | Elapsed |
|---|---:|---:|---|---:|---:|---:|---:|
| claude-opus-5-5 | [1](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 31 | 479 | $5.3491 | 29m 20s |
| claude-opus-5-5 | [2](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 33 | 598 | $4.9309 | 27m 10s |
| claude-opus-5-5 | [3](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 36 | 634 | $4.2374 | 23m 46s |
| gpt-6-astra | [1](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 66 | 1172 | $5.1448 | 15m 33s |
| gpt-6-astra | [2](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 63 | 1206 | $5.4024 | 18m 13s |
| gpt-6-astra | [3](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 56 | 1088 | $3.8869 | 12m 48s |

| Model / trial | Static camera | Wrist camera | Steps and readbacks |
|---|---|---|---|
| claude-opus-5-5 / 1 | [MP4](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/episode.mp4) | [MP4](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 2 | [MP4](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/episode.mp4) | [MP4](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 3 | [MP4](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/episode.mp4) | [MP4](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| gpt-6-astra / 1 | [MP4](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/episode.mp4) | [MP4](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| gpt-6-astra / 2 | [MP4](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/episode.mp4) | [MP4](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| gpt-6-astra / 3 | [MP4](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/episode.mp4) | [MP4](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |

API latency and elapsed time include reported request failures. Simulated movement time is separate; API waits pause the simulator. Costs use provider-reported tokens and actual cache reads/writes. Missing usage remains unresolved, never free. Provider caches were not forcibly cleared between trials.

- [Complete comparison JSON](task0_uncapped_20261011_203025_comparison.json)
- [Launch manifest and source hashes](task0_uncapped_20261011_203025.json)
- [Pricing verification](task0_uncapped_20261011_203025_pricing_verification.json)
