"""Export the minimal README animation beside its three result figures."""
import json
import math
import subprocess

import cv2

from create_study_montage import WORKSPACE, probe, read_json, sha256


def main():
    directory = WORKSPACE / "loho-study/videos"
    replay = directory / "astra_opus_tasks_0_1_4_static_grid_4x_preview.gif"
    replay_verification = read_json(directory / "readme_video_preview_verification.json")
    assert replay_verification["passed"] and sha256(replay) == replay_verification["output_sha256"]
    plots = WORKSPACE / "loho-study/plots"
    figures = [plots / "completion_percent.png", plots / "tokens_and_cost_tasks_0_1_4.png",
               plots / "options/02_wallclock_breakdown.png"]
    sources = [{"file": str(path.relative_to(WORKSPACE)), "sha256": sha256(path)}
               for path in [replay, *figures]]
    replay_info = probe(replay)
    width, height, fps = 3840, 2160, 40
    margin, gap, figure_width, figure_gap = 48, 48, 1216, 24
    video_width = width - 2 * margin - gap - figure_width
    content_height = height - 2 * margin
    figure_height = (content_height - 2 * figure_gap) // 3
    right_x = margin + video_width + gap
    frames = math.ceil(replay_info["duration_seconds"] * fps)
    output = directory / "astra_opus_tasks_0_1_4_replay_with_figures_4x.mp4"
    temporary = output.with_name(output.stem + ".encoding.mp4")
    filters = [
        "[0:v]fps={},scale={}:{}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
        "pad={}:{}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,"
        "tpad=stop_mode=clone:stop_duration=1,trim=end_frame={},setpts=N/({}*TB),"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0xd8d8d8:t=2[replay]".format(
            fps, video_width, content_height, video_width, content_height, frames, fps),
    ]
    inputs = ["-threads", "1", "-ignore_loop", "1", "-i", str(replay)]
    for index, figure in enumerate(figures, 1):
        inputs += ["-threads", "1", "-loop", "1", "-framerate", str(fps), "-i", str(figure)]
        filters.append(
            "[{}:v]scale={}:{}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
            "pad={}:{}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,"
            "trim=end_frame={},setpts=N/({}*TB)[chart{}]".format(
                index, figure_width, figure_height, figure_width, figure_height, frames, fps, index))
    layout = ["{}_{}".format(margin, margin)] + [
        "{}_{}".format(right_x, margin + index * (figure_height + figure_gap)) for index in range(3)]
    filters.append(
        "[replay][chart1][chart2][chart3]xstack=inputs=4:layout={}:fill=white:shortest=1,"
        "pad={}:{}:0:0:color=white,setsar=1[final]".format("|".join(layout), width, height))
    graph = directory / "replay_with_figures_filter.txt"
    graph.write_text(";\n".join(filters), encoding="utf-8")
    review = WORKSPACE / "setup_logs/replay_with_figures_review"
    review.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-filter_complex_threads", "2"] + inputs + [
        "-filter_complex_script", str(graph), "-map", "[final]", "-an", "-frames:v", str(frames),
        "-r", str(fps), "-c:v", "libx264", "-threads", "4", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(temporary)]
    print("Encoding {}x{} | {:.2f}s | replay left, three figures right".format(width, height, frames / fps), flush=True)
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
            raise RuntimeError("FFmpeg failed; inspect setup_logs/replay_with_figures_review/encoding.log")
    metadata = probe(temporary)
    assert metadata["frames"] == frames and metadata["fps"] == fps
    assert metadata["width"] == width and metadata["height"] == height
    assert metadata["codec_name"] == "h264" and metadata["pix_fmt"] == "yuv420p"
    assert abs(metadata["duration_seconds"] - replay_info["duration_seconds"]) < .05
    for source in sources:
        assert sha256(WORKSPACE / source["file"]) == source["sha256"]
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
        "output_video": metadata, "source_files_unchanged": True, "sources": sources,
        "layout": "Minimal six-view static-camera replay on the left; three README figures stacked on the right.",
        "figure_order": ["Goal completion", "Total tokens and estimated API cost", "Wall-clock breakdown"],
        "playback": "Same full 4x simulation animation as the README GIF; API waiting omitted from replay.",
        "figure_scope": "Means and sample SD over five saved episodes per model/task; not just the six illustrated episodes.",
        "frame_rate_note": "40-fps container repeats the GIF frames; no motion interpolation.",
    }
    (directory / "replay_with_figures_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "verified": True,
                      "duration_seconds": metadata["duration_seconds"], "size_bytes": output.stat().st_size}), flush=True)


if __name__ == "__main__":
    main()
