import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils import video_output


def test_normalize_output_folder_supports_nested_account_folders():
    assert video_output.normalize_output_folder("TikTok/Animais Selvagens") == (
        "TikTok/Animais Selvagens"
    )
    assert video_output.normalize_output_folder("curiosidades: geral") == (
        "curiosidades_ geral"
    )


@pytest.mark.parametrize(
    "unsafe_folder",
    ["../fora", "conta/../fora", "C:\\videos", "/tmp/videos"],
)
def test_normalize_output_folder_rejects_unsafe_paths(unsafe_folder):
    with pytest.raises(ValueError):
        video_output.normalize_output_folder(unsafe_folder)


def test_normalize_video_title_handles_extensions_and_windows_names():
    assert video_output.normalize_video_title("Meu: vídeo.mp4") == "Meu_ vídeo"
    assert video_output.normalize_video_title("CON") == "_CON"


def test_reserve_output_video_path_avoids_overwriting_existing_video():
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        video_output, "output_root", return_value=temp_dir
    ):
        with video_output.reserve_output_video_path(
            "animais",
            "Leões",
            index=1,
            total=1,
        ) as first_path:
            Path(first_path).write_bytes(b"first")

        with video_output.reserve_output_video_path(
            "animais",
            "Leões",
            index=1,
            total=1,
        ) as second_path:
            Path(second_path).write_bytes(b"second")

        assert Path(first_path).name == "Leões.mp4"
        assert Path(second_path).name == "Leões-2.mp4"
        assert Path(first_path).read_bytes() == b"first"
        assert Path(second_path).read_bytes() == b"second"
        assert not list(Path(temp_dir).rglob("*.mpt.lock"))


def test_reservation_removes_partial_video_when_generation_fails():
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        video_output, "output_root", return_value=temp_dir
    ):
        with pytest.raises(RuntimeError, match="render failed"):
            with video_output.reserve_output_video_path(
                "autoestima",
                "Você consegue",
                index=1,
                total=1,
            ) as output_path:
                Path(output_path).write_bytes(b"partial")
                raise RuntimeError("render failed")

        assert not Path(output_path).exists()
        assert not list(Path(temp_dir).rglob("*.mpt.lock"))


def test_resolve_existing_output_video_accepts_only_output_root():
    with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as other:
        with patch.object(video_output, "output_root", return_value=temp_dir):
            valid = Path(temp_dir) / "animais" / "video.mp4"
            valid.parent.mkdir()
            valid.write_bytes(b"video")
            outside = Path(other) / "outside.mp4"
            outside.write_bytes(b"video")

            assert video_output.resolve_existing_output_video(str(valid)) == str(valid)
            assert video_output.resolve_existing_output_video(str(outside)) == ""
