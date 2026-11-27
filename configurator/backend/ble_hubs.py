import os
import re
import json
import time
import asyncio
import concurrent.futures
import secrets
import yaml
import requests
from flask import Blueprint, request, jsonify
from aioesphomeapi import APIClient
import generate_tiles_api
from backend.state import (
    APP_DIR,
    BASE_DIR,
    HA_URL,
    IS_ADDON,
    SUPERVISOR_TOKEN,
    _CACHED_SHELLY_KNOWN_NAMES,
    _resolve_safe_path,
    is_headless_hub_yaml,
)
from backend.esphome_builds import _check_device_online, _parse_device_yaml

ble_hubs_bp = Blueprint('ble_hubs', __name__)

_KNOWN_TUYA_FAN_PRODUCT_IDS = {
    "vfqiwthdnlkynebk",  # Varin VA-E002
    "hceemlamlwxpufpa",  # Sofucor KBS
}


def discover_tuya_ble_fans(ha_config_dir=None):
    """Inspect Home Assistant .storage files to discover Tuya local fans and their companion lights."""
    cfg_dir = ha_config_dir or os.environ.get('HA_CONFIG_DIR', '/config')
    entries_path = os.path.join(cfg_dir, '.storage', 'core.config_entries')
    registry_path = os.path.join(cfg_dir, '.storage', 'core.entity_registry')
    device_registry_path = os.path.join(cfg_dir, '.storage', 'core.device_registry')

    if not os.path.exists(entries_path):
        return []

    try:
        with open(entries_path, 'r', encoding='utf-8') as f:
            entries_doc = json.load(f)
    except Exception as e:
        print(f"[tuya_ble_fans] Failed to read {entries_path}: {e}")
        return []

    # Map config_entry_id -> list of (entity_id, unique_id)
    entities_by_entry = {}
    if os.path.exists(registry_path):
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                reg_doc = json.load(f)
            for ent in reg_doc.get('data', {}).get('entities', []):
                if not isinstance(ent, dict) or ent.get('disabled_by'):
                    continue
                entry_id = ent.get('config_entry_id')
                entity_id = ent.get('entity_id', '')
                unique_id = str(ent.get('unique_id') or '')
                if not entry_id or not entity_id:
                    continue
                entities_by_entry.setdefault(entry_id, []).append((entity_id, unique_id))
        except Exception as e:
            print(f"[tuya_ble_fans] Failed to read {registry_path}: {e}")

    # Map config_entry_id / tuya device_id -> MAC address from core.device_registry
    mac_by_entry = {}
    mac_by_identifier = {}
    if os.path.exists(device_registry_path):
        try:
            with open(device_registry_path, 'r', encoding='utf-8') as f:
                dev_doc = json.load(f)
            for dev in dev_doc.get('data', {}).get('devices', []):
                if not isinstance(dev, dict):
                    continue
                mac_val = ''
                for conn in dev.get('connections') or []:
                    if isinstance(conn, (list, tuple)) and len(conn) >= 2 and str(conn[0]).lower() == 'mac':
                        mac_val = str(conn[1]).strip().upper()
                        break
                if not mac_val:
                    continue
                for ce_id in dev.get('config_entries') or []:
                    mac_by_entry.setdefault(ce_id, mac_val)
                for ident in dev.get('identifiers') or []:
                    if isinstance(ident, (list, tuple)) and len(ident) >= 2:
                        mac_by_identifier.setdefault(str(ident[1]).strip(), mac_val)
        except Exception as e:
            print(f"[tuya_ble_fans] Failed to read {device_registry_path}: {e}")

    fans = []
    seen_device_ids = set()
    for entry in entries_doc.get('data', {}).get('entries', []):
        if not isinstance(entry, dict) or entry.get('disabled_by'):
            continue
        domain = entry.get('domain', '')
        if domain not in ('tuya_local', 'localtuya'):
            continue

        entry_id = entry.get('entry_id', '')
        title = entry.get('title') or ''
        data = entry.get('data') or {}
        options = entry.get('options') or {}

        # Normalize both tuya_local (single device per entry) and localtuya (devices dict)
        is_multi_hub = False
        raw_devices = []
        if 'device_id' in data and 'local_key' in data:
            raw_devices.append((title, data))
        elif isinstance(data.get('devices'), dict):
            is_multi_hub = True
            for dev_id, dev_cfg in data['devices'].items():
                if isinstance(dev_cfg, dict) and dev_cfg.get('local_key'):
                    merged = dict(dev_cfg)
                    merged.setdefault('device_id', dev_id)
                    raw_devices.append((dev_cfg.get('friendly_name') or title, merged))

        entry_entities = entities_by_entry.get(entry_id, [])

        for dev_name, dev_data in raw_devices:
            device_id = str(dev_data.get('device_id') or '').strip()
            local_key = str(dev_data.get('local_key') or '').strip()
            if not device_id or not local_key or device_id in seen_device_ids:
                continue

            product_id = str(
                dev_data.get('product_id')
                or options.get('product_id')
                or dev_data.get('model')
                or ''
            ).strip()

            if is_multi_hub:
                dev_entities = [eid for eid, uid in entry_entities if device_id in uid]
            else:
                dev_entities = [eid for eid, _uid in entry_entities]

            fan_entities = sorted(e for e in dev_entities if e.startswith('fan.'))
            light_entities = sorted(e for e in dev_entities if e.startswith('light.'))

            fan_entity_id = fan_entities[0] if fan_entities else ''
            light_entity_id = light_entities[0] if light_entities else ''

            is_known_product = product_id in _KNOWN_TUYA_FAN_PRODUCT_IDS
            if not fan_entity_id and not is_known_product:
                # Skip non-fan tuya_local/localtuya devices (plugs, heaters, etc.)
                continue

            mac_address = str(
                dev_data.get('mac_address')
                or dev_data.get('mac')
                or mac_by_identifier.get(device_id)
                or (mac_by_entry.get(entry_id) if not is_multi_hub else '')
                or ''
            ).strip().upper()
            uuid_val = str(dev_data.get('uuid') or '').strip()

            seen_device_ids.add(device_id)
            fans.append({
                'name': dev_name or fan_entity_id or device_id,
                'device_id': device_id,
                'local_key': local_key,
                'product_id': product_id,
                'mac_address': mac_address,
                'uuid': uuid_val,
                'fan_entity_id': fan_entity_id,
                'light_entity_id': light_entity_id,
                'supported': is_known_product or bool(fan_entity_id),
            })

    return fans


BLE_FAN_VAULT_FILENAME = '.cyd_ble_fans.json'


def _ble_fan_vault_path(esphome_dir=None):
    root_dir = esphome_dir or BASE_DIR
    return os.path.join(root_dir, BLE_FAN_VAULT_FILENAME)


def load_ble_fan_vault(esphome_dir=None):
    """Load persisted BLE fan credentials from /config/esphome/.cyd_ble_fans.json."""
    path = _ble_fan_vault_path(esphome_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('fans'), dict):
            return dict(data['fans'])
    except Exception:
        pass
    return {}


def save_ble_fans_to_vault(fans, esphome_dir=None):
    """Upsert BLE fan credentials (device_id + local_key) into .cyd_ble_fans.json without deleting existing entries."""
    if not fans:
        return load_ble_fan_vault(esphome_dir)
    root_dir = esphome_dir or BASE_DIR
    if not root_dir or not os.path.isdir(root_dir):
        return {}

    vault = load_ble_fan_vault(root_dir)
    changed = False
    for fan in fans:
        if not isinstance(fan, dict):
            continue
        dev_id = str(fan.get('device_id') or '').strip()
        local_key = str(fan.get('local_key') or '').strip()
        if not dev_id or not local_key:
            continue
        prev = dict(vault.get(dev_id) or {})
        merged = {
            'name': str(fan.get('name') or prev.get('name') or dev_id).strip(),
            'device_id': dev_id,
            'local_key': local_key,
            'product_id': str(fan.get('product_id') or prev.get('product_id') or '').strip(),
            'mac_address': str(fan.get('mac_address') or prev.get('mac_address') or '').strip().upper(),
            'uuid': str(fan.get('uuid') or prev.get('uuid') or '').strip(),
            'fan_entity_id': str(fan.get('fan_entity_id') or prev.get('fan_entity_id') or '').strip(),
            'light_entity_id': str(fan.get('light_entity_id') or prev.get('light_entity_id') or '').strip(),
            'supported': True,
        }
        if merged != prev:
            vault[dev_id] = merged
            changed = True

    if changed:
        raw = _load_ble_vault_raw(root_dir)
        raw['version'] = 1
        raw['fans'] = vault
        _write_ble_vault_raw(raw, root_dir)
    return vault


def _load_ble_vault_raw(esphome_dir=None):
    path = _ble_fan_vault_path(esphome_dir)
    if not os.path.isfile(path):
        return {'version': 1, 'fans': {}}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            if not isinstance(data.get('fans'), dict):
                data['fans'] = {}
            return data
    except Exception:
        pass
    return {'version': 1, 'fans': {}}


def _write_ble_vault_raw(data, esphome_dir=None):
    root_dir = esphome_dir or BASE_DIR
    if not root_dir or not os.path.isdir(root_dir):
        return
    path = _ble_fan_vault_path(root_dir)
    tmp_path = f'{path}.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True)
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


