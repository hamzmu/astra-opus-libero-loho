"""Combine the per-task examples into a static-camera grid at 4x motion speed."""
from datetime import datetime, timezone
import json
import subprocess

import cv2

from create_study_montage import WORKSPACE, TASKS, MODELS, COLORS, draw_text, read_json, sha256, probe

OUT = WORKSPACE / "loho-study/videos"
PREFIX = "astra_opus_tasks_0_1_4_static_grid_4x"
TILE, COLUMN_GAP, ROW_GAP, FPS, SPEED = 512, 16, 24, 40, 4
HEADER, TASK_BAND, MODEL_BAND, FOOTER = 112, 44, 42, 32
WIDTH = 3 * TILE + 2 * COLUMN_GAP
HEIGHT = HEADER + TASK_BAND + 2 * (MODEL_BAND + TILE) + ROW_GAP + FOOTER
BACKGROUND = "0xf7f9fc"
CAMERA_NOTE = "Wrist camera view omitted from video but used in evaluation"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    for column, task in enumerate(TASKS):
        manifest = read_json(OUT / ("task{}_astra_opus_wrist_static_4x_sources.json".format(task)))
        for row, model in enumerate(MODELS):
            source = dict(next(item for item in manifest["sources"] if item["model"] == model and item["camera"] == "static"))
            path = WORKSPACE / source["source_file"]
            summary = read_json(path.parent / "summary.json")
            assert source["source_sha256"] == sha256(path)
            assert source["source_summary_sha256"] == sha256(path.parent / "summary.json")
            assert summary["success"] and summary["trial_score"]["completion_percent"] == 100
            assert summary["cameras"] == ["agentview", "robot0_eye_in_hand"]
            metadata = probe(path)
            assert metadata["width"] == metadata["height"] == 224 and metadata["fps"] == 10
            assert metadata["frames"] == summary["simulator_action_steps"] + 1
            source.update(row=row, column=column, source_video=metadata,
                          tile_x=column * (TILE + COLUMN_GAP),
                          tile_y=HEADER + TASK_BAND + MODEL_BAND + row * (MODEL_BAND + TILE + ROW_GAP),
                          playback_end_seconds=metadata["frames"] / FPS,
                          evaluation_cameras=summary["cameras"])
            sources.append(source)
    assert len(sources) == 6
    frames = max(source["source_video"]["frames"] for source in sources) + 60
    seconds = frames / FPS
    inputs, filters, layouts = [], [], []
    for index, source in enumerate(sources):
        inputs += ["-threads", "1", "-i", str(WORKSPACE / source["source_file"])]
        ending = "gte(t,{:.6f})".format(source["playback_end_seconds"])
        filters.append(
            "[{}:v]setpts=(PTS-STARTPTS)/{},fps={}:round=near,scale={}:{}:flags=lanczos,"
            "setsar=1,tpad=stop_mode=clone:stop_duration={:.6f},trim=end_frame={},setpts=N/({}*TB),"
            "drawbox=x=0:y=0:w={}:h=32:color=black@0.7:t=fill,{},"
            "drawbox=x=0:y={}:w={}:h=36:color=black@0.8:t=fill:enable='{}',{}[v{}]".format(
                index, SPEED, FPS, TILE, TILE, seconds, frames, FPS, TILE,
                draw_text("Run {}".format(source["display_trial"]), 12, 7, 19, color="white"),
                TILE - 36, TILE, ending,
                draw_text("END | Goal completion 100%", "(w-text_w)/2", TILE - 28,
                          20, color="white", enable=ending), index))
        layouts.append("{}_{}".format(source["tile_x"], source["tile_y"]))
    filters.append("{}xstack=inputs=6:layout={}:fill={}:shortest=1,pad={}:{}:0:0:color={}[grid]".format(
        "".join("[v{}]".format(index) for index in range(6)), "|".join(layouts), BACKGROUND, WIDTH, HEIGHT, BACKGROUND))
    overlays = [
        draw_text("LIBERO-LoHo | Astra vs Opus | 4x simulation replay", 16, 20, 34, bold=True),
        draw_text("Static camera views | " + CAMERA_NOTE, 16, 72, 23),
    ]
    for column, task in enumerate(TASKS):
        overlays.append(draw_text("Task {}".format(task),
                                  "{}+({}-text_w)/2".format(column * (TILE + COLUMN_GAP), TILE),
                                  HEADER + 11, 24, bold=True))
    for row, model in enumerate(MODELS):
        source = next(item for item in sources if item["model"] == model)
        band_y = source["tile_y"] - MODEL_BAND
        name = "GPT-6 Astra max" if model == "astra" else "Claude Opus 5.5 max"
        overlays += [
            "drawbox=x=0:y={}:w={}:h={}:color={}:t=fill".format(band_y, WIDTH, MODEL_BAND, COLORS[model]),
            draw_text(name, "(w-text_w)/2", band_y + 9, 24, color="white", bold=True),
        ]
    overlays.append(draw_text("API waiting omitted | Shorter runs hold their final frame | All examples reached native 100% completion", 16, HEIGHT - 25, 19))
    filters.append("[grid]{}[final]".format(",".join(overlays)))
    graph_path = OUT / (PREFIX + "_filter.txt")
    graph_path.write_text(";\n".join(filters), encoding="utf-8")
    output = OUT / (PREFIX + ".mp4")
    temporary = OUT / (PREFIX + ".encoding.mp4")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", "2"] + inputs + [
        "-filter_complex_script", str(graph_path), "-map", "[final]", "-an", "-frames:v", str(frames),
        "-r", str(FPS), "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)]
    print("Encoding {} views | {} frames | {:.2f}s | {}x{}".format(len(sources), frames, seconds, WIDTH, HEIGHT), flush=True)
    with (OUT / (PREFIX + "_encoding.log")).open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    metadata = probe(temporary)
    assert metadata["frames"] == frames and metadata["fps"] == FPS
    assert metadata["width"] == WIDTH and metadata["height"] == HEIGHT
    assert metadata["codec_name"] == "h264" and metadata["pix_fmt"] == "yuv420p"
    assert abs(metadata["duration_seconds"] - seconds) < .03
    for source in sources:
        path = WORKSPACE / source["source_file"]
        assert sha256(path) == source["source_sha256"]
        assert sha256(path.parent / "summary.json") == source["source_summary_sha256"]
    temporary.replace(output)
    review_dir = WORKSPACE / "setup_logs/static_task_grid_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(output))
    for label, frame in (("start", 0), ("middle", frames // 2), ("ending", frames - 1)):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, pixels = capture.read()
        assert ok and pixels.shape[:2] == (HEIGHT, WIDTH)
        cv2.imwrite(str(review_dir / (label + ".jpg")), pixels, [cv2.IMWRITE_JPEG_QUALITY, 95])
    capture.release()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "output_file": output.name,
        "tasks": list(TASKS), "layout": "Rows Astra / Opus; columns Task 0 / Task 1 / Task 4.",
        "camera": "static only", "camera_note": CAMERA_NOTE,
        "selection": "Same successful examples as the per-task videos; successful run closest to each cohort's median wall-clock duration.",
        "speed_multiplier": SPEED, "time_basis": "Recorded 10-Hz simulation motion; API waiting omitted.",
        "duration_seconds": seconds, "fps": FPS, "resolution": [WIDTH, HEIGHT],
        "ending": "Clips start together; shorter clips hold their final frame.", "sources": sources,
    }
    (OUT / (PREFIX + "_sources.json")).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verification = {
        "passed": True, "output_sha256": sha256(output), "output_video": metadata,
        "source_videos_and_summaries_sha256_unchanged": True, "static_views": 6,
        "selected_episodes": 6, "native_successes": 6,
        "wrist_and_static_used_in_all_selected_evaluations": True,
        "same_examples_as_per_task_videos": True,
    }
    (OUT / (PREFIX + "_verification.json")).write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"video": str(output), "verified": True, "duration_seconds": seconds,
                      "size_bytes": output.stat().st_size}), flush=True)


if __name__ == "__main__":
    main()
