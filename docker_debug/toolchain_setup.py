#!/usr/bin/env python3
"""
Toolchain setup for CYD Tiled Display.

Three-state logic on every container start:

  1. Version matches + packages present  → write ready, exit immediately (silent)
  2. Newer version + old packages exist   → download in background, keep old
                                            toolchain working, overwrite when done
  3. No packages at all (fresh install)   → write no_toolchain, exit.
                                            User is prompted in the Install dialog
                                            and confirms via the UI which calls
                                            POST /api/toolchain/start_local_build,
                                            which re-runs with --force-local.

Progress is written to /tmp/toolchain_setup_progress.json so the Flask backend
can expose it to the React UI via /api/toolchain/status.

Usage:
    python3 /app/toolchain_setup.py                # normal startup check
    python3 /app/toolchain_setup.py --force-local  # user-confirmed local build
"""

import os
import sys
import json
import glob
import time
import shutil
import tarfile
import platform
import tempfile
import subprocess
import urllib.request
import urllib.error

# ─── Paths ───────────────────────────────────────────────────────────────────
PROGRESS_FILE       = '/tmp/toolchain_setup_progress.json'
PIO_DIR             = '/root/.platformio'
PACKAGES_DIR        = f'{PIO_DIR}/packages'
VERSION_FILE        = f'{PIO_DIR}/.cyd_esphome_version'
SETUP_MARKER        = f'{PIO_DIR}/.cyd_setup_done'
ESPHOME_VER_FILE    = '/app/esphome_version.txt'
GITHUB_REPO_FILE    = '/app/github_repo.txt'
FIX_WRAPPERS_SCRIPT = '/app/fix_pio_wrappers.sh'
PIO_SETUP_LOG       = '/tmp/pio_setup.log'
DUMMY_YAML_DIR      = '/tmp/esp32_setup'

# ─── Helpers ─────────────────────────────────────────────────────────────────

def write_progress(phase: str, progress: int, message: str,
                   fallback: bool = False, error: str | None = None) -> None:
    """Atomically write progress JSON so the UI always reads a complete file."""
    data: dict = {
        'phase':    phase,
        'progress': progress,
        'message':  message,
        'fallback': fallback,
    }
    if error:
        data['error'] = error
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, PROGRESS_FILE)