DEFAULT_ESPNOW_NETWORK_KEY = 'cyd_espnow_default'


def get_or_create_espnow_network_key(esphome_dir=None):
    """Return ESP-NOW network key from .cyd_ble_fans.json or deterministic default for multi-host portability."""
    root_dir = esphome_dir or BASE_DIR
    raw = _load_ble_vault_raw(root_dir)
    key = str(raw.get('espnow_network_key') or '').strip()
    return key or DEFAULT_ESPNOW_NETWORK_KEY


def collect_yaml_ble_fans(esphome_dir=None):
    """Extract all tuya_ble_fan.fans entries currently configured in CYD device YAMLs."""
    root_dir = esphome_dir or BASE_DIR
    collected = []
    if not root_dir or not os.path.isdir(root_dir):
        return collected
    loader_cls = generate_tiles_api.create_safe_yaml_loader()
    for fname in sorted(os.listdir(root_dir)):
        if not (fname.endswith('.yaml') or fname.endswith('.yml')) or fname in ('secrets.yaml', 'images.yaml'):
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            if not re.search(r'^tuya_ble_fan:', raw_text, flags=re.MULTILINE):
                continue
            parsed = yaml.load(raw_text, Loader=loader_cls)
            if not isinstance(parsed, dict):
                continue
            fans = (parsed.get('tuya_ble_fan') or {}).get('fans')
            if isinstance(fans, list):
                for item in fans:
                    if isinstance(item, dict) and item.get('device_id') and item.get('local_key'):
                        collected.append(dict(item))
        except Exception:
            continue
    return collected


def get_all_known_tuya_ble_fans(ha_config_dir=None, esphome_dir=None):
    """Return deduplicated BLE fans from HA storage, CYD YAMLs, and the persistent .cyd_ble_fans.json vault."""
    ha_fans = discover_tuya_ble_fans(ha_config_dir)
    yaml_fans = collect_yaml_ble_fans(esphome_dir)
    vault = save_ble_fans_to_vault(ha_fans + yaml_fans, esphome_dir)

    by_id = {}
    for fan in ha_fans:
        dev_id = str(fan.get('device_id') or '').strip()
        if dev_id:
            by_id[dev_id] = dict(fan)
    for dev_id, vfan in vault.items():
        if dev_id in by_id:
            # Enrich HA entry with cached MAC/UUID if missing
            for k in ('mac_address', 'uuid', 'product_id'):
                if not by_id[dev_id].get(k) and vfan.get(k):
                    by_id[dev_id][k] = vfan[k]
        else:
            by_id[dev_id] = dict(vfan)

    return sorted(by_id.values(), key=lambda x: (str(x.get('name') or '').lower(), str(x.get('device_id') or '')))


def find_ble_fan_hosts(esphome_dir=None):
    """Scan ESPHome device YAMLs to find which device files already host each Tuya BLE fan device_id."""
    by_id, _by_mac, _by_uuid = _find_ble_fan_hosts_extended(esphome_dir)
    return by_id


@ble_hubs_bp.route('/api/tuya_ble_fans', methods=['GET'])
def get_tuya_ble_fans():
    try:
        fans = get_all_known_tuya_ble_fans()
        hosted_by = find_ble_fan_hosts()
        hubs = list_ble_hubs()
        network_key = get_or_create_espnow_network_key()
        for fan in fans:
            fan['hosted_by'] = hosted_by.get(fan['device_id'], [])
        return jsonify({
            'fans': fans,
            'hosted_by': hosted_by,
            'hubs': hubs,
            'network_key': network_key,
        })
    except Exception as e:
        return jsonify({'fans': [], 'hosted_by': {}, 'hubs': [], 'error': str(e)}), 500


def _slugify_hub_name(raw_name):
    slug = re.sub(r'[^a-z0-9-]+', '-', str(raw_name or '').strip().lower())
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug


def list_ble_hubs(esphome_dir=None):
    """Discover all headless ESP32 BLE hub YAMLs in esphome_dir."""
    root_dir = esphome_dir or BASE_DIR
    hubs = []
    if not root_dir or not os.path.isdir(root_dir):
        return hubs
    try:
        entries = sorted(os.listdir(root_dir))
    except OSError:
        return hubs

    for fname in entries:
        if not fname.endswith(('.yaml', '.yml')) or fname == 'secrets.yaml':
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw_text = f.read()
        except OSError:
            continue
        if 'headless_hub_base.yaml' not in raw_text and 'espnow_fan_bridge:' not in raw_text:
            continue
        try:
            parsed = yaml.load(raw_text, Loader=generate_tiles_api.create_safe_yaml_loader())
        except Exception:
            continue
        if not is_headless_hub_yaml(parsed, raw_text):
            continue

        esphome_cfg = parsed.get('esphome') if isinstance(parsed.get('esphome'), dict) else {}
        esp32_cfg = parsed.get('esp32') if isinstance(parsed.get('esp32'), dict) else {}
        bridge_cfg = parsed.get('espnow_fan_bridge') if isinstance(parsed.get('espnow_fan_bridge'), dict) else {}
        tuya_cfg = parsed.get('tuya_ble_fan') if isinstance(parsed.get('tuya_ble_fan'), dict) else {}
        raw_fans = tuya_cfg.get('fans') if isinstance(tuya_cfg.get('fans'), list) else []

        fans = []
        for fan in raw_fans:
            if not isinstance(fan, dict):
                continue
            fans.append({
                'name': str(fan.get('name') or ''),
                'device_id': str(fan.get('device_id') or ''),
                'local_key': str(fan.get('local_key') or ''),
                'product_id': str(fan.get('product_id') or ''),
                'mac_address': str(fan.get('mac_address') or ''),
                'uuid': str(fan.get('uuid') or ''),
                'fan_entity_id': str(fan.get('fan_entity_id') or ''),
                'light_entity_id': str(fan.get('light_entity_id') or ''),
                'expose_to_ha': fan.get('expose_to_ha') is not False,
            })

        gree_ac = _extract_gree_ac_from_yaml(parsed)
        shellys, detached_switches = _extract_shelly_bridge_from_yaml(parsed)

        hubs.append({
            'filename': fname,
            'name': str(esphome_cfg.get('name') or os.path.splitext(fname)[0]),
            'friendly_name': str(esphome_cfg.get('friendly_name') or esphome_cfg.get('name') or os.path.splitext(fname)[0]),
            'board': str(esp32_cfg.get('board') or 'esp32dev'),
            'fallback_channel': int(bridge_cfg.get('fallback_channel') or 1),
            'network_key': str(bridge_cfg.get('network_key') or ''),
            'fans': fans,
            'gree_ac': gree_ac,
            'shellys': shellys,
            'detached_switches': detached_switches,
        })
    return hubs


GREE_AC_MODELS = ('generic', 'yan', 'yaa', 'yac', 'yac1fb9', 'yx1ff', 'yag', 'ybofb')


def _normalize_shelly_mac(mac):
    return re.sub(r'[^0-9a-f]', '', str(mac or '').lower())


def _normalize_shellys_config(raw_list):
    if not isinstance(raw_list, list):
        return []
    out = []
    seen = set()
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        mac = _normalize_shelly_mac(item.get('mac_address') or item.get('mac'))
        if len(mac) != 12:
            continue
        try:
            channel = max(0, min(3, int(item.get('channel') or 0)))
        except (TypeError, ValueError):
            channel = 0
        entity_id = str(item.get('entity_id') or '').strip()
        kind = str(item.get('kind') or '').strip().lower()
        if kind not in ('switch', 'light', 'cover'):
            if entity_id.startswith('cover.'):
                kind = 'cover'
            elif entity_id.startswith('light.'):
                kind = 'light'
            else:
                kind = 'switch'
        key = (mac, channel, entity_id)
        if key in seen:
            continue
        seen.add(key)
        entry = {
            'name': str(item.get('name') or entity_id or mac).strip(),
            'mac_address': mac,
            'channel': channel,
            'kind': kind,
            'entity_id': entity_id,
        }
        if str(item.get('ip') or '').strip():
            entry['ip'] = str(item['ip']).strip()
        out.append(entry)
    return out


def _normalize_detached_switches_config(raw_list):
    if not isinstance(raw_list, list):
        return []
    out = []
    seen = set()
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        mac = _normalize_shelly_mac(item.get('mac_address') or item.get('mac'))
        if len(mac) != 12:
            continue
        try:
            in_ch = max(0, min(3, int(item.get('input_channel') or 0)))
        except (TypeError, ValueError):
            in_ch = 0
        target_fan_id = str(item.get('target_fan_device_id') or '').strip()
        target_light = str(item.get('target_light_entity_id') or '').strip()
        if not target_fan_id and not target_light:
            continue
        key = (mac, in_ch, target_fan_id, target_light)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            'name': str(item.get('name') or f'{mac} in:{in_ch}').strip(),
            'mac_address': mac,
            'input_channel': in_ch,
            'target_fan_device_id': target_fan_id,
            'target_light_entity_id': target_light,
        })
    return out


