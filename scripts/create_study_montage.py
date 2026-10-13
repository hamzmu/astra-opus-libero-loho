"""Compose run-1 static/wrist videos for three tasks and two models at 4x."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

import cv2

WORKSPACE = Path(__file__).resolve().parents[1]
TASKS = (0, 1, 4)
MODELS = ("astra", "opus")
MODEL_IDS = {"astra": "gpt-6-astra", "opus": "claude-opus-5-5"}
CAMERAS = (("static", "episode.mp4"), ("wrist", "wrist_episode.mp4"))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
COLORS = {"astra": "0x1f77b4", "opus": "0xff7f0e"}
GOALS = {
    0: "Task 0 | Front butter and pudding into top drawer; close drawer",
    1: "Task 1 | Soup, butter and tomato sauce into basket",
    4: "Task 4 | Back butter and pudding in drawer; close drawer; bowl on cabinet",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames,codec_name,pix_fmt:format=duration",
                             "-of", "json", str(path)], check=True, text=True, capture_output=True)
    value = json.loads(result.stdout)
    stream = value["streams"][0]
    return dict(stream, duration_seconds=float(value["format"]["duration"]),
                fps=float(Fraction(stream["avg_frame_rate"])), frames=int(stream["nb_read_frames"]))


def draw_text(text, x, y, size=22, color="0x202830", bold=False, enable=None):
    assert "'" not in text and ":" not in text
    result = "drawtext=fontfile={}:text='{}':expansion=none:fontsize={}:fontcolor={}:x={}:y={}".format(
        BOLD if bold else FONT, text, size, color, x, y)
    if enable:
        result += ":enable='{}'".format(enable)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=WORKSPACE / "loho-study/videos")
    parser.add_argument("--cameras", choices=("both", "static"), default="both")
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    static_only = args.cameras == "static"
    cameras = CAMERAS[:1] if static_only else CAMERAS
    suffix = "static_4x" if static_only else "4x"
    output = out / ("astra_opus_tasks_0_1_4_run1_" + suffix + ".mp4")
    temporary = output.with_name(output.stem + ".encoding.mp4")
    metadata_prefix = "static_montage" if static_only else "montage"
    sources = []
    for row, task in enumerate(TASKS):
        folder = WORKSPACE / "loho-study" / ("task " + str(task))
        pointer = read_json(folder / ("latest_task{}_comparison.json".format(task)))
        comparison = read_json(folder / pointer["comparison"])
        for model_index, model in enumerate(MODELS):
            cohort = next(item for item in comparison["models"] if item["model_id"] == MODEL_IDS[model])
            assert cohort["trials"] == 5
            episode = next(item for item in cohort["episodes"] if item["trial"] == 1)
            directory = folder / episode["directory"]
            verification = read_json(directory / "run_verification.json")
            assert verification["passed"] and verification["summary_sha256"] == sha256(directory / "summary.json")
            for camera_index, (camera, filename) in enumerate(cameras):
                path = directory / filename
                metadata = probe(path)
                assert metadata["frames"] == episode["action_steps"] + 1
                assert metadata["width"] == metadata["height"] == 224 and metadata["fps"] == 10
                sources.append({"task_id": task, "model": model, "model_id": MODEL_IDS[model],
                                "display_trial": 1, "camera": camera, "row": row,
                                "column": model_index * len(cameras) + camera_index,
                                "source_file": str(path.relative_to(WORKSPACE)), "source_sha256": sha256(path),
                                "source_summary_sha256": verification["summary_sha256"],
                                "completion_percent": episode["completion_percent"], "success": episode["success"],
                                "termination_reason": episode["termination_reason"], "source_video": metadata,
                                "playback_end_seconds": metadata["frames"] / 40})
    view_count = len(TASKS) * len(MODELS) * len(cameras)
    assert len(sources) == view_count
    target_frames = max(item["source_video"]["frames"] for item in sources) + 60
    target_seconds = target_frames / 40
    width, height, tile = (1024 if static_only else 1920), 1712, 432
    filters, layouts, arguments = [], [], []
    for index, source in enumerate(sources):
        arguments += ["-threads", "1", "-i", str(WORKSPACE / source["source_file"])]
        ending = "gte(t,{:.6f})".format(source["playback_end_seconds"])
        caption = "END | final score {:.1f}%".format(source["completion_percent"])
        filters.append("[{}:v]setpts=(PTS-STARTPTS)/4,fps=40:round=near,scale={}:{}:flags=lanczos,setsar=1,"
                       "tpad=stop_mode=clone:stop_duration={:.6f},trim=end_frame={},setpts=N/(40*TB),"
                       "drawbox=x=0:y={}:w={}:h=36:color=black@0.80:t=fill:enable='{}',{}[v{}]".format(
                           index, tile, tile, target_seconds, target_frames, tile - 36, tile, ending,
                           draw_text(caption, 12, tile - 28, size=20, color="white", enable=ending), index))
        layouts.append("{}_{}".format(72 + source["column"] * 448, 216 + source["row"] * 492))
    filters.append("{}xstack=inputs={}:layout={}:fill=0xf7f9fc:shortest=1,"
                   "pad={}:{}:0:0:color=0xf7f9fc[grid]".format(
                       "".join("[v{}]".format(index) for index in range(view_count)), view_count, "|".join(layouts), width, height))
    overlays = [
        draw_text("LIBERO-LoHo | Astra vs Opus", 72, 22, 35, bold=True),
        draw_text("Static cameras | 4x playback | Run 1 per model/task" if static_only else
                  "12 synchronized views | 4x simulation playback | Run 1 per model and task", 72, 72, 20),
    ]
    column_labels = ("Astra | Static camera", "Opus | Static camera") if static_only else (
        "Astra | Static camera", "Astra | Wrist camera", "Opus | Static camera", "Opus | Wrist camera")
    for column, label in enumerate(column_labels):
        x = 72 + column * 448
        color = COLORS["astra" if column < len(cameras) else "opus"]
        overlays += ["drawbox=x={}:y=114:w=432:h=42:color={}:t=fill".format(x, color),
                     draw_text(label, x + 16, 124, size=22, color="white", bold=True)]
    for row, task in enumerate(TASKS):
        short_goals = {
            0: "Task 0 | Front butter + pudding in drawer; close drawer",
            1: "Task 1 | Soup + butter + tomato sauce in basket",
            4: "Task 4 | Back butter + pudding in drawer; close; bowl on cabinet",
        }
        overlays.append(draw_text(short_goals[task] if static_only else GOALS[task], 72, 180 + row * 492, size=23, bold=True))
    if static_only:
        overlays += [draw_text("Final frames hold when a run ends.", 72, 1658, size=17),
                     draw_text("Recorded motion only; API waiting time is omitted.", 72, 1684, size=17)]
    else:
        overlays.append(draw_text("Final frames hold after each run ends | Recorded motion only; API waiting time is omitted", 72, 1672, size=18))
    filters.append("[grid]{}[final]".format(",".join(overlays)))
    graph_path = out / (metadata_prefix + "_filter.txt")
    graph_path.write_text(";\n".join(filters), encoding="utf-8")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", "2"] + arguments + [
        "-filter_complex_script", str(graph_path), "-map", "[final]", "-an", "-frames:v", str(target_frames),
        "-r", "40", "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(temporary)]
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "selection": "Display run 1 from each current five-run cohort, without outcome-based selection.",
                "tasks": list(TASKS), "run_per_task_model": 1, "examples": 6, "views": view_count, "speed_multiplier": 4,
                "fps": 40, "output_frames": target_frames, "duration_seconds": target_seconds,
                "resolution": [width, height], "tile_resolution": [tile, tile],
                "layout": "Rows Task 0 / Task 1 / Task 4; columns Astra static / Opus static." if static_only else
                          "Rows Task 0 / Task 1 / Task 4; columns Astra static / Astra wrist / Opus static / Opus wrist.",
                "time_basis": "4x recorded simulation-motion frames. API waits were omitted in the original recordings. Clips start together; shorter clips hold their ending frame.",
                "sources": sources, "output_file": output.name}
    (out / (metadata_prefix + "_sources.json")).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Encoding {} views, {} frames, {:.3f}s at 4x, {}x{}".format(view_count, target_frames, target_seconds, width, height), flush=True)
    with (out / (metadata_prefix + "_encoding.log")).open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True)
        for line in process.stdout:
            if line.startswith(("frame=", "out_time=", "speed=", "progress=")):
                print(line.rstrip(), flush=True)
        return_code = process.wait()
    if return_code:
        raise RuntimeError("FFmpeg failed; inspect " + str(out / (metadata_prefix + "_encoding.log")))
    metadata = probe(temporary)
    assert metadata["frames"] == target_frames and metadata["fps"] == 40
    assert metadata["width"] == width and metadata["height"] == height
    assert metadata["codec_name"] == "h264" and metadata["pix_fmt"] == "yuv420p"
    assert abs(metadata["duration_seconds"] - target_seconds) < .03
    for source in sources:
        assert source["source_sha256"] == sha256(WORKSPACE / source["source_file"])
    temporary.replace(output)
    review_dir = WORKSPACE / ("setup_logs/montage_review_static" if static_only else "setup_logs/montage_review")
    review_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(output))
    for label, frame in (("start", 0), ("middle", target_frames // 2), ("ending", target_frames - 1)):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, pixels = capture.read()
        assert ok
        cv2.imwrite(str(review_dir / (label + ".jpg")), pixels, [cv2.IMWRITE_JPEG_QUALITY, 95])
    capture.release()
    verification = {"passed": True, "output_video": metadata, "output_sha256": sha256(output),
                    "source_videos_sha256_unchanged": True, "selected_examples": 6, "simultaneous_camera_views": view_count,
                    "speed_multiplier": 4, "notes": "End-score tags appear when a run finishes; every clip's final frame is held to the shared ending."}
    (out / (metadata_prefix + "_verification.json")).write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    lines = ["# Astra and Opus video comparison", "", "[Combined MP4](" + output.name + ")", "",
             "{} simultaneous camera views at **4x simulation speed**, using run 1 for each model on Tasks 0, 1 and 4.".format(view_count), "",
             "Rows are Task 0, Task 1 and Task 4. Columns are {}. All clips start together, and shorter clips hold their final frame. End tags show native final goal completion. Playback uses recorded motion frames; API waiting time is omitted.".format(
                 "Astra static and Opus static" if static_only else "Astra static, Astra wrist, Opus static and Opus wrist"), "",
             "| Task | Astra run | Astra final score | Opus run | Opus final score |", "|---|---:|---:|---:|---:|"]
    for task in TASKS:
        scores = [next(source["completion_percent"] for source in sources if source["task_id"] == task and source["model"] == model) for model in MODELS]
        lines.append("| {} | 1 | {:.1f}% | 1 | {:.1f}% |".format(task, *scores))
    lines += ["", "Output: **{} x {}**, H.264 MP4, 40 fps, **{:.3f} seconds**. Native 224 x 224 views are enlarged without cropping. The longest clip also holds its final frame for 1.5 seconds.".format(width, height, target_seconds), "",
              "[Source selection, timings and hashes]({}_sources.json) · [Verification]({}_verification.json)".format(metadata_prefix, metadata_prefix), "",
              "Rebuild from the workspace with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_study_montage.py --cameras {}`.".format(args.cameras), ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(output), "verified": True, "views": view_count, "examples": 6,
                      "fps": 40, "duration_seconds": target_seconds, "size_bytes": output.stat().st_size}), flush=True)


if __name__ == "__main__":
    main()
