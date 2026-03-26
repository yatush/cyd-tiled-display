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
import threading
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

BUILD_ID_FILE       = f'{PIO_DIR}/.cyd_toolchain_build_id'

# Cache-warming paths (emulator pre-compile)
_SCRIPT_DIR         = os.path.dirname(os.path.abspath(__file__))
# Stored inside PIO_DIR so it survives HA addon updates via the
# /root/.platformio → /data/.platformio symlink created in vnc_startup.sh.
# The file contains the ESPHome version string so we re-warm after upgrades.
EMULATOR_MARKER     = os.path.join(PIO_DIR, '.emulator_prebuilt')
ESPHOME_DIR         = '/app/esphome'
PREPARE_PRECACHE    = os.path.join(_SCRIPT_DIR, 'prepare_precache.py')

# ─── Helpers ─────────────────────────────────────────────────────────────────

def write_progress(phase: str, progress: int, message: str,
                   fallback: bool = False, error: str | None = None) -> None:
    """Atomically write progress JSON so the UI always reads a complete file."""
    # Read the baked-in ESPHome version once per write (cheap file read).
    esphome_version = ''
    try:
        with open(ESPHOME_VER_FILE) as f:
            esphome_version = f.read().strip()
    except OSError:
        pass
    build_id = ''
    try:
        if os.path.exists(BUILD_ID_FILE):
            with open(BUILD_ID_FILE) as f:
                build_id = f.read().strip()
    except OSError:
        pass
    data: dict = {
        'phase':           phase,
        'progress':        progress,
        'message':         message,
        'fallback':        fallback,
        'esphome_version': esphome_version,
        'build_id':        build_id,
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
    """Return the currently-installed ESPHome version.

    Always queries the live installed package so the version stays accurate
    even after an in-place pip upgrade done by maybe_upgrade_esphome().
    Falls back to the baked-in file only when importlib can't find the package.
    """
    try:
        r = subprocess.run(
            ['python3', '-c', 'from importlib.metadata import version; print(version("esphome"))'],
            capture_output=True, text=True, timeout=30)
        v = r.stdout.strip()
        if v:
            return v
    except Exception:
        pass
    if os.path.exists(ESPHOME_VER_FILE):
        v = open(ESPHOME_VER_FILE).read().strip()
        if v:
            return v
    return 'unknown'


def maybe_upgrade_esphome() -> None:
    """Check PyPI for a newer ESPHome release; upgrade in-place if found.

    Called once per toolchain_setup.py invocation (including the 6-hour
    watchdog) so the container stays current without a Docker image rebuild.
    Failures are non-fatal — the existing installed version is kept.
    """
    try:
        req = urllib.request.Request(
            'https://pypi.org/pypi/esphome/json',
            headers={'User-Agent': 'cyd-tiled-display/toolchain-setup'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            latest = json.load(resp)['info']['version']
    except Exception as e:
        log(f'PyPI version check skipped: {e}')
        return

    installed = get_expected_version()
    if latest == installed:
        log(f'ESPHome {installed} is up-to-date.')
        return

    log(f'ESPHome upgrade available: {installed} → {latest}. Upgrading pip package...')
    try:
        subprocess.run(
            ['pip3', 'install', '--no-cache-dir', f'esphome=={latest}'],
            check=True, timeout=300)
        # Update the baked-in file so other processes (e.g. write_progress) also
        # see the new version immediately.
        with open(ESPHOME_VER_FILE, 'w') as f:
            f.write(latest)
        log(f'ESPHome upgraded to {latest}.')
    except Exception as e:
        log(f'ESPHome upgrade failed: {e}. Keeping {installed}.')


def get_stored_version() -> str | None:
    if os.path.exists(VERSION_FILE):
        return open(VERSION_FILE).read().strip() or None
    return None


def set_stored_version(version: str) -> None:
    os.makedirs(PIO_DIR, exist_ok=True)
    with open(VERSION_FILE, 'w') as f:
        f.write(version)
    open(SETUP_MARKER, 'w').close()


def get_stored_build_id() -> str | None:
    if os.path.exists(BUILD_ID_FILE):
        return open(BUILD_ID_FILE).read().strip() or None
    return None


def set_stored_build_id(build_id: str) -> None:
    os.makedirs(PIO_DIR, exist_ok=True)
    with open(BUILD_ID_FILE, 'w') as f:
        f.write(build_id)


def fetch_and_store_build_id(version: str) -> None:
    """Fetch build_id.txt from the GitHub Release and store it locally.

    Called after a successful toolchain download+extract so the UI can detect
    whether a newer build is available for the same ESPHome version.
    Non-fatal: failures are logged but do not affect the toolchain install.
    """
    repo = get_github_repo()
    url = (f'https://github.com/{repo}/releases/download/'
           f'toolchain-esphome-{version}/build_id.txt')
    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': 'cyd-tiled-display/toolchain-setup'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            build_id = resp.read().decode().strip()
        if build_id:
            set_stored_build_id(build_id)
            log(f'Toolchain build ID stored: {build_id}')
    except Exception as e:
        log(f'Could not fetch build_id.txt (non-fatal): {e}')


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
    The tarball contains paths like  packages/<tool>/...  and  platforms/<plat>/...
    Extracting to PIO_DIR places them at /root/.platformio/packages/... and
    /root/.platformio/platforms/... respectively.

    Uses the native `tar` binary (faster xz decompression + bulk I/O) with a
    progress-ticker thread so the UI stays responsive on slow SD-card systems.
    Falls back to Python tarfile if `tar` is not available.
    """
    label = 'Updating toolchain' if background else 'Extracting toolchain'
    write_progress('extracting', 61, f'{label}: extracting files...')
    log(f'Extracting {tarball_path} → {PIO_DIR}')
    os.makedirs(PIO_DIR, exist_ok=True)

    # ── Try native tar first ──────────────────────────────────────────────────
    # `tar` uses the system's multi-threaded xz and does bulk file I/O in C,
    # which is dramatically faster than the Python tarfile loop on RPi4 SD cards.
    # We run a background ticker thread to keep the UI progress bar moving.
    tar_bin = shutil.which('tar')
    if tar_bin:
        # Count members cheaply with `tar -t` so we can show X/total progress.
        try:
            result = subprocess.run(
                [tar_bin, '-tJf', tarball_path],
                capture_output=True, text=True, timeout=60)
            total = max(result.stdout.count('\n'), 1)
        except Exception:
            total = 0  # unknown — ticker uses time-based fake progress

        stop_ticker = threading.Event()
        start_time  = time.monotonic()

        def _ticker() -> None:
            fake_pct = 61
            while not stop_ticker.is_set():
                stop_ticker.wait(timeout=2.0)
                elapsed = time.monotonic() - start_time
                # Fake progress: advance smoothly toward 84% (leaves room for
                # the real 'fixing' phase at 86%).  Cap at 83 so it never tips
                # into the next phase prematurely.
                fake_pct = min(83, 61 + int(elapsed / 2))
                write_progress('extracting', fake_pct,
                               f'{label}: extracting files...')

        ticker = threading.Thread(target=_ticker, daemon=True)
        ticker.start()

        try:
            subprocess.run(
                [tar_bin, '-xJf', tarball_path, '-C', PIO_DIR],
                check=True)
        finally:
            stop_ticker.set()
            ticker.join(timeout=3)

        write_progress('extracting', 84, f'{label}: finalising...')

    else:
        # ── Fallback: Python tarfile (slower, but works everywhere) ──────────
        with tarfile.open(tarball_path, 'r:xz') as tar:
            members = tar.getmembers()
            total   = max(len(members), 1)
            last_update = 0.0
            for i, member in enumerate(members):
                tar.extract(member, path=PIO_DIR, filter='tar')
                now = time.monotonic()
                if now - last_update >= 1.0:
                    last_update = now
                    pct = 61 + int(i / total * 23)
                    write_progress('extracting', pct,
                                   f'{label}: {i}/{total} files')

    log('Extraction complete.')

    # If the tarball shipped a pre-warmed ccache (built in CI), mark the
    # emulator as already pre-compiled so maybe_warm_cache() nops.
    warmed = os.path.join(PIO_DIR, '.ccache', '.cyd_warmed')
    if os.path.exists(warmed):
        try:
            with open(EMULATOR_MARKER, 'w') as _f:
                _f.write(get_expected_version())
        except OSError:
            open(EMULATOR_MARKER, 'w').close()
        log('Tarball includes pre-warmed ccache — emulator marker set.')


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
        if os.path.isfile(cmake_path) and not os.path.islink(cmake_path) \
                and not os.path.exists(cmake_path + '.orig'):
            os.rename(cmake_path, cmake_path + '.orig')
            with open(cmake_path, 'w') as f:
                f.write('#!/bin/sh\nexec /usr/bin/cmake "$@"\n')
            os.chmod(cmake_path, 0o755)
            log(f'Replaced cmake: {cmake_path}')

    # ninja
    for ninja_path in glob.glob('/root/.platformio/packages/tool-ninja/ninja'):
        if os.path.isfile(ninja_path) and not os.path.islink(ninja_path) \
                and not os.path.exists(ninja_path + '.orig'):
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


def _cmake_needs_fix() -> bool:
    """Return True if a non-wrapped cmake binary exists in the PIO packages dir."""
    for cmake_path in (glob.glob('/root/.platformio/packages/*/bin/cmake') +
                       glob.glob('/root/.platformio/packages/tool-cmake/bin/cmake')):
        if os.path.isfile(cmake_path) and not os.path.exists(cmake_path + '.orig'):
            return True
    return False


# ─── Cache warming ───────────────────────────────────────────────────────────

def maybe_warm_cache() -> None:
    """Pre-compile the emulator for both screen sizes to warm the ccache.

    Skipped when the marker already exists with the current ESPHome version.
    Re-runs automatically when ESPHome is upgraded.
    Failures are non-fatal: the marker is not written, so the next startup retries.
    """
    expected = get_expected_version()
    if os.path.exists(EMULATOR_MARKER):
        try:
            stored_ver = open(EMULATOR_MARKER).read().strip()
        except OSError:
            stored_ver = ''
        if stored_ver == expected:
            log('Emulator cache already warm — skipping.')
            return
        log(f'ESPHome version changed ({stored_ver!r} → {expected!r}) — re-warming.')

    log('Warming emulator cache...')

    env = os.environ.copy()
    env['CCACHE_DIR']             = f'{PIO_DIR}/.ccache'
    env['CCACHE_MAXSIZE']         = '2G'
    env['CCACHE_COMPILERCHECK']   = 'content'
    env['CCACHE_NOHASHDIR']       = 'true'
    # Cap at 1 on arm64 (RPi4) to avoid OOM-killing Gunicorn; 2 on amd64.
    env['CMAKE_BUILD_PARALLEL_LEVEL'] = '1' if get_arch() == 'arm64' else '2'
    os.makedirs(env['CCACHE_DIR'], exist_ok=True)
    ccache_bin = '/usr/local/lib/ccache'
    if os.path.isdir(ccache_bin):
        env['PATH'] = f'{ccache_bin}:{env.get("PATH", "")}'

    # Step 1 — generate test_device_tiles.yaml + images.yaml + PNG files.
    write_progress('warming', 91, 'Warming cache: preparing assets...')
    if os.path.exists(PREPARE_PRECACHE):
        with open(PIO_SETUP_LOG, 'a') as logf:
            subprocess.run(['python3', PREPARE_PRECACHE],
                           stdout=logf, stderr=logf, check=False)
    else:
        log(f'WARNING: prepare_precache.py not found at {PREPARE_PRECACHE}')

    def _compile(label: str, progress: int, screen_w: int, screen_h: int,
                 font_tiny: int, font_small: int, font_medium: int, font_big: int,
                 font_text_regular: int, font_text_bold: int,
                 font_text_big_bold: int, font_text_small: int) -> None:
        write_progress('warming', progress, f'Warming cache: {label}...')
        with open(PIO_SETUP_LOG, 'a') as logf:
            subprocess.run(
                ['esphome',
                 '-s', 'tiles_file',       'test_device_tiles.yaml',
                 '-s', 'screen_w',         str(screen_w),
                 '-s', 'screen_h',         str(screen_h),
                 '-s', 'font_tiny',        str(font_tiny),
                 '-s', 'font_small',       str(font_small),
                 '-s', 'font_medium',      str(font_medium),
                 '-s', 'font_big',         str(font_big),
                 '-s', 'font_text_regular',  str(font_text_regular),
                 '-s', 'font_text_bold',     str(font_text_bold),
                 '-s', 'font_text_big_bold', str(font_text_big_bold),
                 '-s', 'font_text_small',    str(font_text_small),
                 'compile', 'lib/emulator.yaml'],
                cwd=ESPHOME_DIR, env=env,
                stdout=logf, stderr=logf, check=False,
            )

    # Step 2 — 320×240 (2432s028).  Done first so 480×320 seeded build is last.
    _compile('320\u00d7240 (2432s028)', 93,
             320, 240, 24, 40, 60, 80, 20, 20, 30, 12)

    # Step 3 — 480×320 (3248s035, same as emulator.yaml defaults).  Done last
    # so its build output seeds the per-session copy in run_session.sh.
    _compile('480\u00d7320 (3248s035)', 97,
             480, 320, 32, 60, 80, 100, 30, 30, 40, 18)
    # Step 3.5 — re-fix wrappers: the emulator compiles above may have caused
    # PlatformIO to download a new toolchain package (e.g. toolchain-xtensa-esp-elf
    # when pioarduino bumps its version). Those freshly-downloaded packages contain
    # glibc Rust binaries that panic on Alpine/musl. Re-running fix_wrappers() here
    # is idempotent and ensures both the CI tarball and the runtime container always
    # end up with Alpine-compatible shell wrappers.
    fix_wrappers()
    # Step 4 — restore images.yaml to empty placeholder and remove the
    #           temporary test_device_tiles.yaml.
    try:
        with open(os.path.join(ESPHOME_DIR, 'lib', 'images.yaml'), 'w') as f:
            f.write('# no images\n')
    except OSError:
        pass
    try:
        os.remove(os.path.join(ESPHOME_DIR, 'lib', 'test_device_tiles.yaml'))
    except OSError:
        pass

    try:
        with open(EMULATOR_MARKER, 'w') as f:
            f.write(expected)
    except OSError:
        open(EMULATOR_MARKER, 'w').close()
    log('Cache warming complete.')


# ─── Local-build fallback ────────────────────────────────────────────────────

def build_toolchain_locally(reason: str) -> None:
    """Build the toolchain locally via esphome compile (~10–15 min).

    On Alpine Linux, PlatformIO downloads glibc cmake/ninja binaries that hang
    when executed.  A background watcher thread polls for the packages directory
    and replaces those binaries with system wrappers as soon as they appear —
    before PlatformIO can invoke them.  The thread also ticks the progress
    counter so the UI doesn't look frozen during the ~10–15 minute build.
    """
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
    env['CMAKE_BUILD_PARALLEL_LEVEL'] = '1' if get_arch() == 'arm64' else '2'
    env['CCACHE_DIR']           = f'{PIO_DIR}/.ccache'
    env['CCACHE_MAXSIZE']       = '2G'
    env['CCACHE_COMPILERCHECK'] = 'content'
    env['CCACHE_NOHASHDIR']     = 'true'
    os.makedirs(env['CCACHE_DIR'], exist_ok=True)
    ccache_bin = '/usr/local/lib/ccache'
    if os.path.isdir(ccache_bin):
        env['PATH'] = f'{ccache_bin}:{env.get("PATH", "")}'

    # ── Background watcher ────────────────────────────────────────────────────
    # PlatformIO first downloads all its packages (cmake, ninja, …), then
    # invokes cmake.  On Alpine the downloaded cmake is a glibc binary that
    # hangs forever.  We watch for the packages directory to appear and
    # immediately replace those binaries with shell wrappers that delegate to
    # the system (musl-compatible) cmake/ninja installed in the Docker image.
    #
    # Polling at 0.5 s catches the window between "last package downloaded"
    # and "cmake first invoked" — the download phase takes at least a few
    # seconds, so 0.5 s is reliable in practice.
    stop_watcher = threading.Event()

    def _watcher() -> None:
        last_log_size = 0
        fake_pct = 5
        while not stop_watcher.is_set():
            stop_watcher.wait(timeout=0.5)
            # Fix cmake/ninja wrappers as soon as the binaries appear.
            # Keep calling fix_wrappers (idempotent) until cmake is patched,
            # because packages/ may be non-empty before cmake is downloaded.
            if _cmake_needs_fix():
                fix_wrappers()
                log('Watcher: fixed PIO wrappers mid-build.')
            # Tick the UI progress so it doesn't look stuck.
            try:
                sz = os.path.getsize(PIO_SETUP_LOG)
                if sz > last_log_size:
                    last_log_size = sz
                    fake_pct = min(fake_pct + 1, 84)
                    write_progress('building', fake_pct,
                                   'Building toolchain locally — this takes ~10–15 min...',
                                   fallback=True)
            except OSError:
                pass

    watcher = threading.Thread(target=_watcher, daemon=True)
    watcher.start()

    with open(PIO_SETUP_LOG, 'w') as logf:
        logf.write(f'[PIO SETUP] Starting at {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        logf.write(f'[PIO SETUP] Reason: {reason}\n')
        subprocess.run(['esphome', 'compile', dummy_yaml],
                       env=env, timeout=900, check=False,
                       stdout=logf, stderr=logf)

    stop_watcher.set()
    watcher.join(timeout=5)

    # Final wrapper fix pass (idempotent) in case watcher lost the race.
    write_progress('fixing', 86, 'Configuring toolchain for Alpine Linux...', fallback=True)
    fix_wrappers()
    shutil.rmtree(DUMMY_YAML_DIR, ignore_errors=True)
    log('Local build complete.')


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    force_local = '--force-local' in sys.argv

    # ── Upgrade ESPHome if a newer version is available on PyPI ──────────────
    # Skipped when the user triggered a local build (version doesn't matter there).
    if not force_local:
        maybe_upgrade_esphome()

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
        maybe_warm_cache()
        write_progress('ready', 100, 'Toolchain ready.', fallback=True)
        log('Setup complete (local build).')
        return

    # ── Case 1: already up-to-date ────────────────────────────────────────────
    if stored == expected and has_packages():
        log('Toolchain up-to-date.')
        set_stored_version(expected)   # ensures SETUP_MARKER is present
        fix_wrappers()   # idempotent catch-all: PlatformIO may have downloaded
                         # new packages outside our control (e.g. a fresh
                         # toolchain-xtensa-esp-elf during a previous esphome run).
        maybe_warm_cache()
        write_progress('ready', 100, 'Toolchain ready.')
        return

    # ── Case 3: no packages at all (fresh install) ────────────────────────────
    if not has_packages():
        log('No toolchain installed. Trying to download pre-built release...')
        tmp_path = None
        try:
            tmp_path = download_toolchain(expected, arch, background=False)
            extract_toolchain(tmp_path, background=False)
            fix_wrappers()
            set_stored_version(expected)
            maybe_warm_cache()
            write_progress('ready', 100, 'Toolchain installed successfully.')
            log('Fresh install from pre-built release complete.')
        except FileNotFoundError as e:
            log(f'Pre-built release not available: {e}. Waiting for user confirmation.')
            write_progress('no_toolchain', 0,
                           'No toolchain installed. '
                           'First compile will build locally (~10–15 min).')
        except Exception as e:
            log(f'Download failed: {e}. Waiting for user confirmation.')
            write_progress('no_toolchain', 0,
                           'Toolchain download failed. '
                           'First compile will build locally (~10–15 min).')
        else:
            # Download + extract succeeded — store the build ID for update checks.
            fetch_and_store_build_id(expected)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return

    # ── Case 2: newer version available, old packages still usable ───────────
    log('Newer toolchain version detected. Downloading update in background...')
    tmp_path = None

    try:
        tmp_path = download_toolchain(expected, arch, background=True)
        extract_toolchain(tmp_path, background=True)
        fix_wrappers()
        set_stored_version(expected)
        fetch_and_store_build_id(expected)
        maybe_warm_cache()
        write_progress('ready', 100, 'Toolchain updated successfully.')
        log('Background update complete.')

    except FileNotFoundError as e:
        # Release not published yet.
        # If the setup marker exists the existing toolchain is fully functional —
        # keep it working silently. If the marker is missing the packages were
        # downloaded ad-hoc by PlatformIO (old behaviour) and are not reliable,
        # so surface no_toolchain so the user can trigger a proper local build.
        log(f'Pre-built release not available yet: {e}.')
        if os.path.exists(SETUP_MARKER):
            log('Setup marker present — keeping existing toolchain.')
            fix_wrappers()
            maybe_warm_cache()
            write_progress('ready', 100,
                           'Toolchain ready (update pending — new release not yet available)')
        else:
            log('No setup marker — packages were ad-hoc, prompting user to build locally.')
            write_progress('no_toolchain', 0,
                           'Toolchain not initialised. '
                           'First compile will build locally (~10–15 min).')

    except Exception as e:
        log(f'Background download failed: {e}. Keeping existing toolchain.')
        fix_wrappers()
        maybe_warm_cache()
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
