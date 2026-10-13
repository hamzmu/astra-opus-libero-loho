"""Build a minimal README GIF from the six selected static-camera episodes."""
import math
import json
import subprocess

import cv2

from create_study_montage import WORKSPACE, draw_text, probe, read_json, sha256


def main():
    directory = WORKSPACE / "loho-study/videos"
    source = directory / "astra_opus_tasks_0_1_4_static_grid_4x.mp4"
    output = directory / "astra_opus_tasks_0_1_4_static_grid_4x_preview.gif"
    original_hash = sha256(source)
    manifest_path = directory / "astra_opus_tasks_0_1_4_static_grid_4x_sources.json"
    manifest = read_json(manifest_path)
    manifest_hash = sha256(manifest_path)
    sources = manifest["sources"]
    assert len(sources) == 6 and all(item["camera"] == "static" for item in sources)
    tile, gap, row_gap, task_band, model_band, fps = 260, 10, 16, 28, 24, 8
    width = 3 * tile + 2 * gap
    height = task_band + 2 * (model_band + tile) + row_gap
    frames = math.ceil(manifest["duration_seconds"] * fps)
    seconds = frames / fps
    inputs, filters, positions = [], [], []
    for index, item in enumerate(sources):
        path = WORKSPACE / item["source_file"]
        assert sha256(path) == item["source_sha256"]
        assert sha256(path.parent / "summary.json") == item["source_summary_sha256"]
        metadata = probe(path)
        assert metadata["fps"] == 10 and metadata["frames"] == item["action_steps"] + 1
        inputs += ["-threads", "1", "-i", str(path)]
        filters.append(
            "[{}:v]setpts=(PTS-STARTPTS)/4,fps={},scale={}:{}:flags=lanczos,"
            "setsar=1,tpad=stop_mode=clone:stop_duration={:.6f},trim=end_frame={},"
            "setpts=N/({}*TB)[v{}]".format(index, fps, tile, tile, seconds, frames, fps, index))
        x = item["column"] * (tile + gap)
        y = task_band + model_band + item["row"] * (model_band + tile + row_gap)
        positions.append("{}_{}".format(x, y))
    filters.append(
        "{}xstack=inputs=6:layout={}:fill=white:shortest=1,"
        "pad={}:{}:0:0:color=white[grid]".format(
            "".join("[v{}]".format(index) for index in range(6)), "|".join(positions), width, height))
    labels = []
    for column, task in enumerate((0, 1, 4)):
        labels.append(draw_text("Task {}".format(task),
                                "{}+({}-text_w)/2".format(column * (tile + gap), tile),
                                5, 18, color="0x333333"))
    for row, model in enumerate(("Astra", "Opus")):
        y = task_band + row * (model_band + tile + row_gap)
        labels.append(draw_text(model, "(w-text_w)/2", y + 3, 17, color="0x333333"))
    filters.append("[grid]{},split[a][b]".format(",".join(labels)))
    filters += ["[a]palettegen=max_colors=64:stats_mode=diff[p]",
                "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle[gif]"]
    temporary = output.with_name(output.stem + ".encoding.gif")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", "2",
        *inputs, "-filter_complex", ";".join(filters), "-map", "[gif]", "-frames:v", str(frames),
        "-loop", "0", str(temporary),
    ], check=True)
    metadata = probe(temporary)
    source_metadata = probe(source)
    assert metadata["codec_name"] == "gif" and metadata["width"] == width and metadata["height"] == height
    assert metadata["frames"] == frames
    assert abs(metadata["duration_seconds"] - source_metadata["duration_seconds"]) < .15
    assert sha256(source) == original_hash
    assert sha256(manifest_path) == manifest_hash
    for item in sources:
        path = WORKSPACE / item["source_file"]
        assert sha256(path) == item["source_sha256"]
        assert sha256(path.parent / "summary.json") == item["source_summary_sha256"]
    temporary.replace(output)
    review_dir = WORKSPACE / "setup_logs/minimal_readme_preview_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(output))
    checkpoints = {0: "start", frames // 2: "middle", frames - 1: "ending"}
    first_header = None
    for frame in range(frames):
        ok, pixels = capture.read()
        assert ok and pixels.shape[:2] == (height, width)
        header = pixels[:task_band + model_band]
        if first_header is None:
            first_header = header.copy()
        assert cv2.norm(first_header, header, cv2.NORM_INF) == 0
        if frame in checkpoints:
            cv2.imwrite(str(review_dir / (checkpoints[frame] + ".jpg")), pixels,
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
    capture.release()
    result = {
        "passed": True, "source_file": source.name, "source_sha256": original_hash,
        "source_unchanged": True, "output_file": output.name, "output_sha256": sha256(output),
        "source_manifest": manifest_path.name, "source_manifest_sha256": manifest_hash,
        "source_videos_and_summaries_unchanged": True,
        "static_labels_verified_across_all_frames": True,
        "sources": [{key: item[key] for key in ("task_id", "model", "display_trial", "source_file", "source_sha256", "source_summary_sha256")}
                    for item in sources],
        "output_video": metadata, "target_fps": fps, "palette_colors": 64, "loop": "forever",
        "style": "White background; neutral task and model labels only; recorded RGB colors retained.",
        "notes": "Same six examples and full 4x simulation replay; API waiting omitted; shorter clips hold their final frames. Original MP4 remains unchanged.",
    }
    (directory / "readme_video_preview_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"preview": str(output), "verified": True, "size_bytes": output.stat().st_size}))


if __name__ == "__main__":
    main()
