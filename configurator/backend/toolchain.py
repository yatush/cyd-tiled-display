import os
import json
import time
import signal
import shutil
import threading
import subprocess
import requests
from flask import Blueprint, request, jsonify
from backend.state import APP_DIR, BASE_DIR, IS_ADDON

toolchain_bp = Blueprint('toolchain', __name__)

# Cache for the pgrep result in toolchain_status() fallback — avoids spawning a
# new subprocess on every poll when neither the progress file nor the setup-done
# marker exists (e.g. very early in container startup).
_pgrep_cache: dict = {'ts': 0.0, 'running': False}

@toolchain_bp.route('/api/toolchain/status')
def toolchain_status():
    """
    Return the current toolchain setup progress so the UI can show a progress bar.
    Reads from /tmp/toolchain_setup_progress.json (written by toolchain_setup.py).
    Falls back to ready if the legacy .cyd_setup_done marker is present.
    """
    progress_file = '/tmp/toolchain_setup_progress.json'
    upgrade_warning = None
    for warn_file in ('/tmp/cyd_upgrade_warning.json', '/root/.platformio/.cyd_upgrade_warning.json'):
        if os.path.exists(warn_file):
            try:
                with open(warn_file) as f:
                    upgrade_warning = json.load(f)
                break
            except Exception:
                pass

    if os.path.exists(progress_file):
        try:
            with open(progress_file) as f:
                data = json.load(f)
                if upgrade_warning and 'upgrade_warning' not in data:
                    data['upgrade_warning'] = upgrade_warning
                return jsonify(data)
        except (json.JSONDecodeError, OSError):
            pass

    # Legacy: baked-in toolchain (BAKE_TOOLCHAIN=1) or already-set-up volume
    if os.path.exists('/root/.platformio/.cyd_setup_done'):
        res = {'phase': 'ready', 'progress': 100,
               'message': 'Toolchain ready.', 'fallback': False}
        if upgrade_warning:
            res['upgrade_warning'] = upgrade_warning
        return jsonify(res)

    # No progress file and no marker — check if the script is still running.
    # Cache the pgrep result for 5 s so rapid polls don't spawn a new process.
    global _pgrep_cache
    now = time.time()
    if now - _pgrep_cache['ts'] > 5:
        _pgrep_cache['running'] = subprocess.run(
            ['pgrep', '-f', 'toolchain_setup.py'],
            capture_output=True
        ).returncode == 0
        _pgrep_cache['ts'] = now

    if _pgrep_cache['running']:
        return jsonify({'phase': 'starting', 'progress': 0,
                        'message': 'Toolchain setup starting...', 'fallback': False})

    return jsonify({'phase': 'no_toolchain', 'progress': 0,
                    'message': 'Toolchain not initialised. '
                               'Open the Install dialog to build locally.',
                    'fallback': False})


@toolchain_bp.route('/api/toolchain/log', methods=['GET'])
def toolchain_log():
    """
    Return the last N lines of the toolchain setup log.
    Query param ?lines=N (default 200).
    """
    log_path = '/tmp/toolchain_setup.log'
    try:
        n = int(request.args.get('lines', 200))
    except (ValueError, TypeError):
        n = 200
    if not os.path.exists(log_path):
        return '', 200
    try:
        result = subprocess.run(['tail', '-n', str(n), log_path], capture_output=True, text=True)
        return result.stdout, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f'Error reading log: {e}', 500

@toolchain_bp.route('/api/toolchain/start_local_build', methods=['POST'])
def toolchain_start_local_build():
    """
    Trigger a local toolchain build (user confirmed via the UI).
    Launches toolchain_setup.py --force-local in the background.
    """
    progress_file = '/tmp/toolchain_setup_progress.json'
    # Prevent double-start
    if os.path.exists(progress_file):
        try:
            data = json.load(open(progress_file))
            running_phases = ('downloading', 'extracting', 'fixing', 'building')
            if data.get('phase') in running_phases:
                return jsonify({'status': 'already_running', 'phase': data['phase']}), 200
        except (json.JSONDecodeError, OSError):
            pass

    setup_script = '/app/toolchain_setup.py'
    if not os.path.exists(setup_script):
        return jsonify({'error': 'toolchain_setup.py not found'}), 500

    log_file = open('/tmp/toolchain_setup.log', 'w')
    proc = subprocess.Popen(
        ['python3', setup_script, '--force-local'],
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
    )
    # Persist PID so the cancel endpoint can kill it
    with open('/tmp/toolchain_setup.pid', 'w') as f:
        f.write(str(proc.pid))
    return jsonify({'status': 'started'})

