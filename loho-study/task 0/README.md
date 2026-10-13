# Task 0 recorded results

This folder contains the current five-trial-per-model study and the earlier task-0 experiments. See the [study index](../README.md) for all three tested tasks and the [setup guide](../../setup.md) to reproduce the evaluation protocol. Original launch commands and absolute path fields are historical execution records; the run folders and relative video/report links now live here.

**Media retention:** Only camera MP4s are retained as visual files. On October 11, 2026, 1,140 standalone PNGs were removed from this folder, while all 28 existing MP4 hashes stayed unchanged. JSON summaries, prompts, traces and cost records are preserved. Historical PNG references are explained by each run's `media_retention.json`; future control runs record video frame indices and timestamps instead. [Cleanup audit](png_cleanup_20261011_220849.json).

**Latest five-trial comparison:** Trials 4 and 5 for each provider are complete, bringing both models to **5/5 simulator-confirmed full successes**. All ten trials used the same state 0, seed 0, exact prompt, cameras, max effort, 80-call / 2000-step limits and no spending guard. All 454 requests used max; there were no fallbacks, automatic retries, API errors or rejected tools. All 20 camera videos are verified, and no PNGs remain in `results`.

| Model | Full successes | Calls | Action steps | Estimated total USD | Mean API latency |
|---|---:|---:|---:|---:|---:|
| GPT-6 Astra max | 5/5 | 284 | 5358 | $21.5267270 | 13.18s |
| Opus 5.5 max | 5/5 | 170 | 3060 | $27.6327558 | 49.20s |

Combined estimated cost: **$49.1594828 USD**, fully priced. The four added episodes cost **$20.2080461 USD**. All terminated on success before either episode limit.

