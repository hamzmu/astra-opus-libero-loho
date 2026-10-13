"""Build the animated README preview from the saved combined MP4, offline."""
import json
import subprocess

from create_study_montage import WORKSPACE, probe, sha256


def main():
    directory = WORKSPACE / "loho-study/videos"
    source = directory / "astra_opus_tasks_0_1_4_static_grid_4x.mp4"
    output = directory / "astra_opus_tasks_0_1_4_static_grid_4x_preview.gif"
    original_hash = sha256(source)
    filters = (
        "[0:v]fps=8,scale=800:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=max_colors=64:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
    )
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-threads", "1",
        "-i", str(source), "-filter_complex_threads", "2", "-filter_complex", filters,
        "-loop", "0", str(output),
    ], check=True)
    metadata = probe(output)
    source_metadata = probe(source)
    assert metadata["codec_name"] == "gif" and metadata["width"] == 800
    assert abs(metadata["duration_seconds"] - source_metadata["duration_seconds"]) < .15
    assert sha256(source) == original_hash
    result = {
        "passed": True, "source_file": source.name, "source_sha256": original_hash,
        "source_unchanged": True, "output_file": output.name, "output_sha256": sha256(output),
        "output_video": metadata, "target_fps": 8, "palette_colors": 64, "loop": "forever",
        "notes": "Full 4x simulation replay; GIF frame delays have centisecond precision. Original MP4 is linked for playback at full resolution.",
    }
    (directory / "readme_video_preview_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"preview": str(output), "verified": True, "size_bytes": output.stat().st_size}))


if __name__ == "__main__":
    main()