@toolchain_bp.route('/api/toolchain/cancel', methods=['POST'])
def toolchain_cancel():
    """
    Kill any running toolchain_setup.py process and reset state to no_toolchain.
    """
    import signal as _signal
    killed = False
    pid_file = '/tmp/toolchain_setup.pid'
    # Try pid file first
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, _signal.SIGTERM)
            killed = True
        except (ValueError, ProcessLookupError, OSError):
            pass
        finally:
            try:
                os.remove(pid_file)
            except OSError:
                pass
    # Fallback: pkill by script name
    if not killed:
        try:
            subprocess.run(['pkill', '-f', 'toolchain_setup.py'], check=False)
            killed = True
        except Exception:
            pass
    # Reset progress file to no_toolchain
    progress_file = '/tmp/toolchain_setup_progress.json'
    try:
        import tempfile, json as _json
        payload = _json.dumps({'phase': 'no_toolchain', 'progress': 0,
                               'message': 'Build cancelled.', 'fallback': False})
        tmp = progress_file + '.tmp'
        with open(tmp, 'w') as f:
            f.write(payload)
        os.replace(tmp, progress_file)
    except Exception:
        pass
    return jsonify({'status': 'cancelled', 'killed': killed})

def _has_toolchain_assets() -> bool:
    packages_dir = '/root/.platformio/packages'
    idf_dir = '/root/.cache/esphome/idf'
    return (
        (os.path.isdir(packages_dir) and bool(os.listdir(packages_dir))) or
        (os.path.isdir(idf_dir) and bool(os.listdir(idf_dir)))
    )


@toolchain_bp.route('/api/toolchain/check_update', methods=['GET'])
def toolchain_check_update():
    """
    Non-destructive check: returns whether a newer toolchain build is available.
    Does NOT launch toolchain_setup.py — use POST /api/toolchain/download_latest for that.

    Returns:
      { update_available: bool, remote_build_id, local_build_id, version }
    """
    import urllib.request as _urllib_req
    import urllib.error   as _urllib_err

    build_id_file = '/root/.platformio/.cyd_toolchain_build_id'
    ver_file      = '/app/esphome_version.txt'
    repo_file     = '/app/github_repo.txt'

    expected_version = None
    if os.path.exists(ver_file):
        try:
            expected_version = open(ver_file).read().strip() or None
        except OSError:
            pass

    version_file = '/root/.platformio/.cyd_esphome_version'
    stored_version = None
    if os.path.exists(version_file):
        try:
            stored_version = open(version_file).read().strip() or None
        except OSError:
            pass

    local_build_id = None
    if os.path.exists(build_id_file):
        try:
            local_build_id = open(build_id_file).read().strip() or None
        except OSError:
            pass

    has_pkgs = _has_toolchain_assets()

    repo = 'yatush/cyd-tiled-display'
    if os.path.exists(repo_file):
        try:
            r = open(repo_file).read().strip()
            if r:
                repo = r
        except OSError:
            pass

    # When the stored toolchain is already ahead of the baked-in ESPHome version
    # (e.g. stored=2026.4.3, baked-in=2026.4.0), look up build_id.txt for the
    # stored version — not the baked-in one.  Using the baked-in version would
    # always produce a mismatch against the stored build_id, making the update
    # check incorrectly report that a new download is needed on every restart.
    def _ver_key(v):
        try:
            return tuple(int(x) for x in (v or '').split('.'))
        except Exception:
            return (0,)

    lookup_version = expected_version
    if _ver_key(stored_version) > _ver_key(lookup_version):
        lookup_version = stored_version

    remote_build_id = None
    if lookup_version:
        url = (f'https://github.com/{repo}/releases/download/'
               f'toolchain-esphome-{lookup_version}/build_id.txt')
        try:
            req = _urllib_req.Request(url, headers={'User-Agent': 'cyd-tiled-display/server'})
            with _urllib_req.urlopen(req, timeout=10) as resp:
                remote_build_id = resp.read().decode().strip() or None
        except _urllib_err.HTTPError as e:
            if e.code == 404:
                remote_build_id = None
        except Exception:
            pass

    update_available = bool(remote_build_id and has_pkgs and remote_build_id != local_build_id)

    return jsonify({
        'update_available': update_available,
        'remote_build_id': remote_build_id,
        'local_build_id': local_build_id,
        'version': lookup_version,
    })

