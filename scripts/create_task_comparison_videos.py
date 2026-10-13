"""Create one wrist/static comparison MP4 per task from saved study episodes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess

import cv2

from create_study_montage import (
    WORKSPACE, TASKS, MODELS, MODEL_IDS, COLORS, draw_text, read_json, sha256, probe,
)

CAMERAS = (("wrist", "wrist_episode.mp4"), ("static", "episode.mp4"))
TILE, FPS, SPEED = 512, 40, 4
HEADER, BAND, ROW_GAP, FOOTER = 64, 58, 24, 32
WIDTH = 2 * TILE
HEIGHT = HEADER + 2 * (BAND + TILE) + ROW_GAP + FOOTER
MODEL_NAMES = {"astra": "GPT-6 Astra max", "opus": "Claude Opus 5.5 max"}
BACKGROUND = "0xf7f9fc"


def selected_sources(task):
    folder = WORKSPACE / "loho-study" / ("task " + str(task))
    pointer = read_json(folder / ("latest_task{}_comparison.json".format(task)))
    comparison = read_json(folder / pointer["comparison"])
    sources = []
    for row, model in enumerate(MODELS):
        cohort = next(item for item in comparison["models"] if item["model_id"] == MODEL_IDS[model])
        assert len(cohort["episodes"]) == 5
        median = statistics.median(item["elapsed_seconds"] for item in cohort["episodes"])
        episode = min((item for item in cohort["episodes"] if item["success"]),
                      key=lambda item: (abs(item["elapsed_seconds"] - median), item["trial"]))
        directory = folder / episode["directory"]
        verification = read_json(directory / "run_verification.json")
        summary = read_json(directory / "summary.json")
        assert verification["passed"] and verification["summary_sha256"] == sha256(directory / "summary.json")
        assert summary["success"] and summary["trial_score"]["completion_percent"] == 100
        assert summary["effort"] == "max" and summary["control_hz"] == 10
        assert summary["initial_state_id"] == summary["sim_seed"] == 0
        for column, (camera, filename) in enumerate(CAMERAS):
            path = directory / filename
            metadata = probe(path)
            assert metadata["frames"] == summary["simulator_action_steps"] + 1
            assert metadata["width"] == metadata["height"] == 224 and metadata["fps"] == 10
            sources.append({
                "task_id": task, "model": model, "model_id": MODEL_IDS[model],
                "display_trial": episode["trial"], "camera": camera, "row": row, "column": column,
                "source_file": str(path.relative_to(WORKSPACE)), "source_sha256": sha256(path),
                "source_summary_sha256": verification["summary_sha256"],
                "success": True, "completion_percent": 100,
                "elapsed_seconds": summary["elapsed_seconds"], "cohort_median_elapsed_seconds": median,
                "action_steps": summary["simulator_action_steps"], "source_video": metadata,
                "playback_end_seconds": metadata["frames"] / FPS,
                "tile_x": column * TILE,
                "tile_y": HEADER + BAND + row * (BAND + TILE + ROW_GAP),
            })
    assert len(sources) == 4
    for row in range(2):
        pair = [source for source in sources if source["row"] == row]
        assert pair[0]["source_video"]["frames"] == pair[1]["source_video"]["frames"]
        assert pair[1]["tile_x"] == pair[0]["tile_x"] + TILE
    return sources


def encode_task(task, out):
    sources = selected_sources(task)
    prefix = "task{}_astra_opus_wrist_static_4x".format(task)
    output = out / (prefix + ".mp4")
    temporary = out / (prefix + ".encoding.mp4")
    target_frames = max(source["source_video"]["frames"] for source in sources) + 60
    target_seconds = target_frames / FPS
    inputs, filters, layout = [], [], []
    for index, source in enumerate(sources):
        inputs += ["-threads", "1", "-i", str(WORKSPACE / source["source_file"])]
        filters.append(
            "[{}:v]setpts=(PTS-STARTPTS)/{},fps={}:round=near,scale={}:{}:flags=lanczos,"
            "setsar=1,tpad=stop_mode=clone:stop_duration={:.6f},trim=end_frame={},"
            "setpts=N/({}*TB)[v{}]".format(
                index, SPEED, FPS, TILE, TILE, target_seconds, target_frames, FPS, index))
        layout.append("{}_{}".format(source["tile_x"], source["tile_y"]))
    filters.append(
        "[v0][v1][v2][v3]xstack=inputs=4:layout={}:fill={}:shortest=1,"
        "pad={}:{}:0:0:color={}[grid]".format("|".join(layout), BACKGROUND, WIDTH, HEIGHT, BACKGROUND))
    overlays = [draw_text("LIBERO-LoHo | Task {} | 4x simulation replay".format(task), 16, 20, 27, bold=True)]
    for row, model in enumerate(MODELS):
        source = next(item for item in sources if item["model"] == model)
        band_y = source["tile_y"] - BAND
        ending = "gte(t,{:.6f})".format(source["playback_end_seconds"])
        end_y = source["tile_y"] + TILE - 36
        overlays += [
            "drawbox=x=0:y={}:w={}:h={}:color={}:t=fill".format(band_y, WIDTH, BAND, COLORS[model]),
            draw_text("{} | Run {}".format(MODEL_NAMES[model], source["display_trial"]),
                      "(w-text_w)/2", band_y + 6, 24, color="white", bold=True),
            draw_text("Wrist camera", "({}-text_w)/2".format(TILE), band_y + 36, 16, color="white"),
            draw_text("Static camera", "{}+({}-text_w)/2".format(TILE, TILE), band_y + 36, 16, color="white"),
            "drawbox=x=0:y={}:w={}:h=36:color=black@0.8:t=fill:enable='{}'".format(end_y, WIDTH, ending),
            draw_text("END | Native goal completion 100%", "(w-text_w)/2", end_y + 8,
                      20, color="white", enable=ending),
        ]
    overlays.append(draw_text("API waiting omitted | Shorter runs hold their final frame", 16, HEIGHT - 25, 18))
    filters.append("[grid]{}[final]".format(",".join(overlays)))
    graph_path = out / (prefix + "_filter.txt")
    graph_path.write_text(";\n".join(filters), encoding="utf-8")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", "2"] + inputs + [
        "-filter_complex_script", str(graph_path), "-map", "[final]", "-an", "-frames:v", str(target_frames),
        "-r", str(FPS), "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)]
    print("Encoding Task {} | {} frames | {:.2f}s | {}x{}".format(task, target_frames, target_seconds, WIDTH, HEIGHT), flush=True)
    with (out / (prefix + "_encoding.log")).open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    metadata = probe(temporary)
    assert metadata["frames"] == target_frames and metadata["fps"] == FPS
    assert metadata["width"] == WIDTH and metadata["height"] == HEIGHT
    assert metadata["codec_name"] == "h264" and metadata["pix_fmt"] == "yuv420p"
    assert abs(metadata["duration_seconds"] - target_seconds) < .03
    for source in sources:
        assert source["source_sha256"] == sha256(WORKSPACE / source["source_file"])
        summary_path = (WORKSPACE / source["source_file"]).parent / "summary.json"
        assert source["source_summary_sha256"] == sha256(summary_path)
    temporary.replace(output)
    review_dir = WORKSPACE / "setup_logs/task_video_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(output))
    for label, frame in (("start", 0), ("middle", target_frames // 2), ("ending", target_frames - 1)):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, pixels = capture.read()
        assert ok and pixels.shape[:2] == (HEIGHT, WIDTH)
        cv2.imwrite(str(review_dir / ("task{}_{}.jpg".format(task, label))), pixels, [cv2.IMWRITE_JPEG_QUALITY, 95])
    capture.release()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "task_id": task,
        "selection": "Successful run closest to the median wall-clock duration of each current five-run cohort.",
        "layout": "Top Astra, bottom Opus; left wrist, right static; no column gap; 24-pixel gap between model rows.",
        "column_gap_pixels": 0, "model_row_gap_pixels": ROW_GAP,
        "speed_multiplier": SPEED, "time_basis": "Recorded 10-Hz simulation frames; API waiting omitted.",
        "ending": "Shorter clips hold their final frame. Both cameras in each row are from the same episode and synchronized.",
        "resolution": [WIDTH, HEIGHT], "fps": FPS, "duration_seconds": target_seconds,
        "output_file": output.name, "sources": sources,
    }
    (out / (prefix + "_sources.json")).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verification = {
        "passed": True, "output_sha256": sha256(output), "output_video": metadata,
        "source_videos_and_summaries_sha256_unchanged": True,
        "selected_episodes": 2, "camera_views": 4, "successes": 2,
        "column_gap_pixels": 0, "model_row_gap_pixels": ROW_GAP,
        "camera_pairs_same_episode_and_frame_count": True,
    }
    (out / (prefix + "_verification.json")).write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"task": task, "video": output.name, "verified": True,
                      "duration_seconds": target_seconds, "size_bytes": output.stat().st_size}), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=WORKSPACE / "loho-study/videos")
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = [encode_task(task, out) for task in TASKS]
    (out / "task_comparison_videos.json").write_text(json.dumps({
        "tasks": list(TASKS), "videos": [item["output_file"] for item in results],
        "examples": 6, "camera_views": 12, "source_data_unchanged": True,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
