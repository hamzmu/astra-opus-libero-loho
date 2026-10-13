# Astra and Opus video comparisons

## Combined static-camera video

[Watch Tasks 0, 1 and 4 together](astra6_opus55_tasks_0_1_4_static_minimal_4x.mp4)

The main README displays a looping [GIF preview](astra6_opus55_tasks_0_1_4_static_minimal_4x_preview.gif), linked to this MP4. Both show model/logo badges, bold underlined task headings and a bottom-right ×4 badge. The preview is 800 × 556, targets 8 fps and uses 128 palette colors. GitHub removes repository-relative HTML video embeds from rendered READMEs.

Rebuild the preview offline with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_branded_readme_preview.py`. [Preview verification](branded_readme_preview_verification.json).

Columns are **Task 0, Task 1 and Task 4**; rows are **Astra on top and Opus below**. All six static-camera clips start together at **4× simulation speed**, with shorter runs holding their final frame. API waiting is omitted.

**Wrist camera view omitted from this video, but used in evaluation.** Both camera views were supplied to each model during every selected episode.

The video uses the same six successful examples as the per-task videos below. Each was selected as the successful run closest to its model/task cohort's median wall-clock duration. Output is **1568 × 1090**, H.264 MP4 at **40 fps**, lasting **33.35 seconds**; views are enlarged without cropping.

[Sources and hashes](astra_opus_tasks_0_1_4_static_grid_4x_sources.json) · [Verification](minimal_branded_replay_verification.json)

Rebuild with `wsl -d Ubuntu-24.04 -u root --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_minimal_branded_replay.py`.

## Per-task wrist and static videos

Each MP4 shows **Astra on top and Opus below**, with **wrist on the left and static on the right**. The two camera views touch; a 24-pixel gap separates the models. Both views in each row come from the same episode and advance together.

Playback is **4× recorded simulation motion**, with API waiting omitted. Shorter runs hold their ending frame, labelled with native 100% completion. These clips illustrate robot motion; the shared-clock videos below show API waiting and elapsed time.

| Task | Video | Astra run | Opus run | Duration |
|---|---|---:|---:|---:|
| 0 | [Wrist + static MP4](task0_astra_opus_wrist_static_4x.mp4) | 5 | 1 | 26.85 s |
| 1 | [Wrist + static MP4](task1_astra_opus_wrist_static_4x.mp4) | 1 | 3 | 27.15 s |
| 4 | [Wrist + static MP4](task4_astra_opus_wrist_static_4x.mp4) | 3 | 2 | 33.35 s |

Selection uses the successful run closest to the median wall-clock duration of each current five-run cohort. All six examples achieved native 100% completion. Output is 1024 × 1260, H.264 MP4 at 40 fps; original 224 × 224 views are enlarged without cropping. No new model requests were made.

[Video index](task_comparison_videos.json). Each video has accompanying `_sources.json` and `_verification.json` files documenting source hashes, camera synchronization and output checks.

Rebuild with `wsl -d Ubuntu-24.04 -u root --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_task_comparison_videos.py`.

## Shared-clock comparison with API waiting

[40x overview](astra_opus_tasks_0_1_4_wait_aware_40x.mp4) · [4x version](astra_opus_tasks_0_1_4_wait_aware_4x.mp4)

Rows are Tasks 0, 1 and 4; columns are Astra and Opus static cameras. All episodes start together on a shared elapsed-time clock. API waiting is visible as frozen images labelled `API WAIT`; completed runs hold their final frame labelled `DONE 100%`.

The earlier motion-only montage omitted API waiting, so shorter robot trajectories could finish sooner in video while taking longer in wall-clock time. This video reconstructs a waiting-aware timeline from recorded request latency and episode duration. Per-frame wall-clock timestamps were not recorded: movement uses the 10-Hz simulation rate and residual processing time is spread evenly before calls. Total episode durations and API wait durations match the logs; frame timing is approximate.

For each task/model, the selected successful run is closest to the median duration of the current five saved runs. All selected examples achieved native 100% completion, using state 0, seed 0 and max effort; Task 4 uses its retained run set.

| Task | Astra run | Astra wall time | Opus run | Opus wall time |
|---|---:|---:|---:|---:|
| 0 | 5 | 13:52 | 1 | 29:20 |
| 1 | 1 | 10:55 | 3 | 45:59 |
| 4 | 3 | 18:08 | 2 | 29:11 |

[Source timelines and hashes](wait_aware_sources.json) · [Verification](wait_aware_verification.json)

Rebuild with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_wait_aware_video.py`.
