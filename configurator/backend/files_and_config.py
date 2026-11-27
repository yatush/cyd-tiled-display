import os
import re
import json
import time
import shutil
import hashlib
import zipfile
import yaml
import requests
from flask import Blueprint, request, jsonify, current_app
import generate_tiles_api
from github_sync import sync_github_files
from backend.state import (
    APP_DIR,
    BASE_DIR,
    IS_ADDON,
    _DEVICE_CONFIG,
    _DEFAULT_DEVICE,
    _load_device_configs,
    _resolve_safe_path,
    _run_generate_subprocess,
)

files_bp = Blueprint('files', __name__)

@files_bp.route('/api/generate', methods=['POST'])
def generate():
    try:
        input_data = request.get_data(as_text=True)
        _lib_dir = os.path.join(BASE_DIR, 'lib')
        if not os.path.exists(_lib_dir):
            _lib_dir = os.path.join(APP_DIR, 'esphome/lib')
        # PNG files live inside lib/images/ so ESPHome resolves
        # "file: images/foo.png" relative to lib_common.yaml (which is in lib/).
        _images_dir = os.path.join(_lib_dir, 'images')
        result = _run_generate_subprocess(input_data, lib_dir=_lib_dir, images_dir=_images_dir)
        
        if "error" in result:
            print(f"Generation Error: {result['error']}", flush=True)
            return jsonify(result), 500
            
        return jsonify(result)
    except Exception as e:
        print(f"Server Error: {str(e)}", flush=True)
        return jsonify({"error": str(e)}), 500


