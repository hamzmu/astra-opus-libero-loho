# Task 0 comparison without a spending guard

5 fresh Opus 5.5 max and 5 GPT-6 Astra max trials, each using state 0 and seed 0.

Every episode used 80 model calls, 2000 action steps, static plus wrist cameras, RGB + proprioception, absolute pose tools, append-only conversation/images, 10 Hz, 224x224 and 128000 output tokens per call. No dollar cap or request reservations were applied. Initial images, robot state, prompt and runtime matched the reference. All 20 videos were independently decoded. Only MP4s are retained as visual files; older standalone PNGs were removed, and later runs store video frame references. Historical capped episodes are separate.

| Model | Full successes | Mean goal completion | Calls | Steps | Estimated USD | Mean API latency |
|---|---:|---:|---:|---:|---:|---:|
| claude-opus-5-5 | 5/5 | 100.0% | 170 | 3060 | $27.6328 | 49.20s |
| gpt-6-astra | 5/5 | 100.0% | 284 | 5358 | $21.5267 | 13.18s |

| Model | Trial | Completion | Stop | Calls | Steps | Estimated USD | Elapsed |
|---|---:|---:|---|---:|---:|---:|---:|
| claude-opus-5-5 | [1](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 31 | 479 | $5.3491 | 29m 20s |
| claude-opus-5-5 | [2](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 33 | 598 | $4.9309 | 27m 10s |
| claude-opus-5-5 | [3](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 36 | 634 | $4.2374 | 23m 46s |
| claude-opus-5-5 | [4](opus55_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/run_result.json) | 100.0% | success | 32 | 599 | $6.3530 | 31m 22s |
| claude-opus-5-5 | [5](opus55_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/run_result.json) | 100.0% | success | 38 | 750 | $6.7625 | 33m 46s |
| gpt-6-astra | [1](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 66 | 1172 | $5.1448 | 15m 33s |
| gpt-6-astra | [2](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 63 | 1206 | $5.4024 | 18m 13s |
| gpt-6-astra | [3](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/run_result.json) | 100.0% | success | 56 | 1088 | $3.8869 | 12m 48s |
| gpt-6-astra | [4](astra_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/run_result.json) | 100.0% | success | 48 | 879 | $3.4103 | 12m 25s |
| gpt-6-astra | [5](astra_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/run_result.json) | 100.0% | success | 51 | 1013 | $3.6823 | 13m 52s |

| Model / trial | Static camera | Wrist camera | Steps and readbacks |
|---|---|---|---|
| claude-opus-5-5 / 1 | [MP4](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/episode.mp4) | [MP4](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial1_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 2 | [MP4](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/episode.mp4) | [MP4](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial2_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 3 | [MP4](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/episode.mp4) | [MP4](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial3_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 4 | [MP4](opus55_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/episode.mp4) | [MP4](opus55_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/STEPS_TAKEN.txt) |
| claude-opus-5-5 / 5 | [MP4](opus55_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/episode.mp4) | [MP4](opus55_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/wrist_episode.mp4) | [Steps](opus55_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/STEPS_TAKEN.txt) |
| gpt-6-astra / 1 | [MP4](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/episode.mp4) | [MP4](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial1_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| gpt-6-astra / 2 | [MP4](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/episode.mp4) | [MP4](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial2_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| gpt-6-astra / 3 | [MP4](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/episode.mp4) | [MP4](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial3_task0_uncapped_20261011_203025/STEPS_TAKEN.txt) |
| gpt-6-astra / 4 | [MP4](astra_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/episode.mp4) | [MP4](astra_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial4_task0_uncapped_extend_20261011_221112/STEPS_TAKEN.txt) |
| gpt-6-astra / 5 | [MP4](astra_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/episode.mp4) | [MP4](astra_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/wrist_episode.mp4) | [Steps](astra_task0_max_nocost_trial5_task0_uncapped_extend_20261011_221112/STEPS_TAKEN.txt) |

API latency and elapsed time include reported request failures. Simulated movement time is separate; API waits pause the simulator. Costs use provider-reported tokens and actual cache reads/writes. Missing usage remains unresolved, never free. Provider caches were not forcibly cleared between trials.

- [Complete comparison JSON](task0_uncapped_extend_20261011_221112_combined_comparison.json)
- [Launch manifest and source hashes](task0_uncapped_20261011_203025.json)
- [Launch manifest and source hashes](task0_uncapped_extend_20261011_221112.json)