def _extract_shelly_bridge_from_yaml(parsed):
    if not isinstance(parsed, dict):
        return [], []
    sb = parsed.get('shelly_ble_bridge')
    if not isinstance(sb, dict):
        return [], []
    return (
        _normalize_shellys_config(sb.get('shellys')),
        _normalize_detached_switches_config(sb.get('detached_switches')),
    )


def _normalize_gree_ac_config(raw):
    """Validate and normalize an optional Gree IR AC config dict."""
    if not isinstance(raw, dict) or not raw.get('enabled'):
        return None
    ac_name = str(raw.get('name') or '').strip()
    if not ac_name:
        return None
    model = str(raw.get('model') or 'generic').strip().lower()
    if model not in GREE_AC_MODELS:
        model = 'generic'
    tx_pin = str(raw.get('tx_pin') or 'GPIO4').strip() or 'GPIO4'
    rx_pin = str(raw.get('rx_pin') if raw.get('rx_pin') is not None else 'GPIO5').strip()
    return {
        'enabled': True,
        'name': ac_name,
        'model': model,
        'tx_pin': tx_pin,
        'rx_pin': rx_pin,
        'supports_cool': raw.get('supports_cool') is not False,
        'supports_heat': raw.get('supports_heat') is not False,
        'dump_ir': bool(raw.get('dump_ir')),
    }


def _extract_gree_ac_from_yaml(parsed):
    """Extract Gree IR AC config back out of a parsed headless hub YAML."""
    if not isinstance(parsed, dict):
        return None
    climates = parsed.get('climate')
    if not isinstance(climates, list):
        return None
    gree_entry = next(
        (c for c in climates if isinstance(c, dict) and str(c.get('platform') or '').lower() == 'gree'),
        None,
    )
    if not gree_entry:
        return None

    # Resolve AC name from sub-device or climate.name
    ac_name = str(gree_entry.get('name') or '').strip()
    if ac_name.lower() == 'none':
        ac_name = ''
    dev_id = str(gree_entry.get('device_id') or '').strip()
    if not ac_name and dev_id:
        esphome_cfg = parsed.get('esphome') if isinstance(parsed.get('esphome'), dict) else {}
        devices = esphome_cfg.get('devices') if isinstance(esphome_cfg.get('devices'), list) else []
        for dev in devices:
            if isinstance(dev, dict) and str(dev.get('id') or '').strip() == dev_id:
                ac_name = str(dev.get('name') or '').strip()
                break
    if not ac_name:
        ac_name = 'Gree AC'

    tx_cfg = parsed.get('remote_transmitter')
    if isinstance(tx_cfg, list):
        tx_cfg = tx_cfg[0] if tx_cfg else {}
    tx_pin_raw = tx_cfg.get('pin') if isinstance(tx_cfg, dict) else ''
    tx_pin = str(tx_pin_raw.get('number') if isinstance(tx_pin_raw, dict) else (tx_pin_raw or 'GPIO4')).strip()

    rx_cfg = parsed.get('remote_receiver')
    if isinstance(rx_cfg, list):
        rx_cfg = rx_cfg[0] if rx_cfg else {}
    rx_pin = ''
    dump_ir = False
    if isinstance(rx_cfg, dict):
        rx_pin_raw = rx_cfg.get('pin')
        rx_pin = str(rx_pin_raw.get('number') if isinstance(rx_pin_raw, dict) else (rx_pin_raw or '')).strip()
        dump_val = rx_cfg.get('dump')
        if isinstance(dump_val, list):
            dump_ir = any(str(x).lower() in ('gree', 'raw', 'all') for x in dump_val)
        elif isinstance(dump_val, str):
            dump_ir = dump_val.lower() in ('gree', 'raw', 'all')

    model = str(gree_entry.get('model') or 'generic').strip().lower()
    if model not in GREE_AC_MODELS:
        model = 'generic'

    return {
        'enabled': True,
        'name': ac_name,
        'model': model,
        'tx_pin': tx_pin or 'GPIO4',
        'rx_pin': rx_pin,
        'supports_cool': gree_entry.get('supports_cool') is not False,
        'supports_heat': gree_entry.get('supports_heat') is not False,
        'dump_ir': dump_ir,
    }


def _find_fan_ownership_conflicts(target_filename, fans, esphome_dir=None):
    """Return list of {device_id, fan_name, fan_entity_id, host_file} for fans hosted in other YAMLs."""
    root_dir = esphome_dir or BASE_DIR
    target_norm = os.path.basename(str(target_filename or '')).lower()
    conflicts = []
    if not root_dir or not os.path.isdir(root_dir) or not fans:
        return conflicts

    wanted_ids = {str(f.get('device_id') or '').strip() for f in fans if f.get('device_id')}
    wanted_macs = {str(f.get('mac_address') or '').strip().upper() for f in fans if f.get('mac_address')}
    wanted_uuids = {str(f.get('uuid') or '').strip() for f in fans if f.get('uuid')}
    wanted_entities = {str(f.get('fan_entity_id') or '').strip().lower() for f in fans if f.get('fan_entity_id')}

    for fname in sorted(os.listdir(root_dir)):
        if not fname.endswith(('.yaml', '.yml')) or fname == 'secrets.yaml':
            continue
        if fname.lower() == target_norm:
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw_text = f.read()
        except OSError:
            continue
        if not re.search(r'^tuya_ble_fan:', raw_text, flags=re.MULTILINE):
            continue
        try:
            parsed = yaml.load(raw_text, Loader=generate_tiles_api.create_safe_yaml_loader())
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        existing_fans = (parsed.get('tuya_ble_fan') or {}).get('fans')
        if not isinstance(existing_fans, list):
            continue
        for ef in existing_fans:
            if not isinstance(ef, dict):
                continue
            eid = str(ef.get('device_id') or '').strip()
            emac = str(ef.get('mac_address') or '').strip().upper()
            euuid = str(ef.get('uuid') or '').strip()
            eent = str(ef.get('fan_entity_id') or '').strip().lower()
            if (
                (eid and eid in wanted_ids)
                or (emac and emac in wanted_macs)
                or (euuid and euuid in wanted_uuids)
                or (eent and eent in wanted_entities)
            ):
                conflicts.append({
                    'device_id': eid,
                    'fan_name': str(ef.get('name') or eid or eent),
                    'fan_entity_id': str(ef.get('fan_entity_id') or ''),
                    'host_file': fname,
                })
    return conflicts


def _remove_fans_from_host_yaml(filepath, fans_to_remove):
    """Remove matching fans from an existing Hub or CYD YAML file atomically."""
    if not os.path.isfile(filepath) or not fans_to_remove:
        return False
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    try:
        parsed = yaml.load(raw_text, Loader=generate_tiles_api.create_safe_yaml_loader())
    except Exception:
        return False
    if not isinstance(parsed, dict) or not isinstance(parsed.get('tuya_ble_fan'), dict):
        return False

    rem_ids = {str(f.get('device_id') or '').strip() for f in fans_to_remove if f.get('device_id')}
    rem_macs = {str(f.get('mac_address') or '').strip().upper() for f in fans_to_remove if f.get('mac_address')}
    rem_uuids = {str(f.get('uuid') or '').strip() for f in fans_to_remove if f.get('uuid')}
    rem_ents = {str(f.get('fan_entity_id') or '').strip().lower() for f in fans_to_remove if f.get('fan_entity_id')}

    old_fans = parsed['tuya_ble_fan'].get('fans') or []
    kept_fans = []
    for ef in old_fans:
        if not isinstance(ef, dict):
            continue
        eid = str(ef.get('device_id') or '').strip()
        emac = str(ef.get('mac_address') or '').strip().upper()
        euuid = str(ef.get('uuid') or '').strip()
        eent = str(ef.get('fan_entity_id') or '').strip().lower()
        matched = (
            (eid and eid in rem_ids)
            or (emac and emac in rem_macs)
            or (euuid and euuid in rem_uuids)
            or (eent and eent in rem_ents)
        )
        if not matched:
            kept_fans.append(ef)

    if len(kept_fans) == len(old_fans):
        return False

    updated_text = raw_text
    if kept_fans:
        new_ble = dict(parsed['tuya_ble_fan'])
        new_ble['fans'] = kept_fans
        rendered = yaml.safe_dump({'tuya_ble_fan': new_ble}, sort_keys=False, default_flow_style=False).rstrip()
        updated_text = _replace_top_level_yaml_block(updated_text, 'tuya_ble_fan', rendered)
    else:
        # Remove top-level tuya_ble_fan: block completely
        updated_text = _replace_top_level_yaml_block(updated_text, 'tuya_ble_fan', '').strip() + '\n'
        # For CYD files, also drop lib/tuya_ble_fan.yaml package include if present
        if not is_headless_hub_yaml(parsed, raw_text):
            updated_text = re.sub(
                r'^\s*tuya_ble_fan:\s*!include\s+lib/tuya_ble_fan\.yaml\s*\n?',
                '',
                updated_text,
                flags=re.MULTILINE,
            )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(updated_text)
    return True