@files_bp.route('/api/files', methods=['GET'])
def list_files():
    try:
        path = request.args.get('path', '')
        if not os.path.exists(BASE_DIR):
            # Ensure base dir exists
            os.makedirs(BASE_DIR, exist_ok=True)

        full_path = _resolve_safe_path(path, allow_empty=True)
        if not full_path:
            return jsonify({"error": "Invalid path"}), 400
        
        if not os.path.exists(full_path):
            return jsonify({"error": "Path not found"}), 404
            
        items = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            is_dir = os.path.isdir(item_path)
            # Only show .yaml files or directories
            if is_dir or item.endswith('.yaml') or item.endswith('.yml'):
                items.append({
                    "name": item,
                    "is_dir": is_dir,
                    "path": os.path.relpath(item_path, BASE_DIR).replace('\\', '/')
                })
        
        # Sort: directories first, then files
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return jsonify({
            "current_path": path,
            "items": items
        })
    except Exception as e:
        print(f"List Files Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@files_bp.route('/api/mkdir', methods=['POST'])
def make_directory():
    try:
        data = request.get_json() or {}
        path = data.get('path', '')
        full_path = _resolve_safe_path(path, allow_empty=False)
        if not full_path:
            return jsonify({"error": "Invalid path"}), 400
        
        os.makedirs(full_path, exist_ok=True)
        return jsonify({"success": True, "path": path})
    except Exception as e:
        print(f"Mkdir Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# Hardware Overrides Validation
# ============================================================

def _collect_lib_ids(screen_type=None):
    """Scan YAML files in the lib directory and return a set of declared IDs.

    If screen_type is provided (e.g. '2432s028' or '3248s035'), base files for
    the OTHER screen type are skipped so validation reflects the actual device.
    """
    lib_dir = os.path.join(BASE_DIR, 'lib')
    ids = set()
    if not os.path.isdir(lib_dir):
        return ids
    import re
    id_re = re.compile(r'^\s+id:\s+([A-Za-z_][A-Za-z0-9_]*)\s*$')
    for fname in os.listdir(lib_dir):
        if not fname.endswith('.yaml') and not fname.endswith('.yml'):
            continue
        # When a specific screen type is given, skip the other screen's base file
        if screen_type and fname.endswith('_base.yaml') and not fname.startswith(screen_type):
            continue
        fpath = os.path.join(lib_dir, fname)
        try:
            with open(fpath, 'r', errors='replace') as f:
                for line in f:
                    m = id_re.match(line)
                    if m:
                        ids.add(m.group(1))
        except Exception:
            pass
    return ids


def _flatten_dict(d, prefix=''):
    """Recursively flatten a dict into a list of {key, value} pairs using dot notation."""
    result = []
    if not isinstance(d, dict):
        return result
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            result.extend(_flatten_dict(v, full_key))
        else:
            result.append({"key": full_key, "value": v})
    return result


def _parse_hw_overrides(yaml_text, screen_type=None):
    """Parse hw_overrides YAML text and return a list of override entries.

    Each entry: {component_type, id, id_found, changes: [{key, value}]}
    Returns (overrides_list, parse_error_string_or_None).
    """
    class _ExtendTag:
        def __init__(self, value):
            self.value = value

    class _ExtendLoader(yaml.SafeLoader):
        pass

    def _construct_extend(loader, node):
        return _ExtendTag(loader.construct_scalar(node))

    def _ignore_tag(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        else:
            return loader.construct_mapping(node)

    _ExtendLoader.add_constructor('!extend', _construct_extend)
    _ExtendLoader.add_multi_constructor('!', _ignore_tag)

    try:
        doc = yaml.load(yaml_text, Loader=_ExtendLoader)
    except yaml.YAMLError as e:
        return [], str(e)

    if not isinstance(doc, dict):
        return [], None

    known_ids = _collect_lib_ids(screen_type)
    overrides = []

    for component_type, entries in doc.items():
        # A dict means the user forgot the list dash "-" — always an error
        if isinstance(entries, dict):
            id_val = entries.get('id')
            extend_id = id_val.value if isinstance(id_val, _ExtendTag) else '<some_id>'
            return [], (
                f"'{component_type}' override is missing the list dash '-'.\n"
                f"Change:\n  {component_type}:\n    id: !extend {extend_id}\n    ...\n"
                f"To:\n  {component_type}:\n    - id: !extend {extend_id}\n    ..."
            )
        if not isinstance(entries, list):
            # Bare scalar or other unexpected value
            return [], (
                f"Unexpected value for '{component_type}': {repr(entries)}\n"
                f"Each top-level key must be a list of component entries, e.g.:\n"
                f"  {component_type}:\n    - id: !extend <some_id>\n    ..."
            )
        for entry in entries:
            if not isinstance(entry, dict):
                return [], (
                    f"Unexpected item in '{component_type}' list: {repr(entry)}\n"
                    f"Each list item must be a mapping with 'id: !extend <id>', e.g.:\n"
                    f"  {component_type}:\n    - id: !extend <some_id>\n    ..."
                )
            id_val = entry.get('id')
            if id_val is None:
                return [], (
                    f"An entry under '{component_type}' is missing the 'id: !extend <id>' key.\n"
                    f"Each list item must start with 'id: !extend <some_id>'."
                )
            if not isinstance(id_val, _ExtendTag):
                return [], (
                    f"'{component_type}' entry has 'id: {id_val}' but is missing the '!extend' tag.\n"
                    f"Change:\n  - id: {id_val}\n"
                    f"To:\n  - id: !extend {id_val}"
                )
            extend_id = id_val.value
            # Build changes from the rest of the entry (everything except 'id')
            rest = {k: v for k, v in entry.items() if k != 'id'}
            changes = _flatten_dict(rest)
            overrides.append({
                "component_type": component_type,
                "id": extend_id,
                "id_found": extend_id in known_ids,
                "changes": changes,
            })

    return overrides, None


@files_bp.route('/api/hw_overrides/validate', methods=['GET', 'POST'])
def validate_hw_overrides():
    """Validate hw_overrides.yaml.

    GET  — reads lib/hw_overrides.yaml from disk.
    POST — accepts {"yaml_text": "..."} to validate unsaved editor content.
    """
    try:
        hw_overrides_path = os.path.join(BASE_DIR, 'lib', 'hw_overrides.yaml')

        if request.method == 'POST':
            body = request.get_json(silent=True) or {}
            yaml_text = body.get('yaml_text', '')
            screen_type = body.get('screen_type') or None
        else:
            screen_type = request.args.get('screen_type') or None
            if not os.path.exists(hw_overrides_path):
                return jsonify({"overrides": [], "parse_error": None})
            with open(hw_overrides_path, 'r', errors='replace') as f:
                yaml_text = f.read()

        overrides, parse_error = _parse_hw_overrides(yaml_text, screen_type)
        return jsonify({"overrides": overrides, "parse_error": parse_error})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@files_bp.route('/api/save', methods=['POST'])
def save_config():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        config_data = data.get('config')
        # path is relative to BASE_DIR
        rel_path = data.get('path', 'monitor_config/tiles.yaml')
        target_path = _resolve_safe_path(rel_path)
        if not target_path:
            return jsonify({"error": "Invalid path"}), 400
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        if isinstance(config_data, str):
            with open(target_path, 'w') as f:
                f.write(config_data)
            if re.search(r'^tuya_ble_fan:', config_data, flags=re.MULTILINE):
                try:
                    loader_cls = generate_tiles_api.create_safe_yaml_loader()
                    parsed_saved = yaml.load(config_data, Loader=loader_cls)
                    if isinstance(parsed_saved, dict):
                        saved_fans = (parsed_saved.get('tuya_ble_fan') or {}).get('fans')
                        if isinstance(saved_fans, list):
                            __import__('backend.ble_hubs', fromlist=['save_ble_fans_to_vault']).save_ble_fans_to_vault(saved_fans, os.path.dirname(target_path))
                except Exception:
                    pass
        else:
            with open(target_path, 'w') as f:
                yaml.dump(config_data, f, sort_keys=False)
            
        return jsonify({"success": True, "path": rel_path})
    except Exception as e:
        print(f"Save Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@files_bp.route('/api/load', methods=['GET'])
def load_config():
    try:
        # path is relative to BASE_DIR
        rel_path = request.args.get('path', 'monitor_config/tiles.yaml')
        raw_mode = request.args.get('raw', '').lower() in ('1', 'true', 'yes')

        target_path = _resolve_safe_path(rel_path)
        if not target_path:
            return jsonify({"error": "Invalid path"}), 400

        # Raw mode: return plain text (preserves comments, used by hw_overrides editor)
        if raw_mode:
            if not os.path.exists(target_path):
                return '', 404
            with open(target_path, 'r', errors='replace') as f:
                return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}

        if os.path.exists(target_path):
            loader_cls = generate_tiles_api.create_safe_yaml_loader()
            with open(target_path, 'r') as f:
                return jsonify(yaml.load(f, Loader=loader_cls))
        
        return jsonify({"error": f"Config file {rel_path} not found"}), 404
    except Exception as e:
        print(f"Load Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@files_bp.route('/api/load_raw', methods=['GET'])
def load_config_raw():
    """Return the raw text content of a file (not YAML-parsed). Used by the HW overrides editor."""
    try:
        rel_path = request.args.get('path', '')
        target_path = _resolve_safe_path(rel_path)
        if not target_path:
            return jsonify({"error": "Invalid path"}), 400
        if not os.path.exists(target_path):
            return '', 404
        with open(target_path, 'r', errors='replace') as f:
            return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@files_bp.route('/api/schema', methods=['GET'])
def get_schema():
    schema_path = os.path.join(BASE_DIR, 'external_components/tile_ui/schema.json')
    if not os.path.exists(schema_path):
        schema_path = os.path.join(APP_DIR, 'esphome/external_components/tile_ui/schema.json')
    if os.path.exists(schema_path):
        with open(schema_path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Schema not found"}), 404

@files_bp.route('/api/sync_github_lib', methods=['POST'])
def sync_github_lib():
    if not IS_ADDON:
        return jsonify({"error": "GitHub sync is only available in add-on mode"}), 403
    try:
        def validate_lib(lib_dir):
            configs = _load_device_configs(lib_dir)
            if _DEFAULT_DEVICE not in configs:
                raise ValueError("GitHub archive has an invalid default device configuration")

        count = sync_github_files(BASE_DIR, validate_lib)
        _DEVICE_CONFIG.clear()
        _DEVICE_CONFIG.update(_load_device_configs(os.path.join(BASE_DIR, 'lib')))
        return jsonify({"success": True, "count": count})
    except (OSError, ValueError, RuntimeError, requests.RequestException, zipfile.BadZipFile) as error:
        current_app.logger.exception("GitHub sync failed")
        return jsonify({"error": str(error)}), 500

@files_bp.route('/api/update_lib', methods=['POST'])
def update_lib():
    try:
        # Update lib with backup
        source_lib = os.path.join(APP_DIR, 'esphome/lib')
        target_lib = os.path.join(BASE_DIR, 'lib')
        backup_lib = os.path.join(BASE_DIR, 'lib_old')
        
        # If source and target are the same (local dev), skip
        if os.path.abspath(source_lib) == os.path.abspath(target_lib):
             return jsonify({"success": True, "message": "Source and target are the same (local dev)"})

        if os.path.exists(source_lib):
            if os.path.exists(target_lib):
                if os.path.exists(backup_lib):
                    shutil.rmtree(backup_lib)
                shutil.move(target_lib, backup_lib)
            shutil.copytree(source_lib, target_lib, ignore=shutil.ignore_patterns('.*', 'user_config.yaml', 'user_config_*.yaml', 'hw_overrides.yaml', 'test_device_tiles.yaml', 'images.yaml'))

            # Restore hw_overrides.yaml: keep user's existing file, otherwise seed from template
            hw_target = os.path.join(target_lib, 'hw_overrides.yaml')
            hw_backup = os.path.join(backup_lib, 'hw_overrides.yaml')
            hw_source = os.path.join(source_lib, 'hw_overrides.yaml')
            if os.path.exists(hw_backup):
                shutil.copy2(hw_backup, hw_target)
            elif os.path.exists(hw_source):
                shutil.copy2(hw_source, hw_target)
            
        # Update external components (tile_ui, tuya_ble_fan, espnow_fan_bridge, and shelly_ble_bridge) without backup
        for comp_name in ('tile_ui', 'tuya_ble_fan', 'espnow_fan_bridge', 'shelly_ble_bridge'):
            source_comp = os.path.join(APP_DIR, 'esphome/external_components', comp_name)
            target_comp = os.path.join(BASE_DIR, 'external_components', comp_name)
            if os.path.exists(source_comp):
                if os.path.exists(target_comp):
                    shutil.rmtree(target_comp)
                os.makedirs(os.path.dirname(target_comp), exist_ok=True)
                shutil.copytree(
                    source_comp,
                    target_comp,
                    ignore=shutil.ignore_patterns('.*', 'tests', '__pycache__'),
                )

        # Update default device YAML files (overwrite if changed, seed if missing).
        for fname in _DEFAULT_DEVICE_YAMLS:
            src = os.path.join(APP_DIR, 'esphome', fname)
            dst = os.path.join(BASE_DIR, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Update Lib Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def get_directory_hashes(directory):
    if not os.path.exists(directory):
        return {}
    
    file_hashes = {}
    for root, dirs, files in os.walk(directory):
        # Filter out hidden directories and the images/ dir to prevent recursion
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'images']
        dirs.sort() # Ensure deterministic traversal
        for file in sorted(files):
            if '_custom.' in file or '__pycache__' in root or file.endswith('.pyc') or file == 'user_config.yaml' or file.startswith('user_config_') or file == 'hw_overrides.yaml' or file.startswith('.'):                continue
            path = os.path.join(root, file)
            rel_path = os.path.relpath(path, directory).replace('\\', '/')
            if rel_path == 'images.yaml':
                continue
            try:
                with open(path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                    file_hashes[rel_path] = file_hash
            except:
                pass
    return file_hashes

# Device YAML files (shipped with the addon) that should be tracked in diffs and synced on update.
_DEFAULT_DEVICE_YAMLS = ['test_device.yaml']

def get_diff(source_hashes, target_hashes):
    diff = []
    all_files = set(source_hashes.keys()) | set(target_hashes.keys())
    
    # Generated/temp files that should never appear in the diff
    _IGNORED_FILES = {'test_device_tiles.yaml'}

    for f in sorted(all_files):
        # Ignore test files — they are dev-only and not deployed to HA
        if f.startswith('tests/') or f.startswith('tests\\'):
            continue
        # Ignore generated artifacts
        if os.path.basename(f) in _IGNORED_FILES:
            continue
        if f not in source_hashes:
            # Ignore PNG files that exist only in the target (they are generated artifacts)
            if f.endswith('.png'):
                continue
            diff.append(f"{f} (Extra in target)")
        elif f not in target_hashes:
            diff.append(f"{f} (Missing in target)")
        elif source_hashes[f] != target_hashes[f]:
            diff.append(f"{f} (Modified)")
            
    return diff

@files_bp.route('/api/check_lib_status')
def check_lib_status():
    try:
        source_lib = os.path.join(APP_DIR, 'esphome/lib')
        target_lib = os.path.join(BASE_DIR, 'lib')
        
        source_ui = os.path.join(APP_DIR, 'esphome/external_components/tile_ui')
        target_ui = os.path.join(BASE_DIR, 'external_components/tile_ui')
        
        # If source and target are the same (local dev), they are synced
        if os.path.abspath(source_lib) == os.path.abspath(target_lib):
            return jsonify({
                "lib_synced": True,
                "ui_synced": True,
                "synced": True,
                "details": []
            })

        source_lib_hashes = get_directory_hashes(source_lib)
        target_lib_hashes = get_directory_hashes(target_lib)
        lib_diff = get_diff(source_lib_hashes, target_lib_hashes)
        
        source_ui_hashes = get_directory_hashes(source_ui)
        target_ui_hashes = get_directory_hashes(target_ui)
        ui_diff = get_diff(source_ui_hashes, target_ui_hashes)

        for comp_name in ('tuya_ble_fan', 'espnow_fan_bridge', 'shelly_ble_bridge'):
            source_comp = os.path.join(APP_DIR, 'esphome/external_components', comp_name)
            target_comp = os.path.join(BASE_DIR, 'external_components', comp_name)
            if os.path.exists(source_comp):
                comp_diff = get_diff(
                    get_directory_hashes(source_comp),
                    get_directory_hashes(target_comp),
                )
                ui_diff.extend([f"{comp_name}/{d}" for d in comp_diff])

        # For device yamls: flag if missing or modified vs the shipped version,
        # but never complain about extra yamls the user added themselves.
        def _md5_file(path):
            try:
                with open(path, 'rb') as _f:
                    return hashlib.md5(_f.read()).hexdigest()
            except Exception:
                return None

        device_diff = []
        for fname in _DEFAULT_DEVICE_YAMLS:
            src_hash = _md5_file(os.path.join(APP_DIR, 'esphome', fname))
            if src_hash is None:
                continue  # source doesn't exist, nothing to check
            dst_hash = _md5_file(os.path.join(BASE_DIR, fname))
            if dst_hash is None:
                device_diff.append(f"{fname} (Missing in target)")
            elif src_hash != dst_hash:
                device_diff.append(f"{fname} (Modified)")

        lib_synced = len(lib_diff) == 0
        ui_synced = len(ui_diff) == 0
        device_synced = len(device_diff) == 0
        
        details = []
        if not lib_synced:
            details.append("Library files:")
            details.extend([f"  - {d}" for d in lib_diff])
        if not ui_synced:
            details.append("UI Component files:")
            details.extend([f"  - {d}" for d in ui_diff])
        if not device_synced:
            details.append("Device files:")
            details.extend([f"  - {d}" for d in device_diff])

        return jsonify({
            "lib_synced": lib_synced,
            "ui_synced": ui_synced,
            "synced": lib_synced and ui_synced and device_synced,
            "details": details
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@files_bp.route('/api/scripts')
def get_scripts():
    try:
        # Determine source directory once
        # Check BASE_DIR first (User config)
        source_dir = os.path.join(BASE_DIR, 'lib')
        if not os.path.exists(source_dir):
            # Fallback to APP_DIR (Default lib)
            source_dir = os.path.join(APP_DIR, 'esphome/lib')

        doc = generate_tiles_api.load_merged_lib_doc(
            user_lib_dir=source_dir,
            fallback_lib_dir=os.path.join(APP_DIR, 'esphome/lib'),
            merge_keys=('script', 'color', 'globals'),
        )
        if doc is None:
            return jsonify({"error": f"lib.yaml not found in {source_dir}"}), 404

        scripts = doc.get('script', [])
        
        # Standard colors — Color(r, g, b) in RGB order, value is the matching CSS hex
        colors = [
            {'id': 'Color(0, 0, 0)',       'value': '#000000'},
            {'id': 'Color(255, 255, 255)', 'value': '#FFFFFF'},
            {'id': 'Color(255, 0, 0)',     'value': '#FF0000'},
            {'id': 'Color(0, 255, 0)',     'value': '#00FF00'},
            {'id': 'Color(0, 0, 255)',     'value': '#0000FF'},
            {'id': 'Color(255, 255, 0)',   'value': '#FFFF00'},
            {'id': 'Color(255, 165, 0)',   'value': '#FFA500'},
            {'id': 'Color(128, 0, 128)',   'value': '#800080'},
        ]

        # Add custom colors from lib.yaml
        for c in doc.get('color', []):
            value = '#000000'
            if 'hex' in c:
                hex_val = c['hex'].replace('#', '')
                if len(hex_val) == 6:
                    value = f"#{hex_val}"
                else:
                    value = f"#{hex_val}"
            elif all(k in c for k in ('red', 'green', 'blue')):
                # Simplified RGB handling
                value = f"rgb({c['red']}, {c['green']}, {c['blue']})"
            colors.append({'id': c['id'], 'value': value})

        # Fonts from base files in SAME directory
        fonts = []
        base_loader = generate_tiles_api.create_safe_yaml_loader()
        for base_file in ['3248s035_base.yaml', '2432s028_base.yaml']:
            base_path = os.path.join(source_dir, base_file)
            if os.path.exists(base_path):
                try:
                    with open(base_path, 'r') as f:
                        base_doc = yaml.load(f, Loader=base_loader) or {}
                        for font in base_doc.get('font', []):
                            if 'id' in font and font['id'] not in fonts:
                                fonts.append(font['id'])
                except Exception as e:
                    print(f"Error loading fonts from {base_file}: {e}")

        # Icons from mdi_glyphs.yaml in SAME directory
        icons = []
        glyphs_path = os.path.join(source_dir, 'mdi_glyphs.yaml')
        if os.path.exists(glyphs_path):
            with open(glyphs_path, 'r') as f:
                for line in f:
                    import re
                    match = re.search(r'"\\U([0-9a-fA-F]+)",\s*#\s*(.*)', line)
                    if match:
                        hex_code = match.group(1)
                        label = match.group(2).strip()
                        icons.append({
                            'value': f"\\U{hex_code}",
                            'label': label
                        })

        scripts_list = []

        for s in scripts:
            if 'id' in s:
                params = s.get('parameters', {})
                param_list = [
                    {'name': k, 'type': v}
                    for k, v in params.items()
                    if k not in ('x', 'y', 'entities', 'x_start', 'y_start', 'x_end', 'y_end')
                ]
                scripts_list.append({'id': s['id'], 'params': param_list})

        globals_list = [
            g['id'] for g in doc.get('globals', [])
            if g.get('type') == 'bool'
        ]

        return jsonify({
            "scripts": scripts_list,
            "colors": colors,
            "fonts": fonts,
            "icons": icons,
            "globals": globals_list
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

