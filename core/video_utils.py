"""Video encoding utilities.

OpenCV's VideoWriter produces MPEG-4 Part 2 ("mp4v"), which desktop browsers
do NOT play in <video>. Every video the dashboard serves must be H.264, so
after writing we transcode in place via the ffmpeg binary bundled with
imageio-ffmpeg (works on Linux/macOS/Windows without a system ffmpeg).

If transcoding fails we keep the original file and log loudly — a playable-
in-VLC-only video is better than no video, but the failure must be visible
(tech plan principle #10).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from core.log import get_logger

log = get_logger("video_utils")


def to_h264(path: str | Path, crf: int = 23) -> Path:
    """Transcode an mp4 to H.264 in place. Returns the path."""
    path = Path(path)
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        log.error("imageio-ffmpeg unavailable (%s) — %s stays mp4v and will NOT "
                  "play in browsers", e, path.name)
        return path

    tmp = path.with_suffix(".h264.mp4")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(path),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(tmp)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        tmp.replace(path)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, "stderr", b"") or b""
        log.error("H.264 transcode FAILED for %s: %s — file stays mp4v and will "
                  "NOT play in browsers", path.name, stderr.decode()[:300])
        tmp.unlink(missing_ok=True)
    return path
