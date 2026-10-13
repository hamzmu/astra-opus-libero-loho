# Task 4: drawer and bowl

Five retained GPT-6 Astra max runs and five retained Opus 5.5 max runs are saved here. All ten have simulator-confirmed **100% completion**. [Full report and twenty camera videos](task4_retained_20261012_135134_REPORT.md), [comparison JSON](task4_retained_20261012_135134_comparison.json), [latest result pointer](latest_task4_comparison.json).

| Model | Retained full successes | Mean final completion | Calls | Action steps | Estimated retained-run USD | Mean API latency |
|---|---:|---:|---:|---:|---:|---:|
| GPT-6 Astra max | 5/5 | 100% | 309 | 6,022 | $22.7302665 | 15.84s |
| Opus 5.5 max | 5/5 | 100% | 210 | 3,699 | $29.5998880 | 39.80s |

The retained runs cost an estimated **$52.3301545 USD**, with complete provider-reported usage accounting. All 519 requests used max effort. There were zero API errors, effort fallbacks or automatic retries. Astra run 2 had one rejected motion tool included in the request and cost totals. Every retained run stopped on native simulator success before the call and action-step limits. No controller remains running.

The instruction is: **Put the butter at the back and the chocolate pudding into the cabinet top drawer, then close the top drawer. Place the black bowl on top of the cabinet.**

Native final scoring has four equally weighted goals:

1. The back butter (`butter_2`) is in the top drawer.
2. The chocolate pudding is in the top drawer.
3. The top drawer is closed.
4. The black bowl is on top of the cabinet.

Each satisfied final goal contributes 25%; full success requires all four simultaneously. Final and peak completion are recorded separately.

Each run starts from stored state 0 with seed 0 and a fresh conversation. Settings match the task-0 and task-1 study: max reasoning, an 80-call / 2000-action-step episode limit, 128000 output tokens per request, static plus wrist RGB, proprioception, absolute pose tools, append-only conversation and images, 10 Hz, 224x224 RGB, and 25% motion speed. There is no spending guard or request reservation. Astra may fall back to xhigh only if max is explicitly rejected. No prior-run hindsight is supplied.

One run executes at a time per provider; the two providers run concurrently. The controller, prompt template, model configuration and pricing snapshots have the same frozen hashes as task 1. Task instruction, initial images and measured rig facts are specific to task 4. A simulator-only preflight verified reset, scoring, cameras and robot state without paid API requests.

Only the static `episode.mp4` and wrist `wrist_episode.mp4` are saved as visual files; no PNGs are retained. Each run includes prompts, actions, measured tool results, scores, usage, estimated cost and inference latency. All retained records passed configuration and accounting verification, and all twenty MP4s were independently decoded with the expected resolution, frame rate and frame counts. These results cover one stored initial state.

- [Retained-run manifest and frozen controller hashes](task4_retained_20261012_135134.json)
- [Simulator-only preflight](../../setup_logs/task4_reference_20261012_110427/preflight_verification.json)
- [Study index](../README.md)
- [Workspace setup](../../README.md)
