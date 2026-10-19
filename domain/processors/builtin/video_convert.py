import asyncio
import inspect
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import aiofiles

from domain.processors.base import ProcessorOutput

# libopenh264 has no CRF control, so the quality slider is mapped to a bitrate.
_TIME_RE = re.compile(r"^(?:\d+(?:\.\d+)?|\d{1,3}:[0-5]\d(?::[0-5]\d)?(?:\.\d+)?)$")
_ENCODERS: set[str] | None = None

VIDEO_ENCODERS = {
    "h264": ("libx264", "libopenh264"),
    "h265": ("libx265",),
    "vp9": ("libvpx-vp9",),
    "av1": ("libsvtav1", "libaom-av1"),
    "mpeg4": ("mpeg4", "libxvid"),
}
AUDIO_ENCODERS = {
    "aac": ("aac", "libfdk_aac"),
    "mp3": ("libmp3lame",),
    "opus": ("libopus", "opus"),
    "vorbis": ("libvorbis", "vorbis"),
}
AUDIO_BITRATE = {"aac": "160k", "mp3": "192k", "opus": "128k", "vorbis": "160k"}
VP9_SPEED = {"veryfast": "5", "fast": "4", "medium": "2", "slow": "1"}
SVT_PRESET = {"veryfast": "10", "fast": "8", "medium": "6", "slow": "4"}
AOM_SPEED = {"veryfast": "8", "fast": "6", "medium": "4", "slow": "2"}
HEIGHTS = {"original": None, "2160p": 2160, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}


@dataclass(frozen=True)
class FormatSpec:
    ext: str
    muxer: str
    video: str
    audio: str
    media_type: str
    faststart: bool = False
    gif: bool = False


FORMATS = {
    "mp4": FormatSpec(".mp4", "mp4", "h264", "aac", "video/mp4", faststart=True),
    "webm": FormatSpec(".webm", "webm", "vp9", "opus", "video/webm"),
    "mkv": FormatSpec(".mkv", "matroska", "h264", "aac", "video/x-matroska"),
    "mov": FormatSpec(".mov", "mov", "h264", "aac", "video/quicktime", faststart=True),
    "avi": FormatSpec(".avi", "avi", "mpeg4", "mp3", "video/x-msvideo"),
    "gif": FormatSpec(".gif", "gif", "gif", "none", "image/gif", gif=True),
    "mp3": FormatSpec(".mp3", "mp3", "none", "mp3", "audio/mpeg"),
    "m4a": FormatSpec(".m4a", "ipod", "none", "aac", "audio/mp4"),
    "ogg": FormatSpec(".ogg", "ogg", "none", "vorbis", "audio/ogg"),
}


def _choice(config: dict, key: str, allowed: set[str], default: str, label: str) -> str:
    value = config.get(key, default)
    if value is None or value == "":
        value = default
    text = str(value).strip().lower()
    if text not in allowed:
        raise ValueError(f"不支持的{label}: {value}")
    return text


def _optional_int(config: dict, key: str, label: str, low: int, high: int) -> int | None:
    value = config.get(key)
    if value is None or value == "":
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc
    if number < low or number > high:
        raise ValueError(f"{label}必须在 {low} 到 {high} 之间")
    return number