@toolchain_bp.route('/api/toolchain/download_latest', methods=['POST'])
def toolchain_download_latest():
    """
    Check whether the installed toolchain is already the latest build on GitHub.

    The comparison uses the per-build build_id.txt published with each release
    (format: {esphome_version}-{YYYYMMDD}-run{N}).  This catches re-builds for
    the same ESPHome version.  Falls back to a version-only comparison for older
    releases that predate build_id.txt.

    Returns:
      { status: 'up_to_date', version, build_id }  — nothing to do
      { status: 'started' }                          — toolchain_setup.py launched
      { status: 'already_running', phase }           — already in progress
    """
    import urllib.request as _urllib_req
    import urllib.error   as _urllib_err

    version_file   = '/root/.platformio/.cyd_esphome_version'
    build_id_file  = '/root/.platformio/.cyd_toolchain_build_id'
    ver_file       = '/app/esphome_version.txt'
    repo_file      = '/app/github_repo.txt'
    progress_file  = '/tmp/toolchain_setup_progress.json'

    # Prevent double-start
    if os.path.exists(progress_file):
        try:
            with open(progress_file) as _f:
                _data = json.load(_f)
            running_phases = ('downloading', 'extracting', 'fixing', 'building', 'warming')
            if _data.get('phase') in running_phases:
                return jsonify({'status': 'already_running', 'phase': _data['phase']}), 200
        except (json.JSONDecodeError, OSError):
            pass

    # Read local state
    expected_version = None
    if os.path.exists(ver_file):
        try:
            expected_version = open(ver_file).read().strip() or None
        except OSError:
            pass

    local_build_id = None
    if os.path.exists(build_id_file):
        try:
            local_build_id = open(build_id_file).read().strip() or None
        except OSError:
            pass

    stored_version = None
    if os.path.exists(version_file):
        try:
            stored_version = open(version_file).read().strip() or None
        except OSError:
            pass

    has_pkgs = _has_toolchain_assets()

    # Determine GitHub repo
    repo = 'yatush/cyd-tiled-display'
    if os.path.exists(repo_file):
        try:
            r = open(repo_file).read().strip()
            if r:
                repo = r
        except OSError:
            pass

    # When the stored toolchain is already ahead of the baked-in ESPHome version
    # (e.g. stored=2026.4.3, baked-in=2026.4.0), look up build_id.txt for the
    # stored version — not the baked-in one.  Using the baked-in version would
    # always produce a mismatch against the stored build_id, triggering a
    # spurious re-download on every container restart.
    def _ver_key(v):
        try:
            return tuple(int(x) for x in (v or '').split('.'))
        except Exception:
            return (0,)

    lookup_version = expected_version
    if _ver_key(stored_version) > _ver_key(lookup_version):
        lookup_version = stored_version

    # Fetch remote build_id.txt (tiny file, fast)
    remote_build_id = None
    if lookup_version:
        url = (f'https://github.com/{repo}/releases/download/'
               f'toolchain-esphome-{lookup_version}/build_id.txt')
        try:
            req = _urllib_req.Request(
                url, headers={'User-Agent': 'cyd-tiled-display/server'})
            with _urllib_req.urlopen(req, timeout=10) as resp:
                remote_build_id = resp.read().decode().strip() or None
        except _urllib_err.HTTPError as e:
            if e.code == 404:
                # Old release without build_id.txt — fall back to version comparison
                remote_build_id = None
            # Other HTTP errors: treat as 'unknown', fall through
        except Exception:
            # Network error: treat as 'unknown', fall through
            pass

    # ── Decision ─────────────────────────────────────────────────────────────
    # Case A: remote build_id fetched successfully — compare directly
    if remote_build_id is not None:
        if remote_build_id == local_build_id:
            return jsonify({'status': 'up_to_date',
                            'version': lookup_version,
                            'build_id': remote_build_id})
        # IDs differ (or no local ID) → fall through to launch

    # Case B: no remote build_id (old release / network error) — version fallback
    else:
        if lookup_version and stored_version and has_pkgs and stored_version == lookup_version:
            return jsonify({'status': 'up_to_date', 'version': stored_version})

    # Launch toolchain_setup.py to download the new build.
    # Pass --force-download so it skips the "version already matches" check
    # (Case 1) and re-downloads even when the ESPHome version is unchanged
    # but a newer build tarball has been published (different build_id).
    setup_script = '/app/toolchain_setup.py'
    if not os.path.exists(setup_script):
        return jsonify({'error': 'toolchain_setup.py not found'}), 500

    log_file = open('/tmp/toolchain_setup.log', 'w')
    proc = subprocess.Popen(
        ['python3', setup_script, '--force-download'],
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
    )
    with open('/tmp/toolchain_setup.pid', 'w') as f:
        f.write(str(proc.pid))
    return jsonify({'status': 'started'})

