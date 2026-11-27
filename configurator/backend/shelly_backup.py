import os
import re
import json
import yaml
import requests
from flask import Blueprint, request, jsonify
from backend.state import (
    APP_DIR,
    BASE_DIR,
    HA_URL,
    IS_ADDON,
    SUPERVISOR_TOKEN,
    _CACHED_SHELLY_KNOWN_NAMES,
)
from backend.ble_hubs import (
    get_or_create_espnow_network_key,
    list_ble_hubs,
    save_ble_hub_yaml,
    _normalize_shelly_mac,
)

shelly_bp = Blueprint('shelly_backup', __name__)

def _load_shelly_script_template():
    candidates = [
        os.path.join(APP_DIR, 'shelly', 'cyd_ble_backup.js'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shelly', 'cyd_ble_backup.js'),
    ]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
    return None


def _shelly_rpc_call(ip, method, params=None, password=None, timeout=6):
    url = f"http://{ip}/rpc"
    body = {'id': 1, 'method': method}
    if params is not None:
        body['params'] = params
    auth = requests.auth.HTTPDigestAuth('admin', password) if password else None
    resp = requests.post(url, json=body, auth=auth, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get('error'):
        raise RuntimeError(str(data['error']))
    return data.get('result') if isinstance(data, dict) else data


def deploy_shelly_script_to_device(ip, script_code, password=None, script_name='cyd_ble_backup'):
    """Deploy and enable cyd_ble_backup.js on a Shelly Gen2/3/4 device over local HTTP RPC."""
    info = _shelly_rpc_call(ip, 'Shelly.GetDeviceInfo', password=password) or {}
    fw_id = str(info.get('fw_id') or '')
    app_name = str(info.get('app') or '')
    model = str(info.get('model') or '')
    mac = _normalize_shelly_mac(info.get('mac') or '')
    zigbee_warning = ('ZB' in fw_id.upper()) or ('ZB' in app_name.upper()) or ('ZIGBEE' in fw_id.upper())

    scripts_res = _shelly_rpc_call(ip, 'Script.List', password=password) or {}
    scripts = scripts_res.get('scripts') if isinstance(scripts_res, dict) else []
    script_id = None
    was_running = False
    for sc in (scripts or []):
        if isinstance(sc, dict) and sc.get('name') == script_name:
            script_id = sc.get('id')
            was_running = bool(sc.get('running'))
            break

    if script_id is None:
        created = _shelly_rpc_call(ip, 'Script.Create', {'name': script_name}, password=password) or {}
        script_id = created.get('id')
        if script_id is None:
            raise RuntimeError('Script.Create did not return a script id')
    elif was_running:
        _shelly_rpc_call(ip, 'Script.Stop', {'id': script_id}, password=password)

    # Chunk Script.PutCode to stay well under Shelly's HTTP RPC payload limit
    chunk_size = 1024
    for offset in range(0, len(script_code), chunk_size):
        chunk = script_code[offset:offset + chunk_size]
        _shelly_rpc_call(
            ip,
            'Script.PutCode',
            {'id': script_id, 'code': chunk, 'append': offset > 0},
            password=password,
        )

    _shelly_rpc_call(
        ip,
        'Script.SetConfig',
        {'id': script_id, 'config': {'name': script_name, 'enable': True}},
        password=password,
    )
    _shelly_rpc_call(ip, 'Script.Start', {'id': script_id}, password=password)

    return {
        'ip': ip,
        'ok': True,
        'mac_address': mac,
        'model': model,
        'fw_id': fw_id,
        'script_id': script_id,
        'zigbee_warning': zigbee_warning,
    }


_SHELLY_HA_DISCOVERY_TEMPLATE = (
    "{% set ns = namespace(devs=[], seen=[]) %}"
    "{% for eid in integration_entities('shelly') %}"
    "{% set did = device_id(eid) %}"
    "{% if did and did not in ns.seen %}"
    "{% set ns.seen = ns.seen + [did] %}"
    "{% set conns = device_attr(did, 'connections') or [] %}"
    "{% set m = namespace(v='', sid='') %}"
    "{% for c in conns %}{% if c[0] == 'mac' %}{% set m.v = c[1] %}{% endif %}{% endfor %}"
    "{% for ident in (device_attr(did, 'identifiers') or []) %}{% if ident[0] == 'shelly' %}{% set m.sid = ident[1] %}{% endif %}{% endfor %}"
    "{% set ents = namespace(items=[], inputs=[]) %}"
    "{% for deid in device_entities(did) %}"
    "{% set dom = deid.split('.')[0] %}"
    "{% if dom in ['switch', 'light', 'cover'] %}"
    "{% set ents.items = ents.items + [{'entity_id': deid, 'name': state_attr(deid, 'friendly_name') or deid, 'domain': dom}] %}"
    "{% elif dom in ['event', 'binary_sensor'] %}"
    "{% set ents.inputs = ents.inputs + [deid] %}"
    "{% endif %}"
    "{% endfor %}"
    "{% set ns.devs = ns.devs + [{"
    "'ha_device_id': did,"
    "'via_device_id': device_attr(did, 'via_device_id') or '',"
    "'shelly_id': m.sid,"
    "'name': device_attr(did, 'name_by_user') or device_attr(did, 'name') or did,"
    "'model': device_attr(did, 'model') or '',"
    "'mac': m.v,"
    "'config_url': device_attr(did, 'configuration_url') or '',"
    "'area_id': area_id(did) or '',"
    "'area_name': area_name(did) or '',"
    "'entities': ents.items,"
    "'input_entities': ents.inputs"
    "}] %}"
    "{% endif %}"
    "{% endfor %}"
    "{{ ns.devs | tojson }}"
)


def _walk_nested_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_nested_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_nested_dicts(item)


def _extract_entity_ids(obj):
    out = set()
    if isinstance(obj, str) and '.' in obj:
        out.add(obj.strip())
    elif isinstance(obj, list):
        for item in obj:
            out.update(_extract_entity_ids(item))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'entity_id':
                out.update(_extract_entity_ids(v))
            else:
                out.update(_extract_entity_ids(v))
    return out


def _infer_input_channel_from_trigger(trig, matched_eids):
    for eid in matched_eids:
        m = re.search(r'(?:input|button)_(\d+)', eid)
        if m:
            return max(0, min(3, int(m.group(1))))
    subtype = str(trig.get('subtype') or '').lower()
    m_sub = re.search(r'(?:button|input)[_\s-]?(\d+)', subtype)
    if m_sub:
        val = int(m_sub.group(1))
        # HA Shelly device triggers use button1/button2 (1-based)
        return max(0, min(3, val - 1 if 'button' in subtype and val >= 1 else val))
    ev_data = trig.get('event_data') if isinstance(trig.get('event_data'), dict) else {}
    if 'channel' in ev_data:
        try:
            ch = int(ev_data['channel'])
            return max(0, min(3, ch - 1 if ch >= 1 else ch))
        except Exception:
            pass
    return 0


def detect_detached_switch_suggestions(devices, fans, automations_path='/config/automations.yaml'):
    """Auto-detect detached Shelly wall switch -> Tuya BLE fan light bindings.

    Tier 1: Parse HA automations.yaml for triggers on a discovered Shelly + light actions on a fan.
    Tier 2: Fallback suggestion when a Shelly with input entities shares an HA area with a fan.
    """
    if not devices or not fans:
        return []

    fan_by_light = {}
    for f in fans:
        le = str(f.get('light_entity_id') or '').strip()
        if le:
            fan_by_light[le] = f

    dev_by_ha_id = {str(d.get('ha_device_id') or ''): d for d in devices if d.get('ha_device_id')}
    dev_by_input_eid = {}
    for d in devices:
        for ie in (d.get('input_entities') or []):
            dev_by_input_eid[str(ie)] = d

    suggestions = []
    seen_keys = set()

    # Tier 1: Parse /config/automations.yaml
    if automations_path and os.path.isfile(automations_path):
        try:
            with open(automations_path, 'r', encoding='utf-8') as f:
                autos = yaml.safe_load(f) or []
        except Exception:
            autos = []
        if isinstance(autos, list):
            for auto in autos:
                if not isinstance(auto, dict):
                    continue
                triggers = auto.get('triggers') or auto.get('trigger') or []
                actions = auto.get('actions') or auto.get('action') or []
                if isinstance(triggers, dict):
                    triggers = [triggers]
                if isinstance(actions, dict):
                    actions = [actions]

                matched_fans = []
                for act in _walk_nested_dicts(actions):
                    svc = str(act.get('action') or act.get('service') or '').strip().lower()
                    if svc not in ('light.toggle', 'light.turn_on', 'light.turn_off'):
                        continue
                    target_eids = _extract_entity_ids(act.get('target') or act.get('entity_id'))
                    for eid in target_eids:
                        if eid in fan_by_light:
                            matched_fans.append((eid, fan_by_light[eid]))
                if not matched_fans:
                    continue

                alias = str(auto.get('alias') or auto.get('id') or 'HA automation')
                for trig in triggers:
                    if not isinstance(trig, dict):
                        continue
                    matched_dev = None
                    matched_eids = []
                    tdid = str(trig.get('device_id') or '')
                    if tdid and tdid in dev_by_ha_id:
                        matched_dev = dev_by_ha_id[tdid]
                    if matched_dev is None:
                        for eid in _extract_entity_ids(trig):
                            if eid in dev_by_input_eid:
                                matched_dev = dev_by_input_eid[eid]
                                matched_eids.append(eid)
                    if matched_dev is None:
                        continue
                    ch = _infer_input_channel_from_trigger(trig, matched_eids)
                    if ch in (matched_dev.get('button_channels') or []):
                        continue
                    mac = matched_dev.get('mac_address') or ''
                    for light_eid, fan in matched_fans:
                        key = (mac, ch, light_eid)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        suggestions.append({
                            'name': matched_dev.get('name') or mac,
                            'mac_address': mac,
                            'input_channel': ch,
                            'target_fan_device_id': str(fan.get('device_id') or ''),
                            'target_light_entity_id': light_eid,
                            'source': 'automation',
                            'reason': f"Automation: {alias}",
                        })

    # Tier 2: Same HA area fallback — ONLY for Shellys with verified detached switch inputs
    # (never suggest covers, attached light switches, or button-mode inputs).
    matched_macs = {s['mac_address'] for s in suggestions}
    for d in devices:
        mac = d.get('mac_address') or ''
        area_name = str(d.get('area_name') or '').strip().lower()
        if not mac or mac in matched_macs or not area_name:
            continue
        # Never suggest a cover/blind controller as a detached wall switch
        if any((e.get('kind') == 'cover') for e in (d.get('entities') or [])):
            continue
        detached_chs = d.get('detached_channels')
        if not isinstance(detached_chs, list) or len(detached_chs) == 0:
            continue
        for f in fans:
            le = str(f.get('light_entity_id') or '').strip()
            if not le:
                continue
            fan_hay = f"{f.get('name', '')} {f.get('fan_entity_id', '')} {le}".lower()
            if area_name in fan_hay:
                ch = int(detached_chs[0])
                key = (mac, ch, le)
                if key not in seen_keys:
                    seen_keys.add(key)
                    suggestions.append({
                        'name': d.get('name') or mac,
                        'mac_address': mac,
                        'input_channel': ch,
                        'target_fan_device_id': str(f.get('device_id') or ''),
                        'target_light_entity_id': le,
                        'source': 'area',
                        'reason': f"Detached input:{ch} in {d.get('area_name')}",
                    })
                break

    return suggestions


def _probe_shelly_input_info(ip, timeout=1.2):
    """Query Shelly.GetConfig over local HTTP RPC and return (detached_switch_channels, button_channels, available_inputs).

    Inputs configured in button mode (input:N.type == 'button') are excluded from
    detached_switch_channels and recorded in button_channels so they are not suggested.
    """
    if not ip:
        return [], [], []
    try:
        cfg = _shelly_rpc_call(ip, 'Shelly.GetConfig', timeout=timeout)
    except Exception:
        return [], [], []
    if not isinstance(cfg, dict):
        return [], [], []
    sys_dev = (cfg.get('sys') or {}).get('device') if isinstance(cfg.get('sys'), dict) else {}
    if isinstance(sys_dev, dict) and str(sys_dev.get('profile') or '').lower() == 'cover':
        return [], [], []

    detached = []
    buttons = []
    available = []
    for ch in range(4):
        sw = cfg.get(f'switch:{ch}')
        lt = cfg.get(f'light:{ch}')
        inp = cfg.get(f'input:{ch}')
        if isinstance(inp, dict) or isinstance(sw, dict) or isinstance(lt, dict):
            available.append(ch)
        if isinstance(inp, dict) and str(inp.get('type') or '').lower() == 'button':
            buttons.append(ch)
            continue
        if isinstance(sw, dict):
            if str(sw.get('in_mode') or '').lower() == 'detached':
                detached.append(ch)
        elif isinstance(lt, dict):
            if str(lt.get('in_mode') or '').lower() == 'detached':
                detached.append(ch)
        elif isinstance(inp, dict):
            # Standalone switch-mode input without a relay (e.g. Shelly i4 in switch mode)
            detached.append(ch)
    return detached, buttons, available


def _probe_shelly_detached_channels(ip, timeout=1.2):
    """Query Shelly.GetConfig over local HTTP RPC and return list of detached switch-mode input channels."""
    detached, _, _ = _probe_shelly_input_info(ip, timeout=timeout)
    return detached


def _encode_detached_switches_blob(detached_switches):
    lines = []
    for ds in (detached_switches or []):
        name = str(ds.get('name') or '').replace('|', ' ').replace('\n', ' ').strip()
        mac = _normalize_shelly_mac(ds.get('mac_address') or '')
        if len(mac) != 12:
            continue
        ch = max(0, min(3, int(ds.get('input_channel') or 0)))
        fan_id = str(ds.get('target_fan_device_id') or '').replace('|', '').strip()
        light_id = str(ds.get('target_light_entity_id') or '').replace('|', '').strip()
        lines.append(f"{name}|{mac}|{ch}|{fan_id}|{light_id}")
    return '\n'.join(lines)


def push_detached_switches_live_to_hubs(detached_switches, esphome_dir=None):
    """Push detached switch rules live to all online headless hubs via HA ESPHome API service."""
    if not SUPERVISOR_TOKEN:
        return []
    hubs = list_ble_hubs(esphome_dir)
    blob = _encode_detached_switches_blob(detached_switches)
    pushed = []
    for hub in hubs:
        hub_slug = re.sub(r'[^a-z0-9]+', '_', str(hub.get('name') or '').lower()).strip('_')
        if not hub_slug:
            continue
        svc = f"{hub_slug}_sync_shelly_detached_switches"
        try:
            r = requests.post(
                f"{HA_URL}/api/services/esphome/{svc}",
                headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}', 'Content-Type': 'application/json'},
                json={'rules': blob},
                timeout=5,
            )
            if r.ok:
                pushed.append(hub['name'])
        except Exception:
            pass
    return pushed


def _collect_all_detached_switches(esphome_dir=None):
    hubs = list_ble_hubs(esphome_dir)
    seen = set()
    out = []
    for h in hubs:
        for ds in (h.get('detached_switches') or []):
            key = (
                _normalize_shelly_mac(ds.get('mac_address') or ''),
                int(ds.get('input_channel') or 0),
                str(ds.get('target_light_entity_id') or ''),
                str(ds.get('target_fan_device_id') or ''),
            )
            if not key[0] or key in seen:
                continue
            seen.add(key)
            out.append({
                'name': str(ds.get('name') or key[0]),
                'mac_address': key[0],
                'input_channel': key[1],
                'target_fan_device_id': key[3],
                'target_light_entity_id': key[2],
            })
    return out


def sync_detached_switches_to_all_hubs(detached_switches, esphome_dir=None):
    """Sync house-wide detached wall switch rules onto every headless hub YAML."""
    root_dir = esphome_dir or BASE_DIR
    hubs = list_ble_hubs(root_dir)
    updated = []
    for hub in hubs:
        payload = {
            'filename': hub['filename'],
            'name': hub['name'],
            'board': hub['board'],
            'fallback_channel': hub.get('fallback_channel', 1),
            'network_key': hub.get('network_key') or get_or_create_espnow_network_key(root_dir),
            'fans': hub.get('fans') or [],
            'gree_ac': hub.get('gree_ac'),
            'shellys': [],  # Dynamic zero-config Shelly discovery on all hubs
            'detached_switches': detached_switches,
        }
        res, err, status = save_ble_hub_yaml(payload, esphome_dir=root_dir)
        if status == 200 and res:
            updated.append(hub['filename'])
    return updated


def _collect_entity_to_cyds_map(esphome_dir=None):
    """Scan all CYD YAML files and map referenced entity_id -> sorted list of CYD device names."""
    root_dir = esphome_dir or BASE_DIR
    entity_to_cyds = {}
    if not root_dir or not os.path.isdir(root_dir):
        return entity_to_cyds

    hub_files = {h['filename'].lower() for h in list_ble_hubs(root_dir)}
    skip_files = {'secrets.yaml', 'lib.yaml'}

    def _walk_strings(obj, out_set):
        if isinstance(obj, str):
            base = obj.split('|')[0].strip()
            if '.' in base and ' ' not in base:
                dom = base.split('.', 1)[0]
                if dom in ('switch', 'light', 'cover', 'fan', 'climate', 'sensor', 'binary_sensor'):
                    out_set.add(base)
        elif isinstance(obj, list):
            for item in obj:
                _walk_strings(item, out_set)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk_strings(v, out_set)

    class _CydTagLoader(yaml.SafeLoader):
        pass

    _CydTagLoader.add_multi_constructor('!', lambda loader, suffix, node: (
        loader.construct_mapping(node) if isinstance(node, yaml.MappingNode)
        else loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
        else loader.construct_scalar(node)
    ))

    for fname in sorted(os.listdir(root_dir)):
        if not fname.endswith(('.yaml', '.yml')):
            continue
        low = fname.lower()
        if low in skip_files or low in hub_files:
            continue
        fpath = os.path.join(root_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception:
            continue
        if 'tile_ui:' not in text:
            continue
        try:
            parsed = yaml.load(text, Loader=_CydTagLoader) or {}
        except Exception:
            continue
        if not isinstance(parsed, dict) or 'tile_ui' not in parsed:
            continue
        cyd_name = os.path.splitext(fname)[0]
        subs = parsed.get('substitutions') if isinstance(parsed.get('substitutions'), dict) else {}
        if subs.get('device_name'):
            cyd_name = str(subs['device_name']).strip()
        refs = set()
        _walk_strings(parsed.get('tile_ui'), refs)
        for eid in refs:
            entity_to_cyds.setdefault(eid, set()).add(cyd_name)

    return {eid: sorted(names) for eid, names in entity_to_cyds.items()}


def _is_shelly_script_switch(entity_id):
    low = str(entity_id or '').lower()
    if not low.startswith('switch.'):
        return False
    return 'cyd_ble_backup' in low or '_script_' in low or low.endswith('_script')


def _parse_discovered_shelly_devices(raw_devs, entity_to_cyds=None):
    """Merge HA Shelly parent + multi-channel sub-devices by MAC and deduplicate switch_as_x helpers."""
    entity_to_cyds = entity_to_cyds or {}
    raw_list = [d for d in (raw_devs if isinstance(raw_devs, list) else []) if isinstance(d, dict)]

    # Index parent MACs by ha_device_id so child sub-devices with empty connections resolve via via_device_id
    mac_by_did = {}
    for d in raw_list:
        did = str(d.get('ha_device_id') or '')
        mac = _normalize_shelly_mac(d.get('mac') or '')
        if len(mac) != 12:
            sid = str(d.get('shelly_id') or '').strip()
            if sid:
                mac = _normalize_shelly_mac(sid.split('-', 1)[0])
        if did and len(mac) == 12:
            mac_by_did[did] = mac

    grouped = {}
    for d in raw_list:
        sid = str(d.get('shelly_id') or '').strip()
        m_sub = re.search(r'-(?:switch|light|cover):(\d+)$', sid, re.I)
        sub_ch = max(0, min(3, int(m_sub.group(1)))) if m_sub else None

        mac = _normalize_shelly_mac(d.get('mac') or '')
        if len(mac) != 12 and sid:
            mac = _normalize_shelly_mac(sid.split('-', 1)[0])
        if len(mac) != 12:
            via = str(d.get('via_device_id') or '')
            if via and via in mac_by_did:
                mac = mac_by_did[via]
        if len(mac) != 12:
            continue

        is_sub = (sub_ch is not None) or bool(d.get('via_device_id'))
        cfg_url = str(d.get('config_url') or '')
        m_ip = re.search(r'https?://([^/:]+)', cfg_url)
        ip = m_ip.group(1) if m_ip else ''

        rec = grouped.get(mac)
        if rec is None:
            rec = {
                'ha_device_id': str(d.get('ha_device_id') or ''),
                'name': str(d.get('name') or mac),
                'model': str(d.get('model') or ''),
                'mac_address': mac,
                'ip': ip,
                'area_id': str(d.get('area_id') or ''),
                'area_name': str(d.get('area_name') or ''),
                'entities_by_slot': {},
                'input_entities': set(),
                'used_by_cyds': set(),
                '_has_parent': not is_sub,
            }
            grouped[mac] = rec
        else:
            if not is_sub and not rec['_has_parent']:
                rec['ha_device_id'] = str(d.get('ha_device_id') or rec['ha_device_id'])
                rec['name'] = str(d.get('name') or rec['name'])
                rec['model'] = str(d.get('model') or rec['model'])
                rec['_has_parent'] = True
            if ip and not rec['ip']:
                rec['ip'] = ip
            if not rec['model'] and d.get('model'):
                rec['model'] = str(d.get('model'))
            if not rec['area_id'] and d.get('area_id'):
                rec['area_id'] = str(d.get('area_id'))
            if not rec['area_name'] and d.get('area_name'):
                rec['area_name'] = str(d.get('area_name'))

        for inp in (d.get('input_entities') or []):
            rec['input_entities'].add(str(inp))

        ents = d.get('entities') if isinstance(d.get('entities'), list) else []
        for ent in ents:
            if not isinstance(ent, dict):
                continue
            eid = str(ent.get('entity_id') or '').strip()
            if not eid or _is_shelly_script_switch(eid):
                continue
            dom = str(ent.get('domain') or 'switch').strip().lower()
            kind = dom if dom in ('switch', 'light', 'cover') else 'switch'
            if sub_ch is not None:
                ch = sub_ch
            elif kind == 'cover':
                ch = 0
            else:
                m_ch = re.search(r'(?:switch|light|output|channel)_(\d+)$', eid)
                ch = max(0, min(3, int(m_ch.group(1)))) if m_ch else 0

            cyd_list = list(entity_to_cyds.get(eid, []))
            rec['used_by_cyds'].update(cyd_list)

            slot = ('cover' if kind == 'cover' else 'output', ch)
            existing = rec['entities_by_slot'].get(slot)
            candidate = {
                'entity_id': eid,
                'name': str(ent.get('name') or eid),
                'kind': kind,
                'channel': ch,
                'cyd_devices': cyd_list,
            }
            if existing is None:
                rec['entities_by_slot'][slot] = candidate
            else:
                merged_cyds = sorted(set(existing['cyd_devices']) | set(cyd_list))
                # Prefer HA switch_as_x 'light' helper over the hidden underlying 'switch'
                if existing['kind'] != 'light' and candidate['kind'] == 'light':
                    candidate['cyd_devices'] = merged_cyds
                    rec['entities_by_slot'][slot] = candidate
                else:
                    existing['cyd_devices'] = merged_cyds

    devices = []
    for rec in grouped.values():
        parsed_entities = sorted(
            rec['entities_by_slot'].values(),
            key=lambda e: (0 if e['kind'] != 'cover' else 1, e['channel'], e['entity_id']),
        )
        devices.append({
            'ha_device_id': rec['ha_device_id'],
            'name': rec['name'],
            'model': rec['model'],
            'mac_address': rec['mac_address'],
            'ip': rec['ip'],
            'area_id': rec['area_id'],
            'area_name': rec['area_name'],
            'entities': parsed_entities,
            'input_entities': sorted(rec['input_entities']),
            'used_by_cyds': sorted(rec['used_by_cyds']),
        })
    return devices


@shelly_bp.route('/api/shelly/devices', methods=['GET'])
def api_discover_shelly_devices():
    """Auto-discover Shelly devices, entities, areas, CYD usage, and detached-switch suggestions from HA."""
    hubs = list_ble_hubs()
    all_fans = [f for h in hubs for f in (h.get('fans') or [])]
    detached_switches = _collect_all_detached_switches()
    network_key = get_or_create_espnow_network_key()
    entity_to_cyds = _collect_entity_to_cyds_map()

    if not SUPERVISOR_TOKEN:
        return jsonify({
            'devices': [],
            'suggestions': [],
            'detached_switches': detached_switches,
            'network_key': network_key,
            'error': 'Home Assistant Supervisor API not available in local dev mode',
        }), 200
    try:
        resp = requests.post(
            f"{HA_URL}/api/template",
            headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}', 'Content-Type': 'application/json'},
            json={'template': _SHELLY_HA_DISCOVERY_TEMPLATE},
            timeout=10,
        )
        if not resp.ok:
            detail = (resp.text or '').strip()[:300]
            return jsonify({'devices': [], 'error': f"HA template error ({resp.status_code}): {detail or resp.reason}"}), 502
        raw_devs = json.loads(resp.text or '[]')
        devices = _parse_discovered_shelly_devices(raw_devs, entity_to_cyds)
        # Cache HA friendly names so hub YAMLs automatically label Visible Shellys by name
        for dev in devices:
            if dev.get('mac_address') and dev.get('name'):
                _CACHED_SHELLY_KNOWN_NAMES[dev['mac_address']] = str(dev['name'])[:32]
        # Probe Shelly.GetConfig in parallel for non-cover devices to detect truly detached inputs
        from concurrent.futures import ThreadPoolExecutor
        probe_targets = [
            dev for dev in devices
            if dev.get('ip') and not any(e.get('kind') == 'cover' for e in (dev.get('entities') or []))
        ]
        for dev in devices:
            dev['detached_channels'] = []
            dev['button_channels'] = []
            dev['available_inputs'] = []
        if probe_targets:
            with ThreadPoolExecutor(max_workers=12) as pool:
                futs = {pool.submit(_probe_shelly_input_info, dev['ip']): dev for dev in probe_targets}
                for fut, dev in futs.items():
                    try:
                        det_chs, btn_chs, avail_chs = fut.result()
                        dev['detached_channels'] = det_chs
                        dev['button_channels'] = btn_chs
                        dev['available_inputs'] = avail_chs
                    except Exception:
                        dev['detached_channels'] = []
                        dev['button_channels'] = []
                        dev['available_inputs'] = []
        # Put Shellys referenced by any CYD first, then alphabetically
        devices.sort(key=lambda x: (0 if x['used_by_cyds'] else 1, x['name'].lower()))
        suggestions = detect_detached_switch_suggestions(devices, all_fans)
        return jsonify({
            'devices': devices,
            'suggestions': suggestions,
            'detached_switches': detached_switches,
            'network_key': network_key,
        })
    except Exception as e:
        return jsonify({'devices': [], 'error': str(e)}), 500


@shelly_bp.route('/api/shelly/sync_detached_switches', methods=['POST'])
def api_sync_detached_switches():
    """Sync house-wide detached wall switch bindings to all headless hubs (YAML + live HA service)."""
    try:
        payload = request.get_json(silent=True) or {}
        raw_list = payload.get('detached_switches') if isinstance(payload.get('detached_switches'), list) else []
        cleaned = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            mac = _normalize_shelly_mac(item.get('mac_address') or '')
            if len(mac) != 12:
                continue
            cleaned.append({
                'name': str(item.get('name') or mac).strip() or mac,
                'mac_address': mac,
                'input_channel': max(0, min(3, int(item.get('input_channel') or 0))),
                'target_fan_device_id': str(item.get('target_fan_device_id') or '').strip(),
                'target_light_entity_id': str(item.get('target_light_entity_id') or '').strip(),
            })
        updated = sync_detached_switches_to_all_hubs(cleaned)
        live_pushed = push_detached_switches_live_to_hubs(cleaned)
        return jsonify({
            'ok': True,
            'updated_hubs': updated,
            'live_pushed_hubs': live_pushed,
            'detached_switches': cleaned,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@shelly_bp.route('/api/shelly/deploy_script', methods=['POST'])
def api_deploy_shelly_script():
    """Deploy cyd_ble_backup.js to one or more Shelly Gen3/Gen4 devices via local HTTP RPC."""
    try:
        payload = request.get_json(silent=True) or {}
        targets = payload.get('targets') if isinstance(payload.get('targets'), list) else []
        if not targets:
            return jsonify({'error': 'At least one Shelly target with an IP address is required'}), 400
        network_key = str(payload.get('network_key') or '').strip() or get_or_create_espnow_network_key()
        password = str(payload.get('password') or '').strip() or None

        template = _load_shelly_script_template()
        if not template:
            return jsonify({'error': 'shelly/cyd_ble_backup.js not found in add-on'}), 500
        safe_key = network_key.replace('\\', '\\\\').replace('"', '\\"')
        script_code = template.replace('__NETWORK_KEY__', safe_key)

        results = []
        seen_ips = set()
        for t in targets:
            if not isinstance(t, dict):
                continue
            ip = str(t.get('ip') or '').strip()
            name = str(t.get('name') or ip).strip()
            if not ip or ip in seen_ips:
                continue
            seen_ips.add(ip)
            try:
                res = deploy_shelly_script_to_device(ip, script_code, password=password)
                res['name'] = name
                results.append(res)
            except Exception as e:
                results.append({
                    'ip': ip,
                    'name': name,
                    'ok': False,
                    'error': str(e),
                })

        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