def _render_headless_hub_yaml(name, friendly_name, board, fallback_channel, network_key, fans, gree_ac=None, shellys=None, detached_switches=None, known_names=None):
    fan_count = len(fans)
    max_conns = min(3, max(1, fan_count))
    idle_disconnect_s = 0 if (fan_count > 0 and fan_count <= max_conns) else 30

    esphome_block = {
        'name': name,
        'friendly_name': friendly_name,
    }
    if gree_ac and gree_ac.get('enabled') and gree_ac.get('name'):
        esphome_block['devices'] = [
            {
                'id': 'gree_ac_device',
                'name': gree_ac['name'],
                'relation': 'via',
            }
        ]

    lines = [
        f'# Headless ESP32 BLE Fan & IR Hub — managed by CYD Configurator',
        yaml.safe_dump({'esphome': esphome_block}, sort_keys=False, default_flow_style=False).rstrip(),
        f'',
        f'esp32:',
        f'  board: {board}',
        f'',
        f'substitutions:',
        f'  ble_max_connections: "{max_conns}"',
        f'',
        f'packages:',
        f'  headless_hub_base: !include lib/headless_hub_base.yaml',
        f'',
    ]

    bridge_block = {
        'espnow_fan_bridge': {
            'role': 'hub',
            'network_key': network_key,
            'fallback_channel': int(fallback_channel),
            'channel_sensor': {
                'name': 'WiFi ESP-NOW Channel',
            },
        }
    }
    lines.append(yaml.safe_dump(bridge_block, sort_keys=False, default_flow_style=False).rstrip())
    lines.append('')

    if fans:
        serialized_fans = []
        for f in fans:
            entry = {
                'name': str(f.get('name') or f.get('fan_entity_id') or f.get('device_id')).strip(),
                'device_id': str(f.get('device_id') or '').strip(),
                'local_key': str(f.get('local_key') or '').strip(),
            }
            if str(f.get('product_id') or '').strip():
                entry['product_id'] = str(f['product_id']).strip()
            if str(f.get('mac_address') or '').strip():
                entry['mac_address'] = str(f['mac_address']).strip()
            if str(f.get('uuid') or '').strip():
                entry['uuid'] = str(f['uuid']).strip()
            if str(f.get('fan_entity_id') or '').strip():
                entry['fan_entity_id'] = str(f['fan_entity_id']).strip()
            if str(f.get('light_entity_id') or '').strip():
                entry['light_entity_id'] = str(f['light_entity_id']).strip()
            entry['expose_to_ha'] = f.get('expose_to_ha') is not False
            serialized_fans.append(entry)

        tuya_block = {
            'tuya_ble_fan': {
                'max_connections': max_conns,
                'idle_disconnect_s': idle_disconnect_s,
                'fans': serialized_fans,
            }
        }
        lines.append(yaml.safe_dump(tuya_block, sort_keys=False, default_flow_style=False).rstrip())
        lines.append('')

    if gree_ac and gree_ac.get('enabled') and gree_ac.get('name'):
        tx_block = {
            'remote_transmitter': {
                'id': 'ir_transmitter',
                'pin': gree_ac['tx_pin'],
                'carrier_duty_percent': '50%',
            }
        }
        lines.append(yaml.safe_dump(tx_block, sort_keys=False, default_flow_style=False).rstrip())
        lines.append('')

        has_rx = bool(gree_ac.get('rx_pin'))
        debug_ir = has_rx and bool(gree_ac.get('dump_ir'))
        if has_rx:
            rx_cfg = {
                'id': 'ir_receiver',
                'pin': {
                    'number': gree_ac['rx_pin'],
                    'inverted': True,
                    'mode': {
                        'input': True,
                        'pullup': True,
                    },
                },
                'idle': '25ms',
                'filter': '50us',
                'tolerance': '50%',
                'buffer_size': '2kb',
            }
            if debug_ir:
                rx_cfg['dump'] = ['raw']
            rx_block = {'remote_receiver': rx_cfg}
            rx_yaml = yaml.safe_dump(rx_block, sort_keys=False, default_flow_style=False).rstrip()
            if debug_ir:
                rx_yaml += (
                    "\n"
                    "  on_raw:\n"
                    "    then:\n"
                    "      - lambda: |-\n"
                    "          esphome::remote_base::RemoteReceiveData rx_std(x, 50, esphome::remote_base::TOLERANCE_MODE_PERCENTAGE);\n"
                    "          auto s_std = esphome::gree::GreeProtocol(esphome::gree::GREE_GENERIC).decode(rx_std);\n"
                    "          esphome::remote_base::RemoteReceiveData rx_ext(x, 50, esphome::remote_base::TOLERANCE_MODE_PERCENTAGE);\n"
                    "          auto s_ext = esphome::gree::GreeProtocol(esphome::gree::GREE_YAC1FB9).decode(rx_ext);\n"
                    "          char buf[96];\n"
                    "          int32_t hdr_space = x.size() >= 2 ? -x[1] : 0;\n"
                    "          if (s_ext.has_value() && hdr_space >= 4250) {\n"
                    "            const auto &s = *s_ext;\n"
                    "            const char *proto = (s[5] == 0x80 || (s[3] == 0xA0 && s[7] == 0xA0)) ? \"yaw1f\" : \"yac1fb9\";\n"
                    "            snprintf(buf, sizeof(buf), \"%s [%02X %02X %02X %02X %02X %02X %02X %02X]\",\n"
                    "                     proto, (unsigned)s[0], (unsigned)s[1], (unsigned)s[2], (unsigned)s[3],\n"
                    "                     (unsigned)s[4], (unsigned)s[5], (unsigned)s[6], (unsigned)s[7]);\n"
                    "            id(gree_ir_debug_protocol).publish_state(buf);\n"
                    "          } else if (s_std.has_value()) {\n"
                    "            const auto &s = *s_std;\n"
                    "            const char *proto = \"generic\";\n"
                    "            if (esphome::gree::GreeClimateCodec::decode(esphome::gree::GREE_YB1FA, s).has_value()) {\n"
                    "              proto = \"yb1fa/yx1ff\";\n"
                    "            } else if (s[5] == 0x40 && (s[2] & 0x60) == 0x60) {\n"
                    "              proto = \"yag\";\n"
                    "            } else if (s[6] == 0x20) {\n"
                    "              proto = \"yaa/yac\";\n"
                    "            } else if ((s[3] & 0xF0) == 0x70) {\n"
                    "              proto = \"yac (aux)\";\n"
                    "            } else if ((s[3] & 0xF0) == 0x50) {\n"
                    "              proto = \"yan\";\n"
                    "            }\n"
                    "            snprintf(buf, sizeof(buf), \"%s [%02X %02X %02X %02X %02X %02X %02X %02X]\",\n"
                    "                     proto, (unsigned)s[0], (unsigned)s[1], (unsigned)s[2], (unsigned)s[3],\n"
                    "                     (unsigned)s[4], (unsigned)s[5], (unsigned)s[6], (unsigned)s[7]);\n"
                    "            id(gree_ir_debug_protocol).publish_state(buf);\n"
                    "          } else if (x.size() >= 2) {\n"
                    "            snprintf(buf, sizeof(buf), \"non-gree (%u pulses, hdr %ld/%ld)\",\n"
                    "                     (unsigned)x.size(), (long)x[0], (long)x[1]);\n"
                    "            id(gree_ir_debug_protocol).publish_state(buf);\n"
                    "          }"
                )
            lines.append(rx_yaml)
            lines.append('')

        climate_entry = {
            'platform': 'gree',
            'id': 'gree_ac',
            'device_id': 'gree_ac_device',
            'name': 'None',
            'model': gree_ac['model'],
            'transmitter_id': 'ir_transmitter',
            'supports_cool': bool(gree_ac.get('supports_cool', True)),
            'supports_heat': bool(gree_ac.get('supports_heat', True)),
            'visual': {
                'min_temperature': 16,
                'max_temperature': 30,
                'temperature_step': 1,
            },
        }
        if has_rx:
            climate_entry['receiver_id'] = 'ir_receiver'

        lines.append(yaml.safe_dump({'climate': [climate_entry]}, sort_keys=False, default_flow_style=False).rstrip())
        lines.append('')

        if debug_ir:
            debug_sensor_block = {
                'text_sensor': [
                    {
                        'platform': 'template',
                        'id': 'gree_ir_debug_protocol',
                        'device_id': 'gree_ac_device',
                        'name': 'IR Debug Protocol',
                        'entity_category': 'diagnostic',
                        'icon': 'mdi:remote',
                    }
                ]
            }
            lines.append(yaml.safe_dump(debug_sensor_block, sort_keys=False, default_flow_style=False).rstrip())
            lines.append('')

    shelly_list = shellys or []
    detached_list = detached_switches or []
    names_map = dict(_CACHED_SHELLY_KNOWN_NAMES)
    if isinstance(known_names, dict):
        names_map.update({k: v for k, v in known_names.items() if k and v})
    sb_cfg = {
        'network_key': network_key,
        'visible_shellys_sensor': {
            'name': 'Visible Shellys',
        },
    }
    if names_map:
        sb_cfg['known_names'] = dict(sorted(names_map.items()))
    if shelly_list:
        sb_cfg['shellys'] = [
            {
                'name': s['name'],
                'mac_address': s['mac_address'],
                'channel': int(s.get('channel') or 0),
                'kind': s.get('kind') or 'switch',
                'entity_id': s.get('entity_id') or '',
            }
            for s in shelly_list
        ]
    if detached_list:
        sb_cfg['detached_switches'] = [
            {
                'name': d['name'],
                'mac_address': d['mac_address'],
                'input_channel': int(d.get('input_channel') or 0),
                'target_fan_device_id': d.get('target_fan_device_id') or '',
                'target_light_entity_id': d.get('target_light_entity_id') or '',
            }
            for d in detached_list
        ]
    lines.append(yaml.safe_dump({'shelly_ble_bridge': sb_cfg}, sort_keys=False, default_flow_style=False).rstrip())
    lines.append('')

    return '\n'.join(lines)


