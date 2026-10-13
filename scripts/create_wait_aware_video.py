"""Reconstruct waiting-aware static-camera comparisons without new model calls."""
import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import subprocess
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from create_study_montage import WORKSPACE, TASKS, MODELS, MODEL_IDS, FONT, BOLD, read_json, sha256, probe

WIDTH, HEIGHT, TILE, FPS = 1024, 1920, 432, 20
BLUE, ORANGE = (31, 119, 180), (255, 127, 14)
GOALS = {
    0: "Task 0 | Front butter + pudding in drawer; close drawer",
    1: "Task 1 | Soup + butter + tomato sauce in basket",
    4: "Task 4 | Back butter + pudding in drawer; close; bowl on cabinet",
}


def clock(seconds):
    seconds = max(0, int(seconds))
    return "{:02d}:{:02d}".format(seconds // 60, seconds % 60)


def choose_sources():
    sources = []
    for row, task in enumerate(TASKS):
        folder = WORKSPACE / "loho-study" / ("task " + str(task))
        pointer = read_json(folder / ("latest_task{}_comparison.json".format(task)))
        comparison = read_json(folder / pointer["comparison"])
        for column, model in enumerate(MODELS):
            cohort = next(item for item in comparison["models"] if item["model_id"] == MODEL_IDS[model])
            assert len(cohort["episodes"]) == 5
            median = statistics.median(item["elapsed_seconds"] for item in cohort["episodes"])
            chosen = min((item for item in cohort["episodes"] if item["success"]),
                         key=lambda item: (abs(item["elapsed_seconds"] - median), item["trial"]))
            directory = folder / chosen["directory"]
            report = read_json(directory / "summary.json")
            verified = read_json(directory / "run_verification.json")
            assert verified["passed"] and verified["summary_sha256"] == sha256(directory / "summary.json")
            assert report["success"] and report["trial_score"]["completion_percent"] == 100
            assert report["control_hz"] == 10 and report["effort"] == "max"
            assert report["initial_state_id"] == report["sim_seed"] == 0
            assert len(report["api_attempts"]) == len(report["decisions"])
            steps = report["simulator_action_steps"]
            movement_seconds = steps / report["control_hz"]
            overhead = report["elapsed_seconds"] - report["total_api_latency_seconds"] - movement_seconds
            assert overhead >= 0
            overhead_per_call = overhead / len(report["api_attempts"])
            decisions = {decision["attempt_id"]: decision for decision in report["decisions"]}
            phases, cursor, frame = [], 0.0, 0
            for call_number, attempt in enumerate(report["api_attempts"], 1):
                decision = decisions[attempt["attempt_id"]]
                latency = attempt["api_latency_seconds"]
                executed = decision["executed_steps"]
                for phase_name, duration, count in (("PROCESSING", overhead_per_call, 0),
                                                     ("API WAIT", latency, 0),
                                                     ("MOVING", executed / report["control_hz"], executed)):
                    if duration > 0:
                        phases.append({"phase": phase_name, "start_seconds": cursor,
                                       "end_seconds": cursor + duration, "start_frame": frame,
                                       "action_steps": count, "call": call_number})
                        cursor += duration
                        frame += count
            assert frame == steps and abs(cursor - report["elapsed_seconds"]) < 1e-7
            video = directory / "episode.mp4"
            metadata = probe(video)
            assert metadata["frames"] == steps + 1 and metadata["fps"] == 10
            sources.append({"task_id": task, "model": model, "model_id": MODEL_IDS[model],
                            "display_trial": chosen["trial"], "row": row, "column": column,
                            "source_file": str(video.relative_to(WORKSPACE)), "source_sha256": sha256(video),
                            "source_summary_sha256": verified["summary_sha256"],
                            "cohort_median_elapsed_seconds": median, "elapsed_seconds": report["elapsed_seconds"],
                            "api_latency_seconds": report["total_api_latency_seconds"],
                            "simulation_motion_seconds": movement_seconds, "other_processing_seconds": overhead,
                            "api_calls": report["decisions_used"], "action_steps": steps,
                            "completion_percent": 100, "phases": phases})
    assert len(sources) == 6
    return sources


class Camera:
    def __init__(self, source):
        self.source = source
        self.capture = cv2.VideoCapture(str(WORKSPACE / source["source_file"]))
        self.ends = [phase["end_seconds"] for phase in source["phases"]]
        self.index = -1
        self.pixels = None

    def at(self, seconds):
        if seconds >= self.source["elapsed_seconds"]:
            target, phase, call = self.source["action_steps"], "DONE 100%", self.source["api_calls"]
        else:
            event = self.source["phases"][bisect_right(self.ends, seconds)]
            target = event["start_frame"]
            if event["phase"] == "MOVING":
                target += min(event["action_steps"], int((seconds - event["start_seconds"]) * 10))
            phase, call = event["phase"], event["call"]
        assert target >= self.index
        if target != self.index:
            while self.index < target:
                ok, frame = self.capture.read()
                assert ok, (self.source["source_file"], target, self.index)
                self.index += 1
            self.pixels = cv2.resize(frame, (TILE, TILE), interpolation=cv2.INTER_LANCZOS4)
        return self.pixels, phase, call


def base_canvas(sources, speed):
    image = Image.new("RGB", (WIDTH, HEIGHT), (247, 249, 252))
    draw = ImageDraw.Draw(image)
    font = lambda size, bold=False: ImageFont.truetype(BOLD if bold else FONT, size)
    draw.text((72, 18), "LIBERO-LoHo | Astra vs Opus", fill=(32, 40, 48), font=font(35, True))
    draw.text((72, 72), "{}x reconstructed wall-clock playback | Static cameras".format(speed),
              fill=(32, 40, 48), font=font(22))
    for column, model in enumerate(MODELS):
        x = 72 + column * 448
        draw.rectangle((x, 152, x + TILE, 194), fill=BLUE if model == "astra" else ORANGE)
        draw.text((x + 16, 160), ("Astra" if model == "astra" else "Opus") + " | Static camera",
                  fill="white", font=font(23, True))
    for row, task in enumerate(TASKS):
        draw.text((72, 208 + row * 552), GOALS[task], fill=(32, 40, 48), font=font(23, True))
    for source in sources:
        x, y = 72 + source["column"] * 448, 243 + source["row"] * 552
        text = "Run {} | total {} | API {}".format(source["display_trial"], clock(source["elapsed_seconds"]), clock(source["api_latency_seconds"]))
        draw.text((x, y), text, fill=(58, 68, 79), font=font(18))
    draw.text((72, 1852), "API wait durations and total elapsed time come from run logs.", fill=(70, 80, 90), font=font(17))
    draw.text((72, 1879), "Motion timing uses 10 Hz; other processing time is distributed.", fill=(70, 80, 90), font=font(17))
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def encode(sources, speed, out):
    duration = max(source["elapsed_seconds"] for source in sources) / speed + 1.5
    frame_count = math.ceil(duration * FPS)
    name = "astra_opus_tasks_0_1_4_wait_aware_{}x.mp4".format(speed)
    temporary = out / (name[:-4] + ".encoding.mp4")
    canvas = base_canvas(sources, speed)
    cameras = [Camera(source) for source in sources]
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", "{}x{}".format(WIDTH, HEIGHT), "-r", str(FPS), "-i", "pipe:0", "-an",
               "-c:v", "libx264", "-threads", "4", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(temporary)]
    print("ENCODE {}x | {} frames | {:.2f}s".format(speed, frame_count, frame_count / FPS), flush=True)
    began = time.monotonic()
    with (out / (name[:-4] + "_encoding.log")).open("w") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
        try:
            for index in range(frame_count):
                seconds = index / FPS * speed
                frame = canvas.copy()
                cv2.putText(frame, "Elapsed wall clock  " + clock(min(seconds, max(s["elapsed_seconds"] for s in sources))),
                            (72, 128), cv2.FONT_HERSHEY_SIMPLEX, .86, (48, 40, 32), 2, cv2.LINE_AA)
                for camera in cameras:
                    pixels, phase, call = camera.at(seconds)
                    source = camera.source
                    x, y = 72 + source["column"] * 448, 288 + source["row"] * 552
                    frame[y:y + TILE, x:x + TILE] = pixels
                    color = (51, 137, 36) if phase == "DONE 100%" else ((50, 90, 145) if phase == "API WAIT" else (70, 70, 70))
                    cv2.rectangle(frame, (x, y - 26), (x + TILE, y - 2), color, -1)
                    label = "{} | call {}/{} | {}".format(phase, call, source["api_calls"], clock(min(seconds, source["elapsed_seconds"])))
                    cv2.putText(frame, label, (x + 6, y - 8), cv2.FONT_HERSHEY_SIMPLEX, .49, (255, 255, 255), 1, cv2.LINE_AA)
                process.stdin.write(frame.tobytes())
                if index and index % 500 == 0:
                    print("{}x {}/{} frames ({:.0f}%)".format(speed, index, frame_count, index / frame_count * 100), flush=True)
            process.stdin.close()
            code = process.wait()
            if code:
                raise RuntimeError("FFmpeg failed; inspect encoding log")
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            for camera in cameras:
                camera.capture.release()
    metadata = probe(temporary)
    assert metadata["frames"] == frame_count and metadata["fps"] == FPS
    assert metadata["width"] == WIDTH and metadata["height"] == HEIGHT
    temporary.replace(out / name)
    review = WORKSPACE / "setup_logs/wait_aware_review"
    review.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(out / name))
    for label, seconds in (("start", 0), ("astra_finished", 1100 / speed), ("ending", (frame_count - 1) / FPS)):
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, pixels = capture.read()
        assert ok
        cv2.imwrite(str(review / ("{}_{}x.jpg".format(label, speed))), pixels, [cv2.IMWRITE_JPEG_QUALITY, 95])
    capture.release()
    result = {"file": name, "speed": speed, "metadata": metadata, "sha256": sha256(out / name),
              "render_seconds": time.monotonic() - began, "size_bytes": (out / name).stat().st_size}
    print("FINISH " + json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speeds", nargs="+", type=int, default=[40, 4])
    parser.add_argument("--outdir", type=Path, default=WORKSPACE / "loho-study/videos")
    args = parser.parse_args()
    assert all(speed > 0 for speed in args.speeds)
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sources = choose_sources()
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "examples": 6, "views": "static only",
                "selection": "Successful run closest to the median wall-clock duration of each current five-run cohort; no fastest-Astra/slowest-Opus selection.",
                "timing": "Reconstructed, not a captured wall-clock recording. Each recorded API request latency is inserted as an exact-duration freeze. Motion frames advance at the recorded 10-Hz simulation rate. Remaining elapsed time is distributed equally as processing before each call. Total endpoints match recorded episode elapsed_seconds.",
                "sources": sources}
    (out / "wait_aware_sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for source in sources:
        print("SELECT Task {} {} run {} | wall {} | API {} | motion {:.1f}s".format(
            source["task_id"], source["model"], source["display_trial"], clock(source["elapsed_seconds"]),
            clock(source["api_latency_seconds"]), source["simulation_motion_seconds"]), flush=True)
    outputs = [encode(sources, speed, out) for speed in args.speeds]
    assert all(sha256(WORKSPACE / source["source_file"]) == source["source_sha256"] for source in sources)
    verified = {"passed": True, "timing_reconstructed": True, "six_static_views": True,
                "source_videos_unchanged": True, "api_waits_match_recorded_latencies": True,
                "elapsed_endpoints_match_run_summaries": True, "outputs": outputs}
    (out / "wait_aware_verification.json").write_text(json.dumps(verified, indent=2) + "\n")
    lines = ["# Astra and Opus: waiting-aware video", "",
             "[40x overview](astra_opus_tasks_0_1_4_wait_aware_40x.mp4) · [4x version](astra_opus_tasks_0_1_4_wait_aware_4x.mp4)", "",
             "Rows are Tasks 0, 1 and 4; columns are Astra and Opus static cameras. All episodes start together on a shared elapsed-time clock. API waiting is visible as frozen images labelled `API WAIT`; completed runs hold their final frame labelled `DONE 100%`.", "",
             "The earlier motion-only montage omitted API waiting, so shorter robot trajectories could finish sooner in video while taking longer in wall-clock time. This video reconstructs a waiting-aware timeline from recorded request latency and episode duration. Per-frame wall-clock timestamps were not recorded: movement uses the 10-Hz simulation rate and residual processing time is spread evenly before calls. Total episode durations and API wait durations match the logs; frame timing is approximate.", "",
             "For each task/model, the selected successful run is closest to the median duration of the current five saved runs. All selected examples achieved native 100% completion, using state 0, seed 0 and max effort; Task 4 uses its retained run set.", "",
             "| Task | Astra run | Astra wall time | Opus run | Opus wall time |", "|---|---:|---:|---:|---:|"]
    for task in TASKS:
        selected = [next(source for source in sources if source["task_id"] == task and source["model"] == model) for model in MODELS]
        lines.append("| {} | {} | {} | {} | {} |".format(task, selected[0]["display_trial"], clock(selected[0]["elapsed_seconds"]),
                                                            selected[1]["display_trial"], clock(selected[1]["elapsed_seconds"])))
    lines += ["", "[Source timelines and hashes](wait_aware_sources.json) · [Verification](wait_aware_verification.json)", "",
              "Rebuild with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_wait_aware_video.py`.", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print("ALL COMPLETE", flush=True)


if __name__ == "__main__":
    main()
