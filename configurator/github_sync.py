import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

import requests


ARCHIVE_URL = "https://github.com/yatush/cyd-tiled-display/archive/refs/heads/main.zip"
MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_FILES_SIZE = 32 * 1024 * 1024


def _managed_path(name):
    parts = PurePosixPath(name).parts
    if len(parts) < 3 or parts[1] != "esphome" or any(
        p in ("", ".", "..") or "\\" in p for p in parts
    ):
        return None
    path = PurePosixPath(*parts[2:])
    if any(p.startswith(".") or p in ("__pycache__", "tests", "images") for p in path.parts):
        return None
    if path == PurePosixPath("test_device.yaml"):
        return path
    if path.parts[0] == "lib" and len(path.parts) > 1:
        filename = path.name
        if (filename in ("lib_custom.yaml", "hw_overrides.yaml", "images.yaml",
                         "secrets.yaml", "user_config.yaml", "test_device_tiles.yaml")
                or filename.startswith("user_config_") or "_custom." in filename):
            return None
        return path
    if path.parts[:2] in (("external_components", "tile_ui"), ("external_components", "tuya_ble_fan")) and len(path.parts) > 2:
        return path
    return None


def sync_github_files(base_dir, validate_lib):
    """Download and overlay managed files, rolling back on failure."""
    base = Path(base_dir).resolve()
    with tempfile.TemporaryDirectory(prefix=".cyd-sync-", dir=base) as temp:
        temp_path = Path(temp)
        archive = temp_path / "main.zip"
        with requests.get(ARCHIVE_URL, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            size = 0
            with archive.open("wb") as output:
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_SIZE:
                        raise ValueError("GitHub archive exceeds the download size limit")
                    output.write(chunk)

        files = {}
        total_size = 0
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                if entry.is_dir():
                    continue
                relative = _managed_path(entry.filename)
                if relative is None:
                    continue
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError(f"GitHub archive contains a symlink: {relative}")
                if relative in files:
                    raise ValueError(f"GitHub archive contains a duplicate path: {relative}")
                total_size += entry.file_size
                if total_size > MAX_FILES_SIZE:
                    raise ValueError("GitHub files exceed the extracted size limit")
                staged = temp_path / "files" / relative
                staged.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as src, staged.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                files[relative] = staged

        required = {
            PurePosixPath("lib/lib.yaml"),
            PurePosixPath("lib/lib_common.yaml"),
            PurePosixPath("external_components/tile_ui/__init__.py"),
            PurePosixPath("external_components/tile_ui/schema.json"),
            PurePosixPath("test_device.yaml"),
        }
        if not required.issubset(files) or not any(
            p.parts[0] == "lib" and p.name.endswith("_base.yaml") for p in files
        ):
            raise ValueError("GitHub archive is missing required ESPHome files")
        validate_lib(temp_path / "files" / "lib")

        for relative in files:
            target = base / relative
            for parent in (target, *target.parents):
                if parent == base:
                    break
                if parent.is_symlink():
                    raise ValueError(f"Target path contains a symlink: {relative}")
            if not target.resolve().is_relative_to(base):
                raise ValueError(f"Target path escapes ESPHome directory: {relative}")
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError(f"Target is not a regular file: {relative}")

        backup = temp_path / "backup"
        existing = set()
        for relative in files:
            target = base / relative
            if target.exists():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
                existing.add(relative)

        installed = []
        try:
            for relative, staged in files.items():
                target = base / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, target)
                installed.append(relative)
        except OSError as error:
            try:
                for relative in reversed(installed):
                    target = base / relative
                    if relative in existing:
                        shutil.copy2(backup / relative, target)
                    else:
                        target.unlink()
            except OSError as rollback_error:
                raise RuntimeError(
                    f"Sync failed: {error}; rollback failed: {rollback_error}"
                ) from error
            raise RuntimeError(f"Sync failed and was rolled back: {error}") from error

        return len(files)