def save_ble_hub_yaml(payload, esphome_dir=None):
    """Create or update a headless BLE hub YAML with strict single-host fan enforcement."""
    root_dir = esphome_dir or BASE_DIR
    if not root_dir or not os.path.isdir(root_dir):
        return None, {'error': 'ESPHome directory not found'}, 500

    raw_name = str(payload.get('name') or '').strip()
    slug = _slugify_hub_name(raw_name)
    if not slug:
        return None, {'error': 'Hub name is required (letters, numbers, underscores, or hyphens)'}, 400

    filename = str(payload.get('filename') or f'{slug}.yaml').strip()
    if not filename.endswith(('.yaml', '.yml')):
        filename += '.yaml'
    filename = os.path.basename(filename)
    if filename in ('secrets.yaml', 'lib.yaml'):
        return None, {'error': f'Invalid hub filename: {filename}'}, 400

    friendly_name = str(payload.get('friendly_name') or raw_name or slug).strip()
    board = str(payload.get('board') or 'esp32dev').strip() or 'esp32dev'
    try:
        fallback_channel = int(payload.get('fallback_channel') or 1)
    except (TypeError, ValueError):
        fallback_channel = 1
    fallback_channel = max(1, min(13, fallback_channel))

    fans = payload.get('fans') if isinstance(payload.get('fans'), list) else []
    valid_fans = [
        f for f in fans
        if isinstance(f, dict) and str(f.get('device_id') or '').strip() and str(f.get('local_key') or '').strip()
    ]
    gree_ac = _normalize_gree_ac_config(payload.get('gree_ac'))
    valid_shellys = _normalize_shellys_config(payload.get('shellys'))
    valid_detached = _normalize_detached_switches_config(payload.get('detached_switches'))

    conflicts = _find_fan_ownership_conflicts(filename, valid_fans, root_dir)
    if conflicts and not payload.get('reassign'):
        return None, {
            'error': 'One or more fans are already hosted on another device',
            'conflicts': conflicts,
        }, 409

    migrated_from = []
    if conflicts and payload.get('reassign'):
        by_host = {}
        for c in conflicts:
            by_host.setdefault(c['host_file'], []).append(c)
        for host_file, host_conflicts in by_host.items():
            host_path = os.path.join(root_dir, host_file)
            if _remove_fans_from_host_yaml(host_path, host_conflicts):
                migrated_from.append(host_file)

    network_key = str(payload.get('network_key') or '').strip() or get_or_create_espnow_network_key(root_dir)
    yaml_content = _render_headless_hub_yaml(
        name=slug,
        friendly_name=friendly_name,
        board=board,
        fallback_channel=fallback_channel,
        network_key=network_key,
        fans=valid_fans,
        gree_ac=gree_ac,
        shellys=valid_shellys,
        detached_switches=valid_detached,
    )

    target_path = os.path.join(root_dir, filename)
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)

    if valid_fans:
        save_ble_fans_to_vault(valid_fans, root_dir)

    return {
        'filename': filename,
        'name': slug,
        'friendly_name': friendly_name,
        'board': board,
        'fallback_channel': fallback_channel,
        'network_key': network_key,
        'fans': valid_fans,
        'gree_ac': gree_ac,
        'shellys': valid_shellys,
        'detached_switches': valid_detached,
        'migrated_from': migrated_from,
    }, None, 200


@ble_hubs_bp.route('/api/ble_hubs', methods=['GET'])
def api_list_ble_hubs():
    try:
        hubs = list_ble_hubs()
        network_key = get_or_create_espnow_network_key()
        hosted_by = find_ble_fan_hosts()
        return jsonify({'hubs': hubs, 'network_key': network_key, 'hosted_by': hosted_by})
    except Exception as e:
        return jsonify({'hubs': [], 'error': str(e)}), 500


