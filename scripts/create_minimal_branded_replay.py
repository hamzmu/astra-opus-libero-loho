"""Export the six selected static-camera examples with minimal model/logo badges."""
import json
import subprocess

import cv2
from PIL import Image, ImageDraw, ImageFont

from create_study_montage import BOLD, FONT, WORKSPACE, probe, read_json, sha256


def create_labels(sources, assets, review, width, height, tile, gap, row_gap, header):
    logos = {}
    for model, filename in (("astra", "openai-blossom.svg"), ("opus", "claude-spark.svg")):
        raster = review / (model + "_logo.png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i",
                        str(assets / filename), "-vf", "scale=128:128:flags=lanczos",
                        "-frames:v", "1", "-threads", "1", str(raster)], check=True)
        logos[model] = Image.open(raster).convert("RGBA").resize((30, 30), Image.LANCZOS)
    labels = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    painter = ImageDraw.Draw(labels)
    task_font = ImageFont.truetype(FONT, 24)
    model_font = ImageFont.truetype(BOLD, 22)
    for column, task in enumerate((0, 1, 4)):
        text = "Task {}".format(task)
        box = painter.textbbox((0, 0), text, font=task_font)
        painter.text((column * (tile + gap) + (tile - (box[2] - box[0])) / 2,
                      (header - (box[3] - box[1])) / 2 - box[1]), text,
                     font=task_font, fill="#333333")
    for source in sources:
        text = "Astra 6" if source["model"] == "astra" else "Opus 5.5"
        x = source["column"] * (tile + gap) + 12
        y = header + source["row"] * (tile + row_gap) + 12
        box = painter.textbbox((0, 0), text, font=model_font)
        badge_width, badge_height = 11 + 30 + 8 + (box[2] - box[0]) + 11, 44
        painter.rounded_rectangle((x, y, x + badge_width, y + badge_height), radius=5,
                                  fill="#ffffff", outline="#e6e6e6", width=1)
        labels.alpha_composite(logos[source["model"]], (x + 11, y + 7))
        painter.text((x + 49, y + (badge_height - (box[3] - box[1])) / 2 - box[1]),
                     text, font=model_font, fill="#171717")
    text = "×4"
    box = painter.textbbox((0, 0), text, font=model_font)
    badge_width, badge_height = (box[2] - box[0]) + 22, 40
    x, y = width - badge_width - 12, height - badge_height - 12
    painter.rounded_rectangle((x, y, x + badge_width, y + badge_height), radius=5,
                              fill="#ffffff", outline="#e6e6e6", width=1)
    painter.text((x + 11, y + (badge_height - (box[3] - box[1])) / 2 - box[1]),
                 text, font=model_font, fill="#171717")
    path = review / "labels.png"
    labels.save(path)
    return path


