"""Safe, collision-free paths for user-facing generated videos."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.utils import utils


_INVALID_COMPONENT_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_MAX_COMPONENT_LENGTH = 100
_MAX_FOLDER_DEPTH = 8


def _safe_component(value: str, *, fallback: str) -> str:
    component = _INVALID_COMPONENT_PATTERN.sub("_", str(value or ""))
    component = re.sub(r"\s+", " ", component).strip(" .")
    component = component[:_MAX_COMPONENT_LENGTH].rstrip(" .")
    if not component:
        component = fallback
    if component.upper() in _RESERVED_WINDOWS_NAMES:
        component = f"_{component}"
    return component


def normalize_output_folder(value: str | None) -> str:
    """Return a safe relative folder such as ``tiktok/animais``."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return "geral"

    drive, _ = os.path.splitdrive(raw_value)
    has_windows_drive = bool(re.match(r"^[A-Za-z]:[\\/]", raw_value))
    if drive or has_windows_drive or os.path.isabs(raw_value):
        raise ValueError("output folder must be relative to storage/outputs")

    raw_parts = re.split(r"[\\/]+", raw_value)
    if any(part.strip() in {"", ".", ".."} for part in raw_parts):
        raise ValueError("output folder contains an invalid path segment")
    if len(raw_parts) > _MAX_FOLDER_DEPTH:
        raise ValueError(f"output folder cannot exceed {_MAX_FOLDER_DEPTH} levels")

    return "/".join(
        _safe_component(part, fallback="pasta") for part in raw_parts
    )


def normalize_video_title(value: str | None, *, fallback: str = "video") -> str:
    """Return a filename-safe title without an extension."""
    raw_title = str(value or "").strip()
    if raw_title.lower().endswith(".mp4"):
        raw_title = raw_title[:-4]
    return _safe_component(raw_title, fallback=fallback)


def output_root(create: bool = False) -> str:
    return utils.storage_dir("outputs", create=create)


def resolve_output_directory(output_folder: str | None, *, create: bool) -> str:
    root = os.path.realpath(output_root(create=create))
    relative_folder = normalize_output_folder(output_folder)
    candidate = os.path.realpath(os.path.join(root, *relative_folder.split("/")))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise ValueError("output folder is outside storage/outputs")
    except ValueError as exc:
        raise ValueError("output folder is outside storage/outputs") from exc

    if create:
        os.makedirs(candidate, exist_ok=True)
    return candidate


@contextmanager
def reserve_output_video_path(
    output_folder: str | None,
    video_title: str | None,
    *,
    index: int,
    total: int,
    fallback_title: str = "video",
) -> Iterator[str]:
    """Reserve a unique MP4 name without overwriting another task's output."""
    directory = resolve_output_directory(output_folder, create=True)
    title = normalize_video_title(video_title, fallback=fallback_title)
    indexed_title = f"{title}-{index}" if total > 1 else title

    lock_path = ""
    output_path = ""
    collision_index = 1
    while not output_path:
        collision_suffix = "" if collision_index == 1 else f"-{collision_index}"
        candidate = os.path.join(directory, f"{indexed_title}{collision_suffix}.mp4")
        candidate_lock = f"{candidate}.mpt.lock"
        if os.path.exists(candidate):
            collision_index += 1
            continue
        try:
            descriptor = os.open(candidate_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            collision_index += 1
            continue
        else:
            os.close(descriptor)
            lock_path = candidate_lock
            output_path = candidate

    try:
        yield output_path
    except Exception:
        Path(output_path).unlink(missing_ok=True)
        raise
    finally:
        Path(lock_path).unlink(missing_ok=True)


def resolve_existing_output_video(candidate: str | None) -> str:
    """Validate a persisted output path before exposing it in the WebUI."""
    if not candidate:
        return ""
    root = os.path.realpath(output_root(create=False))
    resolved = os.path.realpath(str(candidate))
    try:
        if os.path.commonpath([root, resolved]) != root:
            return ""
    except ValueError:
        return ""
    if not resolved.lower().endswith(".mp4") or not os.path.isfile(resolved):
        return ""
    return resolved