@ble_hubs_bp.route('/api/ble_hubs', methods=['POST'])
def api_save_ble_hub():
    try:
        payload = request.get_json(silent=True) or {}
        result, err, status = save_ble_hub_yaml(payload)
        if err:
            return jsonify(err), status
        return jsonify({
            'success': True,
            'hub': result,
            'hubs': list_ble_hubs(),
            'hosted_by': find_ble_fan_hosts(),
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ble_hubs_bp.route('/api/ble_hubs/<path:filename>', methods=['DELETE'])
def api_delete_ble_hub(filename):
    try:
        safe_name = os.path.basename(filename)
        target_path = os.path.join(BASE_DIR, safe_name)
        if not os.path.isfile(target_path):
            return jsonify({'error': 'Hub file not found'}), 404
        with open(target_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        parsed = yaml.load(raw_text, Loader=generate_tiles_api.create_safe_yaml_loader())
        if not is_headless_hub_yaml(parsed, raw_text):
            return jsonify({'error': f'{safe_name} is not a headless BLE hub file'}), 400
        os.remove(target_path)
        return jsonify({
            'success': True,
            'deleted': safe_name,
            'hubs': list_ble_hubs(),
            'hosted_by': find_ble_fan_hosts(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def generate_tuya_ble_credentials():
    """Generate a random Tuya-compatible 22-char device_id and 16-char local_key."""
    import secrets as py_secrets
    import string

    id_alphabet = string.ascii_lowercase + string.digits
    key_alphabet = string.ascii_letters + string.digits
    device_id = 'bf' + ''.join(py_secrets.choice(id_alphabet) for _ in range(20))
    local_key = ''.join(py_secrets.choice(key_alphabet) for _ in range(16))
    return device_id, local_key


def _load_esphome_secrets(esphome_dir=None):
    root_dir = esphome_dir or BASE_DIR
    secrets_path = os.path.join(root_dir, 'secrets.yaml')
    if not os.path.isfile(secrets_path):
        return {}
    try:
        with open(secrets_path, 'r', encoding='utf-8', errors='replace') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_device_api_info(filepath, secrets_map=None):
    """Extract api.encryption.key, api.password, and api.port from an ESPHome device YAML, resolving !secret and packages."""
    secrets_map = secrets_map or {}
    base_loader = generate_tiles_api.create_safe_yaml_loader(
        include_base_dir=os.path.dirname(filepath)
    )

    class SecretResolvingLoader(base_loader):
        pass

    def _secret_ctor(loader, node):
        key_name = loader.construct_scalar(node)
        return secrets_map.get(key_name)

    SecretResolvingLoader.add_constructor('!secret', _secret_ctor)

    try:
        # Skip only the indented tile_ui: block so top-level api: after tile_ui: is still parsed
        lines = []
        skipping_tile_ui = False
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('tile_ui:') or line.startswith('tile_ui '):
                    skipping_tile_ui = True
                    continue
                if skipping_tile_ui:
                    if line.strip() and not line[0].isspace() and not line.lstrip().startswith('#'):
                        skipping_tile_ui = False
                    else:
                        continue
                lines.append(line)
        data = yaml.load(''.join(lines), Loader=SecretResolvingLoader)
    except Exception:
        return {'api_key': None, 'api_password': '', 'api_port': 6053}

    if not isinstance(data, dict):
        return {'api_key': None, 'api_password': '', 'api_port': 6053}

    api_key = None
    api_password = ''
    api_port = 6053

    # Check substitutions.api_port first
    subs = data.get('substitutions')
    if isinstance(subs, dict) and subs.get('api_port'):
        try:
            api_port = int(subs['api_port'])
        except (TypeError, ValueError):
            pass

    def _apply_api_cfg(cfg):
        nonlocal api_key, api_password, api_port
        if not isinstance(cfg, dict):
            return
        enc = cfg.get('encryption')
        if isinstance(enc, dict) and enc.get('key'):
            api_key = str(enc['key']).strip()
        if cfg.get('password'):
            api_password = str(cfg['password'])
        if cfg.get('port'):
            try:
                api_port = int(cfg['port'])
            except (TypeError, ValueError):
                pass

    # Check included packages first, then top-level api: (top-level wins)
    packages = data.get('packages')
    if isinstance(packages, dict):
        for pkg_val in packages.values():
            if isinstance(pkg_val, dict) and isinstance(pkg_val.get('api'), dict):
                _apply_api_cfg(pkg_val['api'])
    _apply_api_cfg(data.get('api'))

    return {'api_key': api_key, 'api_password': api_password, 'api_port': api_port}


def _list_cyd_devices_with_api(esphome_dir=None):
    """Return metadata + API credentials for all CYD YAML files in esphome_dir."""
    root_dir = esphome_dir or BASE_DIR
    if not root_dir or not os.path.isdir(root_dir):
        return []
    secrets_map = _load_esphome_secrets(root_dir)
    skip_files = {'secrets.yaml', 'images.yaml'}
    devices = []
    for fname in sorted(os.listdir(root_dir)):
        if not (fname.endswith('.yaml') or fname.endswith('.yml')) or fname in skip_files:
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        meta = _parse_device_yaml(fpath)
        if not meta or not (meta.get('is_cyd') or meta.get('is_headless_hub')):
            continue
        api_info = _extract_device_api_info(fpath, secrets_map)
        meta['filename'] = fname
        meta['path'] = fname
        meta['filepath'] = fpath
        meta['api_key'] = api_info['api_key']
        meta['api_password'] = api_info['api_password']
        meta['api_port'] = api_info['api_port']
        devices.append(meta)
    return devices


def _find_ble_fan_hosts_extended(esphome_dir=None):
    """Return maps of device_id -> [files], mac -> [files], and uuid -> [files] across CYD YAMLs."""
    root_dir = esphome_dir or BASE_DIR
    by_id, by_mac, by_uuid = {}, {}, {}
    if not root_dir or not os.path.isdir(root_dir):
        return by_id, by_mac, by_uuid

    loader_cls = generate_tiles_api.create_safe_yaml_loader()
    for fname in sorted(os.listdir(root_dir)):
        if not (fname.endswith('.yaml') or fname.endswith('.yml')) or fname in ('secrets.yaml', 'images.yaml'):
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            if not re.search(r'^tuya_ble_fan:', raw_text, flags=re.MULTILINE):
                continue
            parsed = yaml.load(raw_text, Loader=loader_cls)
            if not isinstance(parsed, dict):
                continue
            fans = (parsed.get('tuya_ble_fan') or {}).get('fans')
            if not isinstance(fans, list):
                continue
            for fan in fans:
                if not isinstance(fan, dict):
                    continue
                dev_id = str(fan.get('device_id') or '').strip()
                mac = str(fan.get('mac_address') or '').strip().upper()
                uuid_val = str(fan.get('uuid') or '').strip()
                if dev_id:
                    by_id.setdefault(dev_id, [])
                    if fname not in by_id[dev_id]:
                        by_id[dev_id].append(fname)
                if mac:
                    by_mac.setdefault(mac, [])
                    if fname not in by_mac[mac]:
                        by_mac[mac].append(fname)
                if uuid_val:
                    by_uuid.setdefault(uuid_val, [])
                    if fname not in by_uuid[uuid_val]:
                        by_uuid[uuid_val].append(fname)
        except Exception:
            continue
    return by_id, by_mac, by_uuid


def aggregate_ble_scan_sightings(sightings, tuya_local_fans=None,
                                 hosted_by_id=None, hosted_by_mac=None, hosted_by_uuid=None):
    """Deduplicate raw BLE sightings across CYDs by MAC, rank by strongest RSSI, and enrich with HA/CYD info."""
    tuya_local_fans = tuya_local_fans or []
    hosted_by_id = hosted_by_id or {}
    hosted_by_mac = hosted_by_mac or {}
    hosted_by_uuid = hosted_by_uuid or {}

    by_mac = {}
    for s in sightings:
        mac = str(s.get('mac') or '').strip().upper()
        if not mac:
            continue
        cyd_file = str(s.get('cyd_filename') or s.get('cyd_device') or '').strip()
        try:
            rssi = int(s.get('rssi', -127))
        except (TypeError, ValueError):
            rssi = -127
        try:
            addr_type = int(s.get('addr_type', 0))
        except (TypeError, ValueError):
            addr_type = 0
        bound_raw = s.get('bound', False)
        bound = bound_raw if isinstance(bound_raw, bool) else str(bound_raw).strip().lower() in ('true', '1', 'yes')
        uuid_val = str(s.get('uuid') or '').strip()
        product_id = str(s.get('product_id') or '').strip()

        entry = by_mac.get(mac)
        if entry is None:
            entry = {
                'mac': mac,
                'addr_type': addr_type,
                'bound': bound,
                'uuid': uuid_val,
                'product_id': product_id,
                '_cyd_map': {},
            }
            by_mac[mac] = entry
        else:
            if not entry['uuid'] and uuid_val:
                entry['uuid'] = uuid_val
            if not entry['product_id'] and product_id:
                entry['product_id'] = product_id
            # If any sighting says bound=True, mark bound
            if bound:
                entry['bound'] = True

        existing_cyd = entry['_cyd_map'].get(cyd_file)
        if existing_cyd is None or rssi > existing_cyd['rssi']:
            entry['_cyd_map'][cyd_file] = {
                'cyd_filename': cyd_file,
                'cyd_name': s.get('cyd_name') or cyd_file,
                'friendly_name': s.get('friendly_name') or s.get('cyd_name') or cyd_file,
                'rssi': rssi,
            }

    # Build lookup indexes for tuya_local fans
    ha_by_mac = {str(f.get('mac_address') or '').strip().upper(): f for f in tuya_local_fans if f.get('mac_address')}
    ha_by_uuid = {str(f.get('uuid') or '').strip(): f for f in tuya_local_fans if f.get('uuid')}

    results = []
    for mac, entry in by_mac.items():
        ranked = sorted(entry['_cyd_map'].values(), key=lambda x: x['rssi'], reverse=True)
        best = ranked[0] if ranked else None
        matched_ha = ha_by_mac.get(mac) or (ha_by_uuid.get(entry['uuid']) if entry['uuid'] else None)

        hosted = []
        for h in hosted_by_mac.get(mac, []):
            if h not in hosted:
                hosted.append(h)
        if entry['uuid']:
            for h in hosted_by_uuid.get(entry['uuid'], []):
                if h not in hosted:
                    hosted.append(h)
        if matched_ha and matched_ha.get('device_id'):
            for h in hosted_by_id.get(matched_ha['device_id'], []):
                if h not in hosted:
                    hosted.append(h)

        results.append({
            'mac': mac,
            'addr_type': entry['addr_type'],
            'bound': entry['bound'],
            'uuid': entry['uuid'],
            'product_id': entry['product_id'] or (matched_ha.get('product_id', '') if matched_ha else ''),
            'best_cyd': best,
            'best_rssi': best['rssi'] if best else -127,
            'sightings': ranked,
            'hosted_by': hosted,
            'matched_ha_fan': {
                'name': matched_ha.get('name', ''),
                'device_id': matched_ha.get('device_id', ''),
                'local_key': matched_ha.get('local_key', ''),
                'product_id': matched_ha.get('product_id', ''),
                'fan_entity_id': matched_ha.get('fan_entity_id', ''),
                'light_entity_id': matched_ha.get('light_entity_id', ''),
            } if matched_ha else None,
        })

    results.sort(key=lambda r: r['best_rssi'], reverse=True)
    return results


class _YamlSecret(str):
    """Marker scalar that round-trips as `!secret <name>` during YAML dump."""


class _SecretPreservingDumper(yaml.SafeDumper):
    pass


def _represent_yaml_secret(dumper, data):
    return dumper.represent_scalar('!secret', str(data))


_SecretPreservingDumper.add_representer(_YamlSecret, _represent_yaml_secret)


def _replace_top_level_yaml_block(raw_text, block_key, rendered_block):
    """Replace a top-level YAML block cleanly by line boundaries (preserving column-0 comments and backslashes)."""
    lines = raw_text.splitlines(keepends=True)
    start_idx = None
    for i, line in enumerate(lines):
        if re.match(rf'^{re.escape(block_key)}:\s*(?:#.*)?$', line):
            start_idx = i
            break

    if start_idx is None:
        prefix = raw_text
        if prefix and not prefix.endswith('\n'):
            prefix += '\n'
        return prefix + ('\n' if prefix and not prefix.endswith('\n\n') else '') + rendered_block

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if not line[0].isspace():
            end_idx = j
            break

    replacement = rendered_block + ('\n' if end_idx < len(lines) else '')
    return ''.join(lines[:start_idx]) + replacement + ''.join(lines[end_idx:])


def compute_ble_resource_plan(fan_count, has_ble_proxy=False):
    """Compute simultaneous BLE connection slots and display buffer sizing for a CYD."""
    count = max(0, int(fan_count or 0))
    max_fan_slots = 2 if has_ble_proxy else 3
    fan_slots = min(count, max_fan_slots) if count > 0 else 1
    proxy_slots = 1 if has_ble_proxy else 0
    total_connections = min(3, fan_slots + proxy_slots)
    persistent = count > 0 and count <= fan_slots
    idle_disconnect_s = 0 if persistent else 30
    display_buffer_size = '15%' if total_connections >= 3 else '20%'
    return {
        'fan_count': count,
        'fan_slots': fan_slots,
        'proxy_slots': proxy_slots,
        'total_connections': total_connections,
        'persistent': persistent,
        'idle_disconnect_s': idle_disconnect_s,
        'display_buffer_size': display_buffer_size,
    }


def _upsert_substitution(raw_text, key, value):
    """Set or update a key inside the top-level substitutions: block, preserving formatting."""
    quoted = f'"{value}"'
    lines = raw_text.splitlines(keepends=True)
    subs_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^substitutions:\s*(?:#.*)?$', line):
            subs_idx = i
            break

    if subs_idx is None:
        return f'substitutions:\n  {key}: {quoted}\n\n' + raw_text

    end_idx = len(lines)
    key_idx = None
    key_re = re.compile(rf'^(\s+){re.escape(key)}\s*:')
    for j in range(subs_idx + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if not line[0].isspace():
            end_idx = j
            break
        if key_re.match(line):
            key_idx = j
            break

    if key_idx is not None:
        indent = key_re.match(lines[key_idx]).group(1)
        lines[key_idx] = f'{indent}{key}: {quoted}\n'
    else:
        insert_line = f'  {key}: {quoted}\n'
        if not lines[subs_idx].endswith('\n'):
            lines[subs_idx] += '\n'
        lines.insert(subs_idx + 1, insert_line)
    return ''.join(lines)


def add_ble_fan_to_device_yaml(filepath, fan_entry):
    """Upsert a Tuya BLE fan entry into a target CYD YAML file, preserving comments, !secret tags, and existing fields."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    base_loader = generate_tiles_api.create_safe_yaml_loader()

    class SecretPreservingLoader(base_loader):
        pass

    SecretPreservingLoader.add_constructor(
        '!secret', lambda loader, node: _YamlSecret(loader.construct_scalar(node))
    )

    parsed = yaml.load(raw_text, Loader=SecretPreservingLoader) or {}
    if not isinstance(parsed, dict):
        parsed = {}

    existing_ble_cfg = parsed.get('tuya_ble_fan')
    existing_ble_cfg = dict(existing_ble_cfg) if isinstance(existing_ble_cfg, dict) else {}

    existing_fans = []
    if isinstance(existing_ble_cfg.get('fans'), list):
        for item in existing_ble_cfg['fans']:
            if isinstance(item, dict):
                existing_fans.append(dict(item))

    new_fan = {
        'name': str(fan_entry.get('name') or fan_entry.get('device_id') or 'BLE Fan').strip(),
        'device_id': str(fan_entry.get('device_id') or '').strip(),
        'local_key': str(fan_entry.get('local_key') or '').strip(),
    }
    if not new_fan['device_id'] or not new_fan['local_key']:
        raise ValueError('device_id and local_key are required')

    for opt_key in ('product_id', 'mac_address', 'uuid', 'fan_entity_id', 'light_entity_id'):
        val = str(fan_entry.get(opt_key) or '').strip()
        if val:
            new_fan[opt_key] = val
    new_fan['expose_to_ha'] = fan_entry.get('expose_to_ha', True) is not False

    # Upsert by device_id or mac_address, merging into existing entry to preserve extra fields
    prev_count = len(existing_fans)
    replaced = False
    new_mac = new_fan.get('mac_address', '').upper()
    for idx, ef in enumerate(existing_fans):
        ef_id = str(ef.get('device_id') or '').strip()
        ef_mac = str(ef.get('mac_address') or '').strip().upper()
        if ef_id == new_fan['device_id'] or (new_mac and ef_mac == new_mac):
            merged = dict(ef)
            merged.update(new_fan)
            existing_fans[idx] = merged
            replaced = True
            break
    if not replaced:
        existing_fans.append(new_fan)

    updated_text = raw_text

    # 1. Ensure tuya_ble_fan package include is present under packages: (using parsed dict)
    packages = parsed.get('packages') if isinstance(parsed.get('packages'), dict) else {}
    has_tuya_pkg = any(
        isinstance(v, str) and 'lib/tuya_ble_fan.yaml' in v
        for v in packages.values()
    ) or ('tuya_ble_fan' in packages)
    if not has_tuya_pkg:
        pkg_match = re.search(r'^packages:\s*(?:#.*)?$', updated_text, flags=re.MULTILINE)
        if pkg_match:
            insert_pos = pkg_match.end()
            prefix = updated_text[:insert_pos]
            suffix = updated_text[insert_pos:]
            if not suffix.startswith('\n'):
                suffix = '\n' + suffix
            updated_text = prefix + '\n  tuya_ble_fan: !include lib/tuya_ble_fan.yaml' + suffix
        else:
            updated_text = 'packages:\n  tuya_ble_fan: !include lib/tuya_ble_fan.yaml\n\n' + updated_text

    # 2. Dynamically size ble_max_connections and display_buffer_size based on fan count & ble_proxy
    has_ble_proxy = any(
        k == 'ble_proxy' or (isinstance(v, str) and 'ble_proxy' in v)
        for k, v in packages.items()
    )
    plan = compute_ble_resource_plan(len(existing_fans), has_ble_proxy)
    updated_text = _upsert_substitution(updated_text, 'ble_max_connections', str(plan['total_connections']))
    updated_text = _upsert_substitution(updated_text, 'display_buffer_size', plan['display_buffer_size'])

    # 3. Render new top-level tuya_ble_fan: block (preserving extra keys)
    new_ble_cfg = {
        k: v for k, v in existing_ble_cfg.items()
        if k not in ('fans', 'idle_disconnect_s', 'max_connections')
    }
    new_ble_cfg['max_connections'] = plan['fan_slots']
    if 'idle_disconnect_s' in existing_ble_cfg and prev_count == len(existing_fans):
        new_ble_cfg['idle_disconnect_s'] = existing_ble_cfg['idle_disconnect_s']
    else:
        new_ble_cfg['idle_disconnect_s'] = plan['idle_disconnect_s']
    new_ble_cfg['fans'] = existing_fans

    rendered_block = yaml.dump(
        {'tuya_ble_fan': new_ble_cfg},
        Dumper=_SecretPreservingDumper,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip() + '\n'

    updated_text = _replace_top_level_yaml_block(updated_text, 'tuya_ble_fan', rendered_block)

    tmp_path = f"{filepath}.tmp.{os.getpid()}"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(updated_text)
    os.replace(tmp_path, filepath)

    # Return plain JSON-serializable fan dicts and back up to persistent vault
    plain_fans = [
        {k: (str(v) if isinstance(v, _YamlSecret) else v) for k, v in fan.items()}
        for fan in existing_fans
    ]
    save_ble_fans_to_vault(plain_fans, os.path.dirname(filepath))
    return plain_fans


async def _exec_esphome_service(client, service, data):
    import inspect
    res = client.execute_service(service, data)
    if inspect.isawaitable(res):
        await res


async def _disconnect_esphome_client(client):
    import inspect
    try:
        res = client.disconnect()
        if inspect.isawaitable(res):
            await asyncio.wait_for(res, timeout=3.0)
    except Exception:
        pass


async def _scan_single_cyd(cyd_info, duration_s=10):
    """Connect to one CYD over ESPHome Native API, invoke scan_tuya_ble_fans, and collect sightings."""
    cyd_file = cyd_info['filename']
    cyd_name = cyd_info['device_name']
    friendly = cyd_info['friendly_name']
    address = cyd_info['address']
    client = APIClient(
        address=address,
        port=int(cyd_info.get('api_port') or 6053),
        password=cyd_info.get('api_password') or '',
        noise_psk=cyd_info.get('api_key') or None,
    )
    sightings = []
    done_event = asyncio.Event()
    disconnect_error = []

    def on_stop(expected_disconnect=False):
        if not expected_disconnect and not done_event.is_set():
            disconnect_error.append('CYD disconnected during scan')
            done_event.set()

    def on_service_call(call):
        svc_name = getattr(call, 'service', '') or ''
        data = dict(getattr(call, 'data', {}) or {})
        if svc_name == 'esphome.tuya_ble_fan_found':
            sightings.append({
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'mac': data.get('mac', ''),
                'addr_type': data.get('addr_type', 0),
                'rssi': data.get('rssi', -127),
                'bound': data.get('bound', 'false'),
                'uuid': data.get('uuid', ''),
                'product_id': data.get('product_id', ''),
            })
        elif svc_name == 'esphome.tuya_ble_scan_done':
            done_event.set()

    try:
        try:
            await asyncio.wait_for(client.connect(login=True, on_stop=on_stop), timeout=8.0)
        except TypeError:
            await asyncio.wait_for(client.connect(login=True), timeout=8.0)
        _, services = await asyncio.wait_for(client.list_entities_services(), timeout=8.0)
        scan_svc = next((s for s in services if getattr(s, 'name', '') == 'scan_tuya_ble_fans'), None)
        if scan_svc is None:
            return {
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'status': 'unsupported',
                'error': 'Firmware does not expose scan_tuya_ble_fans (flash updated firmware)',
                'sightings': [],
            }

        client.subscribe_service_calls(on_service_call)
        await _exec_esphome_service(client, scan_svc, {'duration_s': int(duration_s)})
        try:
            await asyncio.wait_for(done_event.wait(), timeout=float(duration_s) + 5.0)
        except asyncio.TimeoutError:
            return {
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'status': 'error',
                'error': 'Timed out waiting for scan completion event from CYD',
                'sightings': sightings,
            }
        if disconnect_error:
            return {
                'cyd_filename': cyd_file,
                'cyd_name': cyd_name,
                'friendly_name': friendly,
                'status': 'error',
                'error': disconnect_error[0],
                'sightings': sightings,
            }
        return {
            'cyd_filename': cyd_file,
            'cyd_name': cyd_name,
            'friendly_name': friendly,
            'status': 'ok',
            'error': '',
            'sightings': sightings,
        }
    except Exception as e:
        return {
            'cyd_filename': cyd_file,
            'cyd_name': cyd_name,
            'friendly_name': friendly,
            'status': 'error',
            'error': str(e),
            'sightings': sightings,
        }
    finally:
        await _disconnect_esphome_client(client)


async def _pair_unbound_on_cyd(cyd_info, mac, addr_type, uuid_val, device_id, local_key, blink_confirm=True):
    """Connect to target CYD and invoke pair_unbound_tuya_fan, awaiting esphome.tuya_ble_fan_paired."""
    client = APIClient(
        address=cyd_info['address'],
        port=int(cyd_info.get('api_port') or 6053),
        password=cyd_info.get('api_password') or '',
        noise_psk=cyd_info.get('api_key') or None,
    )
    target_mac = mac.strip().upper()
    result_box = {}
    done_event = asyncio.Event()

    def on_stop(expected_disconnect=False):
        if not expected_disconnect and not done_event.is_set():
            result_box['ok'] = False
            result_box['error'] = 'CYD disconnected during pairing'
            done_event.set()

    def on_service_call(call):
        svc_name = getattr(call, 'service', '') or ''
        data = dict(getattr(call, 'data', {}) or {})
        if svc_name == 'esphome.tuya_ble_fan_paired':
            ev_mac = str(data.get('mac') or '').strip().upper()
            if ev_mac and ev_mac != target_mac:
                return
            result_box['ok'] = str(data.get('ok', 'false')).lower() == 'true'
            result_box['mac'] = ev_mac or target_mac
            result_box['uuid'] = data.get('uuid', uuid_val)
            result_box['error'] = data.get('error', '')
            done_event.set()

    try:
        try:
            await asyncio.wait_for(client.connect(login=True, on_stop=on_stop), timeout=8.0)
        except TypeError:
            await asyncio.wait_for(client.connect(login=True), timeout=8.0)
        _, services = await asyncio.wait_for(client.list_entities_services(), timeout=8.0)
        pair_svc = next((s for s in services if getattr(s, 'name', '') == 'pair_unbound_tuya_fan'), None)
        if pair_svc is None:
            return {'ok': False, 'error': 'Target CYD firmware does not expose pair_unbound_tuya_fan'}

        client.subscribe_service_calls(on_service_call)
        await _exec_esphome_service(client, pair_svc, {
            'mac': target_mac,
            'addr_type': int(addr_type),
            'uuid': uuid_val,
            'device_id': device_id,
            'local_key': local_key,
            'blink_confirm': bool(blink_confirm),
        })
        await asyncio.wait_for(done_event.wait(), timeout=25.0)
        return result_box
    except asyncio.TimeoutError:
        return {'ok': False, 'error': 'Timed out waiting for BLE pairing response from CYD'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    finally:
        await _disconnect_esphome_client(client)


@ble_hubs_bp.route('/api/tuya_ble/scan', methods=['POST'])
def scan_tuya_ble_whole_house():
    """Trigger an on-demand BLE scan across all online CYDs in parallel and return ranked sightings."""
    try:
        body = request.get_json(silent=True) or {}
        try:
            duration_s = max(3, min(30, int(body.get('duration_s', 10))))
        except (TypeError, ValueError):
            return jsonify({'fans': [], 'cyds': [], 'error': 'Invalid duration_s'}), 400
        requested_devices = body.get('devices')

        all_cyds = _list_cyd_devices_with_api()
        if requested_devices and isinstance(requested_devices, list):
            req_set = set(requested_devices)
            all_cyds = [d for d in all_cyds if d['filename'] in req_set or d['device_name'] in req_set]

        if all_cyds:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(all_cyds))) as ex:
                all_cyds = list(ex.map(_check_device_online, all_cyds))

        online_cyds = [d for d in all_cyds if d.get('online')]
        offline_cyds = [
            {
                'cyd_filename': d['filename'],
                'cyd_name': d['device_name'],
                'friendly_name': d['friendly_name'],
                'status': 'offline',
                'error': 'Device is offline',
                'sightings_count': 0,
            }
            for d in all_cyds if not d.get('online')
        ]

        async def _run_all():
            if not online_cyds:
                return []
            return await asyncio.gather(*[_scan_single_cyd(c, duration_s) for c in online_cyds])

        scan_outputs = asyncio.run(_run_all())

        all_sightings = []
        cyd_statuses = []
        for out in scan_outputs:
            all_sightings.extend(out.get('sightings', []))
            cyd_statuses.append({
                'cyd_filename': out['cyd_filename'],
                'cyd_name': out['cyd_name'],
                'friendly_name': out['friendly_name'],
                'status': out['status'],
                'error': out.get('error', ''),
                'sightings_count': len(out.get('sightings', [])),
            })
        cyd_statuses.extend(offline_cyds)

        tuya_local_fans = get_all_known_tuya_ble_fans()
        hosted_by_id, hosted_by_mac, hosted_by_uuid = _find_ble_fan_hosts_extended()
        aggregated = aggregate_ble_scan_sightings(
            all_sightings,
            tuya_local_fans=tuya_local_fans,
            hosted_by_id=hosted_by_id,
            hosted_by_mac=hosted_by_mac,
            hosted_by_uuid=hosted_by_uuid,
        )

        return jsonify({
            'fans': aggregated,
            'cyds': cyd_statuses,
            'duration_s': duration_s,
            'tuya_local_fans': tuya_local_fans,
        })
    except Exception as e:
        return jsonify({'fans': [], 'cyds': [], 'error': str(e)}), 500


@ble_hubs_bp.route('/api/tuya_ble/pair', methods=['POST'])
def pair_unbound_tuya_ble_fan():
    """Pair an unbound (bound=0) Tuya BLE fan via the selected target CYD."""
    try:
        body = request.get_json(silent=True) or {}
        target_cyd = str(body.get('target_cyd') or '').strip()
        mac = str(body.get('mac') or '').strip().upper()
        try:
            addr_type = int(body.get('addr_type', 0))
            if addr_type < 0 or addr_type > 3:
                raise ValueError('addr_type out of range')
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid addr_type (expected 0..3)'}), 400
        uuid_val = str(body.get('uuid') or '').strip()
        blink_confirm = body.get('blink_confirm', True) is not False

        if not target_cyd or not mac or not uuid_val:
            return jsonify({'ok': False, 'error': 'target_cyd, mac, and uuid are required'}), 400

        cyds = _list_cyd_devices_with_api()
        cyd_info = next((c for c in cyds if c['filename'] == target_cyd or c['device_name'] == target_cyd), None)
        if cyd_info is None:
            return jsonify({'ok': False, 'error': f'Target CYD {target_cyd} not found'}), 404

        gen_id, gen_key = generate_tuya_ble_credentials()
        device_id = str(body.get('device_id') or gen_id).strip()
        local_key = str(body.get('local_key') or gen_key).strip()

        res = asyncio.run(_pair_unbound_on_cyd(
            cyd_info, mac, addr_type, uuid_val, device_id, local_key, blink_confirm=blink_confirm
        ))
        return jsonify({
            'ok': bool(res.get('ok')),
            'mac': res.get('mac', mac),
            'uuid': res.get('uuid', uuid_val),
            'device_id': device_id if res.get('ok') else '',
            'local_key': local_key if res.get('ok') else '',
            'error': res.get('error', ''),
        }), (200 if res.get('ok') else 502)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@ble_hubs_bp.route('/api/tuya_ble/add_to_device', methods=['POST'])
def add_tuya_ble_fan_to_device():
    """Save a discovered/paired BLE fan directly into the target CYD's YAML config."""
    try:
        body = request.get_json(silent=True) or {}
        target_cyd = str(body.get('target_cyd') or '').strip()
        fan = body.get('fan')
        if not target_cyd or not isinstance(fan, dict):
            return jsonify({'ok': False, 'error': 'target_cyd and fan object are required'}), 400

        safe_name = os.path.basename(target_cyd)
        if not (safe_name.endswith('.yaml') or safe_name.endswith('.yml')) or safe_name != target_cyd:
            return jsonify({'ok': False, 'error': 'Invalid target_cyd filename'}), 400
        if safe_name in ('secrets.yaml', 'images.yaml'):
            return jsonify({'ok': False, 'error': f'{safe_name} is not a CYD device config'}), 400

        filepath = _resolve_safe_path(safe_name)
        if not filepath or not os.path.isfile(filepath):
            return jsonify({'ok': False, 'error': f'Device file {safe_name} not found'}), 404

        meta = _parse_device_yaml(filepath)
        if not meta or not (meta.get('is_cyd') or meta.get('is_headless_hub')):
            return jsonify({'ok': False, 'error': f'{safe_name} is not a CYD or BLE Hub device config'}), 400

        fans = add_ble_fan_to_device_yaml(filepath, fan)
        hosted_by = find_ble_fan_hosts()
        return jsonify({
            'ok': True,
            'target_cyd': safe_name,
            'fans': fans,
            'hosted_by': hosted_by,
        })
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