def main():
    directory = WORKSPACE / "loho-study/videos"
    assets = directory / "assets"
    manifest_path = directory / "astra_opus_tasks_0_1_4_static_grid_4x_sources.json"
    manifest = read_json(manifest_path)
    original_manifest_hash = sha256(manifest_path)
    sources = manifest["sources"]
    assert len(sources) == 6 and all(s["camera"] == "static" and s["success"] for s in sources)
    logo_sources = read_json(assets / "logo_sources.json")
    for logo in logo_sources:
        assert sha256(assets / logo["file"]) == logo["sha256"]
    tile, gap, row_gap, header, fps = 512, 16, 24, 42, 40
    width, height = 3 * tile + 2 * gap, header + 2 * tile + row_gap
    frames = round(manifest["duration_seconds"] * fps)
    review = WORKSPACE / "setup_logs/minimal_branded_replay_review"
    review.mkdir(parents=True, exist_ok=True)
    labels = create_labels(sources, assets, review, width, height, tile, gap, row_gap, header)
    inputs, filters, positions = [], [], []
    for index, source in enumerate(sources):
        path = WORKSPACE / source["source_file"]
        assert sha256(path) == source["source_sha256"]
        assert sha256(path.parent / "summary.json") == source["source_summary_sha256"]
        metadata = probe(path)
        assert metadata["fps"] == 10 and metadata["frames"] == source["action_steps"] + 1
        inputs += ["-threads", "1", "-i", str(path)]
        filters.append(
            "[{}:v]setpts=(PTS-STARTPTS)/4,fps={},scale={}:{}:flags=lanczos,setsar=1,"
            "tpad=stop_mode=clone:stop_duration={},trim=end_frame={},setpts=N/({}*TB)[v{}]".format(
                index, fps, tile, tile, frames / fps, frames, fps, index))
        positions.append("{}_{}".format(source["column"] * (tile + gap),
                                       header + source["row"] * (tile + row_gap)))
    inputs += ["-threads", "1", "-loop", "1", "-framerate", str(fps), "-i", str(labels)]
    filters += [
        "{}xstack=inputs=6:layout={}:fill=white:shortest=1,pad={}:{}:0:0:color=white[grid]".format(
            "".join("[v{}]".format(i) for i in range(6)), "|".join(positions), width, height),
        "[6:v]format=rgba,trim=end_frame={},setpts=N/({}*TB)[labels]".format(frames, fps),
        "[grid][labels]overlay=shortest=1:format=auto,format=yuv420p[final]",
    ]
    graph = directory / "minimal_branded_replay_filter.txt"
    graph.write_text(";\n".join(filters), encoding="utf-8")
    output = directory / "astra6_opus55_tasks_0_1_4_static_minimal_4x.mp4"
    temporary = output.with_name(output.stem + ".encoding.mp4")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", "2"] + inputs + [
        "-filter_complex_script", str(graph), "-map", "[final]", "-an", "-frames:v", str(frames),
        "-r", str(fps), "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(temporary)]
    print("Encoding {}x{} | {:.2f}s | six views, logo badges, 4x".format(width, height, frames / fps), flush=True)
    checkpoint = -1
    with (review / "encoding.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True)
        for line in process.stdout:
            if line.startswith("frame="):
                frame = int(line.partition("=")[2])
                if frame // 400 > checkpoint:
                    checkpoint = frame // 400
                    print("Encoded {} / {} frames".format(frame, frames), flush=True)
        if process.wait():
            raise RuntimeError("FFmpeg failed; inspect setup_logs/minimal_branded_replay_review/encoding.log")
    metadata = probe(temporary)
    assert metadata["frames"] == frames and metadata["fps"] == fps
    assert metadata["width"] == width and metadata["height"] == height
    assert metadata["codec_name"] == "h264" and metadata["pix_fmt"] == "yuv420p"
    assert abs(metadata["duration_seconds"] - frames / fps) < .02
    assert sha256(manifest_path) == original_manifest_hash
    for source in sources:
        path = WORKSPACE / source["source_file"]
        assert sha256(path) == source["source_sha256"]
        assert sha256(path.parent / "summary.json") == source["source_summary_sha256"]
    for logo in logo_sources:
        assert sha256(assets / logo["file"]) == logo["sha256"]
    temporary.replace(output)
    capture = cv2.VideoCapture(str(output))
    for name, frame in (("start", 0), ("middle", frames // 2), ("ending", frames - 1)):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, pixels = capture.read()
        assert ok and pixels.shape[:2] == (height, width)
        cv2.imwrite(str(review / (name + ".jpg")), pixels, [cv2.IMWRITE_JPEG_QUALITY, 95])
    capture.release()
    result = {
        "passed": True, "output_file": output.name, "output_sha256": sha256(output),
        "output_video": metadata, "source_files_unchanged": True,
        "source_manifest": manifest_path.name, "source_manifest_sha256": original_manifest_hash,
        "sources": [{key: s[key] for key in ("task_id", "model", "display_trial", "source_file",
                                               "source_sha256", "source_summary_sha256")} for s in sources],
        "logo_sources": logo_sources, "labels": {"astra": "Astra 6", "opus": "Opus 5.5"},
        "speed_badge": {"label": "×4", "position": "bottom right", "margin_pixels": 12},
        "layout": "Rows Astra 6 / Opus 5.5; columns Tasks 0 / 1 / 4; logo badge at the top left of each view.",
        "playback": "4x recorded simulation motion; API waiting omitted; shorter clips hold their final frame.",
        "evaluation_views": "Static and wrist were supplied during evaluation; this replay shows static only.",
    }
    (directory / "minimal_branded_replay_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "verified": True,
                      "duration_seconds": metadata["duration_seconds"], "size_bytes": output.stat().st_size}), flush=True)


if __name__ == "__main__":
    main()