- [Ten-trial scores, times, costs, steps and all 20 MP4 links](task0_uncapped_extend_20261011_221112_combined_REPORT.md)
- [Verified combined comparison JSON](task0_uncapped_extend_20261011_221112_combined_comparison.json)
- [Astra's five-trial metrics](task0_uncapped_extend_20261011_221112_combined_astra_five_trials.json)
- [Opus's five-trial metrics](task0_uncapped_extend_20261011_221112_combined_opus_five_trials.json)
- [Additional trials 4-5 launch manifest](task0_uncapped_extend_20261011_221112.json)
- [Latest result pointer](latest_task0_comparison.json)

The four additions save only MP4s as visual media, with observation frame indices/timestamps and input JPEG hashes in their traces. Native simulator replay verified both a new video-only offline fixture and an older paid trial after its PNG removal. All historical run summaries and the original 28 MP4 hashes are unchanged. Simulator-only smoke/calibration diagnostics can still save their diagnostic PNGs outside this result cohort.

## Earlier three-trial uncapped comparison

The latest six episodes used **80 calls / 2000 action steps with no spending guard**, task 0, state 0, seed 0, both cameras, RGB + proprioception, the same prompt and motion tools, and append-only image history. All six reached simulator-verified **100% completion**, and all 12 videos passed decoding checks. All 285 requests used max; there were no effort fallbacks, automatic retries, API errors or rejected tools. All controllers have stopped.

| Model | Full successes | Mean goal completion | Calls | Action steps | Estimated USD | Mean API latency |
|---|---:|---:|---:|---:|---:|---:|
| Opus 5.5 max | 3/3 | 100% | 100 | 1711 | $14.5173352 | 46.13s |
| GPT-6 Astra max | 3/3 | 100% | 185 | 3466 | $14.4341015 | 12.90s |

Complete estimated trial cost: **$28.9514367 USD**, with no unresolved usage in this batch.

- [Latest per-trial scores, timing, cost, steps and all 12 camera videos](task0_uncapped_20261011_203025_REPORT.md)
- [Verified six-trial comparison JSON](task0_uncapped_20261011_203025_comparison.json)
- [Opus's three complete trial records](task0_uncapped_20261011_203025_opus_three_trials.json)
- [Astra's three complete trial records](task0_uncapped_20261011_203025_astra_three_trials.json)
- [Launch manifest, exact commands, source hashes and shared settings](task0_uncapped_20261011_203025.json)
- [Pricing verification](task0_uncapped_20261011_203025_pricing_verification.json)

Providers ran concurrently with one fresh episode at a time per provider. No previous-run hindsight was injected. Initial images, proprioception, exact system prompt, runtime and controller settings matched the reference; the removal of the spending guard is recorded explicitly. This comparison uses one stored initial state. Historical capped episodes and their startup accounting are separate below.

## Earlier capped trials

The six earlier capped episodes are also archived here: three GPT-6 Astra max and three Opus 5.5 max trials.

| Model | Full-task successes | Mean goal completion | API calls | Estimated trial USD | Mean API latency |
|---|---:|---:|---:|---:|---:|
| claude-opus-5-5 | 3/3 | 100.0% | 130 | $24.5640 | 54.49s |
| gpt-6-astra | 1/3 | 66.7% | 139 | $8.7080 | 10.79s |

**Astra budget limitation:** Trials 1 and 2 ended on the former conservative cost guard at actual spend $3.3491135 and $3.2773665. Next-response reservations were $20.2922 and $20.6735. That guard bounded serialized conversation bytes as tokens and reserved the full 128000-token output allowance, using worst applicable input/cache-write rates. Encrypted Responses history expanded that bound. These reservations are not charges. The recorded comparison includes these early budget stops; both nominal 80-call and 2000-step limits were still available.

All six runs used task 0, stored state 0, seed 0, fresh conversations, absolute pose tools, both cameras, RGB + proprioception, append-only history/images, 10 Hz, 224x224, 80 calls, 2000 action steps, 128000 output tokens per call, and the same effective $23.6317058 cap. The system prompt, initial images and robot measurements, runtime, and controller settings matched. No previous-run hindsight was injected.

The local spending guard and request reservations were removed after these trials on October 11, 2026. Future runs retain the 80-call and 2000-action-step limits and cost telemetry, with no dollar cap. These six archived outcomes and their original limits have not been changed or rerun.

- [Combined model comparison](max_task0_model_comparison.json)
- [Astra scores, timing, tokens, all request costs and stopping reasons](astra_max_task0_three_trials.json)
- [Opus scores, timing, tokens and all request costs](opus55_task0_three_trials.json)
- [Max comparison configuration/status](max_model_comparison.json)

## GPT-6 Astra max

| Trial | Goal completion | Stop | Calls | Steps | Elapsed | Mean API | Estimated USD |
|---|---:|---|---:|---:|---:|---:|---:|
| [1](astra_task0_max_128k_trial1_20261011_155328/run_result.json) | 66.7% | cost_budget | 51 | 1031 | 10m 59s | 10.50s | $3.3491 |
| [2](astra_task0_max_128k_trial2_20261011_160114/run_result.json) | 33.3% | cost_budget | 50 | 957 | 11m 27s | 11.47s | $3.2774 |
| [3](astra_task0_max_128k_trial3_20261011_160114/run_result.json) | 100.0% | success | 38 | 698 | 7m 53s | 10.28s | $2.0816 |

Astra: 1/3 full-task successes; all 139 requests used max, with no xhigh fallback or automatic HTTP retries. One rejected motion command in trial 2 is included in usage and cost. All trial costs are complete. Estimated total: **$8.7080465 USD**.

## Opus 5.5 max

| Trial | Goal completion | Calls | Steps | Elapsed | Mean API | Estimated USD |
|---|---:|---:|---:|---:|---:|---:|
| [1](opus55_task0_max_128k_20261011_125617/run_result.json) | 100% | 32 | 539 | 43m 9s | 78.88s | $9.4182 |
| [2](opus55_task0_max_128k_trial2_20261011_140109/run_result.json) | 100% | 32 | 582 | 23m 48s | 42.46s | $4.1813 |
| [3](opus55_task0_max_128k_trial3_20261011_142433/run_result.json) | 100% | 66 | 1068 | 55m 34s | 48.50s | $10.9644 |

Opus: 3/3 full-task successes; fully priced estimated trial cost **$24.5640082 USD**. Trial 3 required extra contact and arm-recovery motions.

## Camera videos and steps

| Model / trial | Static camera | Wrist camera | Actions and results |
|---|---|---|---|
| Astra 1 | [MP4](astra_task0_max_128k_trial1_20261011_155328/episode.mp4) | [MP4](astra_task0_max_128k_trial1_20261011_155328/wrist_episode.mp4) | [Steps](astra_task0_max_128k_trial1_20261011_155328/STEPS_TAKEN.txt) |
| Astra 2 | [MP4](astra_task0_max_128k_trial2_20261011_160114/episode.mp4) | [MP4](astra_task0_max_128k_trial2_20261011_160114/wrist_episode.mp4) | [Steps](astra_task0_max_128k_trial2_20261011_160114/STEPS_TAKEN.txt) |
| Astra 3 | [MP4](astra_task0_max_128k_trial3_20261011_160114/episode.mp4) | [MP4](astra_task0_max_128k_trial3_20261011_160114/wrist_episode.mp4) | [Steps](astra_task0_max_128k_trial3_20261011_160114/STEPS_TAKEN.txt) |
| Opus 1 | [MP4](opus55_task0_max_128k_20261011_125617/episode.mp4) | [MP4](opus55_task0_max_128k_20261011_125617/wrist_episode.mp4) | [Steps](opus55_task0_max_128k_20261011_125617/STEPS_TAKEN.txt) |
| Opus 2 | [MP4](opus55_task0_max_128k_trial2_20261011_140109/episode.mp4) | [MP4](opus55_task0_max_128k_trial2_20261011_140109/wrist_episode.mp4) | [Steps](opus55_task0_max_128k_trial2_20261011_140109/STEPS_TAKEN.txt) |
| Opus 3 | [MP4](opus55_task0_max_128k_trial3_20261011_142433/episode.mp4) | [MP4](opus55_task0_max_128k_trial3_20261011_142433/wrist_episode.mp4) | [Steps](opus55_task0_max_128k_trial3_20261011_142433/STEPS_TAKEN.txt) |

Static is fixed `agentview`; wrist is moving `robot0_eye_in_hand`. These are the two recorded POVs. All 12 videos were independently decoded at 10 FPS and 224x224. Astra frame counts per view: 1032, 958, 699; Opus: 540, 583, 1069. Videos capture simulation movement; API waits are recorded in wall/inference telemetry.

Each run also contains `summary.json`, `api_attempts.jsonl`, `conversation.json`, `system_prompt.txt`, `configuration_verification.json`, `run_verification.json`, and both MP4 views. Standalone PNGs and final images have been removed; historical summaries remain unchanged.

Estimated cost of all six evaluation trials: **$33.2720547 USD**, fully priced. Two earlier Opus startup requests are preserved under `startup_attempts/`. Including those, known estimated cost is **$33.9280239**, with one unpriced request, so the full combined total remains unknown.

- [Original Opus startup/session accounting](opus_max_session_result.json)
- [Astra pricing verification](astra_pricing_verification.json)

Cost estimates use recorded snapshots; Astra standard rates were checked against [official API pricing](https://developers.openai.com/api/docs/pricing) on October 11, 2026. Reservations are not counted as charges.

The default `scripts/summarize_runs.py` scan includes `loho_runs/`, `results/` and `loho-study/`, retaining archived trials and startup costs in aggregate reporting.
