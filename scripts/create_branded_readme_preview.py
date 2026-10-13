"""Create the README's looping GIF directly from its branded comparison MP4."""
import json
import math
import subprocess

import cv2

from create_study_montage import WORKSPACE, probe, read_json, sha256


def main():
    directory = WORKSPACE / "loho-study/videos"
    source = directory / "astra6_opus55_tasks_0_1_4_static_minimal_4x.mp4"
    verification_path = directory / "minimal_branded_replay_verification.json"
    verification = read_json(verification_path)
    source_hash, verification_hash = sha256(source), sha256(verification_path)
    assert verification["passed"] and source_hash == verification["output_sha256"]
    original = probe(source)
    output = source.with_name(source.stem + "_preview.gif")
    temporary = output.with_name(output.stem + ".encoding.gif")
    fps, width, colors = 8, 800, 128
    height = round(original["height"] * width / original["width"] / 2) * 2
    frames = math.ceil(original["duration_seconds"] * fps)
    filters = (
        "[0:v]fps={},scale={}:{}:flags=lanczos,tpad=stop_mode=clone:stop_duration=0.25,"
        "trim=end_frame={},split[a][b];[a]palettegen=max_colors={}:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle[gif]"
    ).format(fps, width, height, frames, colors)
    review = WORKSPACE / "setup_logs/branded_readme_preview_review"
    review.mkdir(parents=True, exist_ok=True)
    with (review / "encoding.log").open("w", encoding="utf-8") as log:
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", "2",
            "-threads", "1", "-i", str(source), "-filter_complex", filters, "-map", "[gif]",
            "-frames:v", str(frames), "-loop", "0", str(temporary),
        ], check=True, stderr=log)
    metadata = probe(temporary)
    assert metadata["codec_name"] == "gif" and metadata["frames"] == frames
    assert metadata["width"] == width and metadata["height"] == height
    assert abs(metadata["duration_seconds"] - original["duration_seconds"]) < .15
    assert sha256(source) == source_hash and sha256(verification_path) == verification_hash
    temporary.replace(output)
    # Decode sequentially so optimized GIF delta frames retain the full label overlay.
    capture = cv2.VideoCapture(str(output))
    checkpoints = {0: "start", frames // 2: "middle", frames - 1: "ending"}
    for frame in range(frames):
        ok, pixels = capture.read()
        assert ok and pixels.shape[:2] == (height, width)
        if frame in checkpoints:
            cv2.imwrite(str(review / (checkpoints[frame] + ".jpg")), pixels,
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
    capture.release()
    result = {
        "passed": True, "output_file": output.name, "output_sha256": sha256(output),
        "source_file": source.name, "source_sha256": source_hash, "source_unchanged": True,
        "source_verification": verification_path.name, "source_verification_sha256": verification_hash,
        "output_video": metadata, "decoded_frames": frames, "target_fps": fps,
        "palette_colors": colors, "loop": "forever",
        "style": "Same logo badges, model names, bold underlined task headings and bottom-right ×4 badge as the source MP4.",
        "playback": verification["playback"], "evaluation_views": verification["evaluation_views"],
    }
    (directory / "branded_readme_preview_verification.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "verified": True,
                      "duration_seconds": metadata["duration_seconds"], "size_bytes": output.stat().st_size}))


if __name__ == "__main__":
    main()
