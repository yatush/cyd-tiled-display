import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import github_sync


FILES = {
    "lib/lib.yaml": "new lib",
    "lib/lib_common.yaml": "new common",
    "lib/3248s035_base.yaml": "new base",
    "lib/lib_custom.yaml": "upstream custom",
    "lib/hw_overrides.yaml": "upstream override",
    "lib/user_config.yaml": "upstream config",
    "lib/images/picture.png": "upstream image",
    "external_components/tile_ui/__init__.py": "new component",
    "external_components/tile_ui/schema.json": "{}",
    "test_device.yaml": "new device",
}


def make_archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(f"repo-main/esphome/{path}", content)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.content


class GitHubSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        for path, text in {
            "lib/lib.yaml": "old lib",
            "lib/lib_custom.yaml": "my custom",
            "lib/hw_overrides.yaml": "my override",
            "lib/user_config.yaml": "my config",
            "external_components/tile_ui/__init__.py": "old component",
            "test_device.yaml": "old device",
        }.items():
            file = self.base / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text)

    def sync(self, files=FILES, validator=lambda path: None):
        with patch.object(github_sync.requests, "get", return_value=FakeResponse(make_archive(files))):
            return github_sync.sync_github_files(self.base, validator)

    def test_sync_preserves_custom_files_and_backs_up_replacements(self):
        count, backup = self.sync()
        self.assertEqual(count, 6)
        self.assertEqual((self.base / "lib/lib.yaml").read_text(), "new lib")
        self.assertEqual((self.base / backup / "lib/lib.yaml").read_text(), "old lib")
        self.assertEqual((self.base / backup / "external_components/tile_ui/__init__.py").read_text(), "old component")
        self.assertEqual((self.base / backup / "test_device.yaml").read_text(), "old device")
        self.assertEqual((self.base / "lib/lib_custom.yaml").read_text(), "my custom")
        self.assertEqual((self.base / "lib/hw_overrides.yaml").read_text(), "my override")
        self.assertEqual((self.base / "lib/user_config.yaml").read_text(), "my config")
        self.assertFalse((self.base / "lib/images/picture.png").exists())

    def test_missing_files_or_invalid_device_config_do_not_modify_targets(self):
        files = {key: value for key, value in FILES.items() if key != "lib/lib_common.yaml"}
        with self.assertRaises(ValueError):
            self.sync(files)
        def invalid(_path):
            raise ValueError("invalid device")
        with self.assertRaisesRegex(ValueError, "invalid device"):
            self.sync(validator=invalid)
        self.assertEqual((self.base / "lib/lib.yaml").read_text(), "old lib")

    def test_install_failure_rolls_back_replaced_and_new_files(self):
        real_replace = github_sync.os.replace
        calls = 0
        def fail_third(source, target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("disk failure")
            real_replace(source, target)
        with patch.object(github_sync.os, "replace", side_effect=fail_third):
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                self.sync()
        self.assertEqual((self.base / "lib/lib.yaml").read_text(), "old lib")
        self.assertFalse((self.base / "lib/lib_common.yaml").exists())

    def test_symlink_targets_are_rejected(self):
        (self.base / "lib/lib_common.yaml").symlink_to(self.base / "lib/lib_custom.yaml")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.sync()
        self.assertEqual((self.base / "lib/lib_custom.yaml").read_text(), "my custom")


if __name__ == "__main__":
    unittest.main()