def _optional_time(config: dict, key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _TIME_RE.fullmatch(text):
        raise ValueError("开始时间或时长格式无效，请使用秒数或 00:01:30")
    return text


@dataclass(frozen=True)
class ConvertOptions:
    format: str
    video_codec: str
    audio_codec: str
    height: int | None
    crf: int
    preset: str
    fps: int | None
    start: str | None
    duration: str | None
    audio_bitrate: str | None
    subtitles: str


def normalize_config(config: dict | None) -> ConvertOptions:
    raw = config or {}
    fmt = _choice(raw, "format", set(FORMATS), "mp4", "格式")
    resolution = _choice(raw, "resolution", set(HEIGHTS), "original", "分辨率")
    bitrate = _optional_int(raw, "audio_bitrate", "音频码率", 32, 512)
    crf = _optional_int(raw, "crf", "质量", 0, 51)
    return ConvertOptions(
        format=fmt,
        video_codec=_choice(raw, "video_codec", {"auto", "h264", "h265", "vp9", "av1", "mpeg4", "copy"}, "auto", "视频编码"),
        audio_codec=_choice(raw, "audio_codec", {"auto", "aac", "mp3", "opus", "vorbis", "copy", "none"}, "auto", "音频编码"),
        height=HEIGHTS[resolution],
        crf=23 if crf is None else crf,
        preset=_choice(raw, "preset", {"veryfast", "fast", "medium", "slow"}, "medium", "速度预设"),
        fps=_optional_int(raw, "fps", "帧率", 1, 120),
        start=_optional_time(raw, "start"),
        duration=_optional_time(raw, "duration"),
        audio_bitrate=None if bitrate is None else f"{bitrate}k",
        subtitles=_choice(raw, "subtitles", {"drop", "copy"}, "drop", "字幕"),
    )


def adjusted_output_path(target_path: str, config: dict | None) -> str:
    ext = FORMATS[normalize_config(config).format].ext
    path = PurePosixPath(target_path)
    if path.suffix.lower() == ext:
        return target_path
    return str(path.with_suffix(ext))


def parse_encoders(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VASA.":
            found.add(parts[1])
    return found


def pick_encoder(family: str, table: dict[str, tuple[str, ...]], encoders: set[str]) -> str:
    names = table.get(family, ())
    for name in names:
        if name in encoders:
            return name
    needed = "、".join(names) or family
    raise RuntimeError(f"当前 ffmpeg 没有 {family} 编码器（需要 {needed}）")


def _openh264_bitrate(crf: int, height: int | None) -> str:
    quality = max(0.2, (51 - crf) / 28)
    scale = (height or 1080) / 1080
    kbps = int(max(300, 4000 * quality * max(0.2, scale)))
    return f"{kbps}k"


def video_codec_args(encoder: str, crf: int, preset: str, height: int | None) -> list[str]:
    if encoder in {"libx264", "libx265"}:
        return ["-c:v", encoder, "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p"]
    if encoder == "libopenh264":
        return ["-c:v", encoder, "-rc_mode", "bitrate", "-b:v", _openh264_bitrate(crf, height), "-pix_fmt", "yuv420p"]
    if encoder == "libvpx-vp9":
        return ["-c:v", encoder, "-crf", str(crf), "-b:v", "0", "-cpu-used", VP9_SPEED[preset], "-row-mt", "1", "-pix_fmt", "yuv420p"]
    if encoder == "libsvtav1":
        return ["-c:v", encoder, "-crf", str(crf), "-preset", SVT_PRESET[preset], "-pix_fmt", "yuv420p"]
    if encoder == "libaom-av1":
        return ["-c:v", encoder, "-crf", str(crf), "-b:v", "0", "-cpu-used", AOM_SPEED[preset], "-pix_fmt", "yuv420p"]
    if encoder in {"mpeg4", "libxvid"}:
        quantizer = min(31, max(2, round(crf * 31 / 51)))
        return ["-c:v", encoder, "-q:v", str(quantizer), "-pix_fmt", "yuv420p"]
    raise RuntimeError(f"不支持的视频编码器 {encoder}")


def video_filter(options: ConvertOptions, video_family: str) -> str | None:
    if video_family in {"none", "copy"}:
        return None
    if options.format == "gif":
        parts = [f"fps={options.fps or 12}"]
        parts.append(f"scale=-2:{options.height}:flags=lanczos" if options.height else "scale=480:-2:flags=lanczos")
        chain = ",".join(parts)
        return f"{chain},split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer"
    parts = []
    if options.fps:
        parts.append(f"fps={options.fps}")
    if options.height:
        parts.append(f"scale=-2:{options.height}:flags=lanczos")
    if not parts:
        return None
    return ",".join(parts)


def build_ffmpeg_command(src: str, dst: str, config: dict | None, encoders: set[str]) -> list[str]:
    options = normalize_config(config)
    spec = FORMATS[options.format]
    if spec.gif:
        video_family = "gif"
        audio_family = "none"
    elif spec.video == "none":
        video_family = "none"
        audio_family = spec.audio if options.audio_codec in {"auto", "none"} else options.audio_codec
    else:
        video_family = spec.video if options.video_codec == "auto" else options.video_codec
        audio_family = spec.audio if options.audio_codec == "auto" else options.audio_codec

    if video_family == "copy" and (options.height or options.fps):
        raise ValueError("复制视频流时不能同时修改分辨率或帧率")

    command = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error"]
    if options.start:
        command += ["-ss", options.start]
    command += ["-i", src]
    if options.duration:
        command += ["-t", options.duration]

    graph = video_filter(options, video_family)
    if graph:
        command += ["-vf", graph]

    if video_family == "none":
        command += ["-map", "0:a:0", "-vn"]
    elif video_family == "copy":
        command += ["-map", "0:v:0", "-c:v", "copy"]
    elif video_family == "gif":
        if "gif" not in encoders:
            raise RuntimeError("当前 ffmpeg 没有 gif 编码器")
        command += ["-map", "0:v:0", "-c:v", "gif", "-loop", "0"]
    else:
        encoder = pick_encoder(video_family, VIDEO_ENCODERS, encoders)
        command += ["-map", "0:v:0", *video_codec_args(encoder, options.crf, options.preset, options.height)]

    if audio_family == "none":
        command += ["-an"]
    elif video_family != "none":
        audio_map = "-map", "0:a:0?"
        if audio_family == "copy":
            command += [*audio_map, "-c:a", "copy"]
        else:
            encoder = pick_encoder(audio_family, AUDIO_ENCODERS, encoders)
            command += [*audio_map, "-c:a", encoder, "-b:a", options.audio_bitrate or AUDIO_BITRATE[audio_family]]
    elif audio_family == "copy":
        command += ["-c:a", "copy"]
    else:
        encoder = pick_encoder(audio_family, AUDIO_ENCODERS, encoders)
        command += ["-c:a", encoder, "-b:a", options.audio_bitrate or AUDIO_BITRATE[audio_family]]

    if options.subtitles == "copy" and video_family not in {"none", "gif"}:
        command += ["-map", "0:s?", "-c:s", "copy"]
    else:
        command += ["-sn"]

    if spec.faststart:
        command += ["-movflags", "+faststart"]
    command += ["-f", spec.muxer, dst]
    return command


async def available_encoders() -> set[str]:
    global _ENCODERS
    if _ENCODERS is not None:
        return _ENCODERS
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-encoders",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 ffmpeg，可执行文件需要在 PATH 中") from exc
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("无法读取 ffmpeg 编码器列表")
    _ENCODERS = parse_encoders(stdout.decode(errors="replace"))
    return _ENCODERS


async def run_ffmpeg(command: list[str]) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 ffmpeg，可执行文件需要在 PATH 中") from exc
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        message = (stderr or stdout or b"").decode(errors="replace").strip()
        raise RuntimeError(message[-2000:] or "ffmpeg 执行失败")


def _temporary(suffix: str) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    return handle.name


async def _write_response(response: Any, destination: str) -> None:
    iterator = getattr(response, "body_iterator", None)
    try:
        if iterator is None and isinstance(response, (bytes, bytearray)):
            await asyncio.to_thread(Path(destination).write_bytes, bytes(response))
            return
        body = getattr(response, "body", None)
        if iterator is None and body is not None:
            await asyncio.to_thread(Path(destination).write_bytes, bytes(body))
            return
        if iterator is None:
            raise RuntimeError("存储适配器没有返回可读取的文件流")
        async with aiofiles.open(destination, "wb") as output:
            async for chunk in iterator:
                if chunk:
                    await output.write(chunk)
    finally:
        closer = getattr(response, "aclose", None) or getattr(response, "close", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result


async def open_source(input_bytes: bytes, path: str) -> tuple[str, bool]:
    """返回本地路径，以及转码结束后是否要删除它。"""
    suffix = PurePosixPath(path).suffix or ".bin"
    if input_bytes:
        destination = _temporary(suffix)
        await asyncio.to_thread(Path(destination).write_bytes, input_bytes)
        return destination, True

    from fastapi import HTTPException
    from domain.adapters.providers.local import _safe_join
    from domain.virtual_fs import VirtualFSService

    try:
        adapter, model, root, rel = await VirtualFSService.resolve_adapter_and_rel(path)
    except HTTPException as exc:
        raise FileNotFoundError(path) from exc

    # A local mount can be handed to ffmpeg directly. Remote bytes are staged on disk.
    if getattr(model, "type", None) == "local":
        file_path = _safe_join(root, rel)
        if not await asyncio.to_thread(file_path.is_file):
            raise FileNotFoundError(path)
        return str(file_path), False

    destination = _temporary(suffix)
    try:
        stream_file = getattr(adapter, "stream_file", None)
        if callable(stream_file):
            await _write_response(await stream_file(root, rel, None), destination)
        else:
            data = await adapter.read_file(root, rel)
            await asyncio.to_thread(Path(destination).write_bytes, data)
    except Exception:
        with suppress(FileNotFoundError):
            Path(destination).unlink()
        raise
    return destination, True


class VideoConvertProcessor:
    name = "视频转换"
    supported_exts = [
        "mp4", "m4v", "mov", "mkv", "webm", "avi", "wmv", "flv", "mpeg", "mpg",
        "ts", "m2ts", "mts", "3gp", "ogv", "gif", "mp3", "m4a", "aac", "wav",
        "flac", "ogg", "opus", "wma",
    ]
    config_schema = [
        {
            "key": "format",
            "label": "输出格式",
            "type": "select",
            "required": True,
            "default": "mp4",
            "options": [
                {"value": "mp4", "label": "MP4"},
                {"value": "webm", "label": "WebM"},
                {"value": "mkv", "label": "MKV"},
                {"value": "mov", "label": "MOV"},
                {"value": "avi", "label": "AVI"},
                {"value": "gif", "label": "GIF"},
                {"value": "mp3", "label": "MP3 音频"},
                {"value": "m4a", "label": "M4A 音频"},
                {"value": "ogg", "label": "OGG 音频"},
            ],
        },
        {
            "key": "video_codec",
            "label": "视频编码",
            "type": "select",
            "required": False,
            "default": "auto",
            "placeholder": "自动选择当前 ffmpeg 支持的编码器",
            "options": [
                {"value": "auto", "label": "自动"},
                {"value": "h264", "label": "H.264"},
                {"value": "h265", "label": "H.265"},
                {"value": "vp9", "label": "VP9"},
                {"value": "av1", "label": "AV1"},
                {"value": "mpeg4", "label": "MPEG-4"},
                {"value": "copy", "label": "复制视频流"},
            ],
        },
        {
            "key": "audio_codec",
            "label": "音频编码",
            "type": "select",
            "required": False,
            "default": "auto",
            "options": [
                {"value": "auto", "label": "自动"},
                {"value": "aac", "label": "AAC"},
                {"value": "mp3", "label": "MP3"},
                {"value": "opus", "label": "Opus"},
                {"value": "vorbis", "label": "Vorbis"},
                {"value": "copy", "label": "复制音频流"},
                {"value": "none", "label": "无音频"},
            ],
        },
        {
            "key": "resolution",
            "label": "分辨率",
            "type": "select",
            "required": False,
            "default": "original",
            "options": [
                {"value": "original", "label": "原始"},
                {"value": "2160p", "label": "2160p"},
                {"value": "1080p", "label": "1080p"},
                {"value": "720p", "label": "720p"},
                {"value": "480p", "label": "480p"},
                {"value": "360p", "label": "360p"},
            ],
        },
        {"key": "crf", "label": "质量 (CRF)", "type": "number", "required": False, "default": 23, "placeholder": "0-51，越小越清晰"},
        {
            "key": "preset",
            "label": "速度预设",
            "type": "select",
            "required": False,
            "default": "medium",
            "options": [
                {"value": "veryfast", "label": "极快"},
                {"value": "fast", "label": "快"},
                {"value": "medium", "label": "均衡"},
                {"value": "slow", "label": "慢"},
            ],
        },
        {"key": "fps", "label": "帧率", "type": "number", "required": False, "placeholder": "留空保持原帧率"},
        {"key": "start", "label": "开始时间", "type": "string", "required": False, "placeholder": "秒数或 00:01:30"},
        {"key": "duration", "label": "时长", "type": "string", "required": False, "placeholder": "留空表示直到结尾"},
        {"key": "audio_bitrate", "label": "音频码率", "type": "number", "required": False, "placeholder": "kbps，留空使用默认值"},
        {
            "key": "subtitles",
            "label": "字幕",
            "type": "select",
            "required": False,
            "default": "drop",
            "options": [
                {"value": "drop", "label": "丢弃"},
                {"value": "copy", "label": "复制"},
            ],
        },
    ]
    produces_file = True
    supports_directory = False
    requires_input_bytes = False

    def adjust_output_path(self, target_path: str, config: dict) -> str:
        return adjusted_output_path(target_path, config)

    async def process(self, input_bytes: bytes, path: str, config: dict[str, Any]) -> ProcessorOutput:
        options = normalize_config(config)
        encoders = await available_encoders()
        source, remove_source = await open_source(input_bytes or b"", path or "")
        destination = _temporary(FORMATS[options.format].ext)
        try:
            command = build_ffmpeg_command(source, destination, config, encoders)
            await run_ffmpeg(command)
            if not Path(destination).is_file() or Path(destination).stat().st_size <= 0:
                raise RuntimeError("ffmpeg 没有生成输出文件")
        except Exception:
            with suppress(FileNotFoundError):
                Path(destination).unlink()
            raise
        finally:
            if remove_source:
                with suppress(FileNotFoundError):
                    Path(source).unlink()
        return ProcessorOutput(destination, FORMATS[options.format].media_type)


PROCESSOR_TYPE = "video_convert"
PROCESSOR_NAME = VideoConvertProcessor.name
SUPPORTED_EXTS = VideoConvertProcessor.supported_exts
CONFIG_SCHEMA = VideoConvertProcessor.config_schema
produces_file = True
supports_directory = False
PROCESSOR_FACTORY: Callable[[], VideoConvertProcessor] = lambda: VideoConvertProcessor()