def log(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    print(f'[toolchain_setup {ts}] {msg}', flush=True)


def get_arch() -> str:
    m = platform.machine().lower()
    if m in ('aarch64', 'arm64'):
        return 'arm64'
    if m in ('x86_64', 'amd64'):
        return 'amd64'
    return m


def get_expected_version() -> str:
    if os.path.exists(ESPHOME_VER_FILE):
        v = open(ESPHOME_VER_FILE).read().strip()
        if v:
            return v
    try:
        r = subprocess.run(
            ['python3', '-c', 'from importlib.metadata import version; print(version("esphome"))'],
            capture_output=True, text=True, timeout=30)
        return r.stdout.strip()
    except Exception:
        return 'unknown'


def get_stored_version() -> str | None:
    if os.path.exists(VERSION_FILE):
        return open(VERSION_FILE).read().strip() or None
    return None


def set_stored_version(version: str) -> None:
    os.makedirs(PIO_DIR, exist_ok=True)
    with open(VERSION_FILE, 'w') as f:
        f.write(version)
    open(SETUP_MARKER, 'w').close()


def has_packages() -> bool:
    """Return True if the PlatformIO packages directory has content."""
    return os.path.isdir(PACKAGES_DIR) and bool(os.listdir(PACKAGES_DIR))


def get_github_repo() -> str:
    if os.path.exists(GITHUB_REPO_FILE):
        repo = open(GITHUB_REPO_FILE).read().strip()
        if repo:
            return repo
    return 'yatush/cyd-tiled-display'


# ─── Download phase ──────────────────────────────────────────────────────────

def download_toolchain(version: str, arch: str, background: bool = False) -> str:
    """
    Download the toolchain tarball from GitHub Releases.
    Returns path to the downloaded temp file.
    Raises FileNotFoundError if the release doesn't exist (404).
    Raises other exceptions on network errors.
    """
    repo = get_github_repo()
    url = (f'https://github.com/{repo}/releases/download/'
           f'toolchain-esphome-{version}/toolchain-{arch}.tar.xz')
    log(f'Downloading toolchain from: {url}')
    label = 'Updating toolchain in background' if background else 'Downloading toolchain'
    write_progress('downloading', 0, f'{label}: connecting...')

    req = urllib.request.Request(url, headers={'User-Agent': 'cyd-tiled-display/toolchain-setup'})
    try:
        response = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(
                f'No pre-built toolchain release for ESPHome {version} ({arch}). '
                f'It may still be building on GitHub Actions.')
        raise

    total = int(response.headers.get('Content-Length', 0))
    log(f'Content-Length: {total / 1_048_576:.0f} MB' if total else 'Content-Length unknown')

    fd, tmp_path = tempfile.mkstemp(suffix='.tar.xz', prefix='cyd_toolchain_')
    try:
        downloaded = 0
        chunk_size = 128 * 1024  # 128 KB
        last_update = 0.0
        with os.fdopen(fd, 'wb') as tmp:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                tmp.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_update >= 1.0:          # update UI at most 1×/s
                    last_update = now
                    if total > 0:
                        pct = int(downloaded / total * 60)
                        dl_mb   = downloaded / 1_048_576
                        tot_mb  = total / 1_048_576
                        write_progress('downloading', pct,
                                       f'{label}: {dl_mb:.0f} / {tot_mb:.0f} MB')
                    else:
                        dl_mb = downloaded / 1_048_576
                        write_progress('downloading', 10,
                                       f'{label}: {dl_mb:.0f} MB...')
    except Exception:
        os.unlink(tmp_path)
        raise

    log(f'Download complete: {downloaded / 1_048_576:.1f} MB → {tmp_path}')
    return tmp_path


# ─── Extract phase ───────────────────────────────────────────────────────────

def extract_toolchain(tarball_path: str, background: bool = False) -> None:
    """
    Extract the toolchain tarball into PIO_DIR.
    The tarball is expected to have paths like  packages/<tool>/...
    so extracting to PIO_DIR places files at /root/.platformio/packages/...
    """
    label = 'Updating toolchain' if background else 'Extracting toolchain'
    write_progress('extracting', 61, f'{label}: extracting files...')
    log(f'Extracting {tarball_path} → {PIO_DIR}')
    os.makedirs(PIO_DIR, exist_ok=True)

    with tarfile.open(tarball_path, 'r:xz') as tar:
        members = tar.getmembers()
        total   = max(len(members), 1)
        last_update = 0.0
        for i, member in enumerate(members):
            tar.extract(member, path=PIO_DIR, filter='data')
            now = time.monotonic()
            if now - last_update >= 1.0:
                last_update = now
                pct = 61 + int(i / total * 24)
                write_progress('extracting', pct,
                               f'{label}: {i}/{total} files')

    log('Extraction complete.')


# ─── Fix-wrappers phase ──────────────────────────────────────────────────────

def fix_wrappers() -> None:
    """Replace PlatformIO's glibc Rust binaries with Alpine-compatible wrappers."""
    write_progress('fixing', 86, 'Configuring toolchain for Alpine Linux...')
    log('Fixing PlatformIO wrappers...')

    if os.path.exists(FIX_WRAPPERS_SCRIPT):
        subprocess.run(['sh', FIX_WRAPPERS_SCRIPT], check=False)

    # cmake
    for cmake_path in glob.glob('/root/.platformio/packages/*/bin/cmake') + \
                      glob.glob('/root/.platformio/packages/tool-cmake/bin/cmake'):
        if os.path.isfile(cmake_path) and not os.path.islink(cmake_path):
            os.rename(cmake_path, cmake_path + '.orig')
            with open(cmake_path, 'w') as f:
                f.write('#!/bin/sh\nexec /usr/bin/cmake "$@"\n')
            os.chmod(cmake_path, 0o755)
            log(f'Replaced cmake: {cmake_path}')

    # ninja
    for ninja_path in glob.glob('/root/.platformio/packages/tool-ninja/ninja'):
        if os.path.isfile(ninja_path) and not os.path.islink(ninja_path):
            os.rename(ninja_path, ninja_path + '.orig')
            with open(ninja_path, 'w') as f:
                f.write('#!/bin/sh\nexec /usr/bin/ninja "$@"\n')
            os.chmod(ninja_path, 0o755)
            log(f'Replaced ninja: {ninja_path}')

    # Remove .orig backups to save space
    for orig in glob.glob('/root/.platformio/**/*.orig', recursive=True):
        try:
            os.remove(orig)
        except OSError:
            pass

    log('Wrapper fix complete.')


# ─── Local-build fallback ────────────────────────────────────────────────────

def build_toolchain_locally(reason: str) -> None:
    """Build the toolchain locally via esphome compile (~10–15 min)."""
    log(f'Building locally. Reason: {reason}')
    write_progress('building', 5,
                   'Building toolchain locally — this takes ~10–15 min...',
                   fallback=True)

    os.makedirs(DUMMY_YAML_DIR, exist_ok=True)
    dummy_yaml = os.path.join(DUMMY_YAML_DIR, 'dummy.yaml')
    with open(dummy_yaml, 'w') as f:
        f.write('esphome:\n  name: dummy\n'
                'esp32:\n  board: esp32dev\n  framework:\n    type: esp-idf\n')

    env = os.environ.copy()
    env['CMAKE_BUILD_PARALLEL_LEVEL'] = '2'

    with open(PIO_SETUP_LOG, 'w') as logf:
        logf.write(f'[PIO SETUP] Starting at {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        logf.write(f'[PIO SETUP] Reason: {reason}\n')
        subprocess.run(['esphome', 'compile', dummy_yaml],
                       env=env, timeout=900, check=False,
                       stdout=logf, stderr=logf)

    write_progress('fixing', 90, 'Configuring toolchain...', fallback=True)
    fix_wrappers()
    shutil.rmtree(DUMMY_YAML_DIR, ignore_errors=True)
    log('Local build complete.')


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    force_local = '--force-local' in sys.argv
    expected    = get_expected_version()
    stored      = get_stored_version()
    arch        = get_arch()

    log(f'Expected ESPHome version : {expected}')
    log(f'Stored toolchain version : {stored or "(none)"}')
    log(f'Arch                     : {arch}')
    log(f'Has packages             : {has_packages()}')
    log(f'Force local              : {force_local}')

    # ── --force-local: user confirmed, build now ──────────────────────────────
    if force_local:
        build_toolchain_locally('User requested local build')
        set_stored_version(expected)
        write_progress('ready', 100, 'Toolchain ready.', fallback=True)
        log('Setup complete (local build).')
        return

    # ── Case 1: already up-to-date ────────────────────────────────────────────
    if stored == expected and has_packages():
        log('Toolchain up-to-date.')
        write_progress('ready', 100, 'Toolchain ready.')
        return

    # ── Case 3: no packages at all (fresh install) ────────────────────────────
    if not has_packages():
        log('No toolchain installed. Waiting for user confirmation.')
        write_progress('no_toolchain', 0,
                       'No toolchain installed. '
                       'First compile will build locally (~10–15 min).')
        # Return immediately — local build is user-triggered via the UI.
        return

    # ── Case 2: newer version available, old packages still usable ───────────
    log('Newer toolchain version detected. Downloading update in background...')
    tmp_path = None

    try:
        tmp_path = download_toolchain(expected, arch, background=True)
        extract_toolchain(tmp_path, background=True)
        fix_wrappers()
        set_stored_version(expected)
        write_progress('ready', 100, 'Toolchain updated successfully.')
        log('Background update complete.')

    except FileNotFoundError as e:
        # Release not published yet — keep old toolchain working.
        # The daily build-toolchain.yml will publish it soon.
        log(f'Pre-built release not available yet: {e}. Keeping existing toolchain.')
        write_progress('ready', 100,
                       'Toolchain ready (update pending — new release not yet available)')

    except Exception as e:
        log(f'Background download failed: {e}. Keeping existing toolchain.')
        write_progress('ready', 100,
                       'Toolchain ready (update failed; using previous version)')

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


if __name__ == '__main__':
    main()
