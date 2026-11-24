import json
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "api_proxy" not in sys.modules:
    sys.modules["api_proxy"] = types.SimpleNamespace(run_proxy_thread=lambda *a, **kw: None)
if "aioesphomeapi" not in sys.modules:
    sys.modules["aioesphomeapi"] = types.SimpleNamespace(APIClient=object)

import github_sync
import server


def _write_storage(tmp_path: Path, entries: list, entities: list):
    storage = tmp_path / ".storage"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "core.config_entries").write_text(
        json.dumps({"data": {"entries": entries}}),
        encoding="utf-8",
    )
    (storage / "core.entity_registry").write_text(
        json.dumps({"data": {"entities": entities}}),
        encoding="utf-8",
    )


def test_discover_tuya_ble_fans_matches_fans_and_companion_lights(tmp_path):
    _write_storage(
        tmp_path,
        entries=[
            {
                "entry_id": "e_office",
                "domain": "tuya_local",
                "title": "Office Fan",
                "data": {
                    "device_id": "bf_office_123",
                    "local_key": "secret_office_key",
                    "product_id": "vfqiwthdnlkynebk",
                },
            },
            {
                "entry_id": "e_tv",
                "domain": "tuya_local",
                "title": "TV Room Fan",
                "data": {
                    "device_id": "bf_tv_456",
                    "local_key": "secret_tv_key",
                    "product_id": "hceemlamlwxpufpa",
                },
            },
            {
                "entry_id": "e_plug",
                "domain": "tuya_local",
                "title": "Smart Plug",
                "data": {
                    "device_id": "bf_plug_789",
                    "local_key": "secret_plug_key",
                    "product_id": "other_plug_pid",
                },
            },
        ],
        entities=[
            {"config_entry_id": "e_office", "entity_id": "fan.office_fan"},
            {"config_entry_id": "e_office", "entity_id": "light.office_fan_light"},
            {"config_entry_id": "e_tv", "entity_id": "fan.tv_room_fan"},
            {"config_entry_id": "e_tv", "entity_id": "light.tv_room_fan_light"},
            {"config_entry_id": "e_plug", "entity_id": "switch.smart_plug"},
        ],
    )

    fans = server.discover_tuya_ble_fans(str(tmp_path))
    assert len(fans) == 2

    office = next(f for f in fans if f["device_id"] == "bf_office_123")
    assert office["name"] == "Office Fan"
    assert office["local_key"] == "secret_office_key"
    assert office["product_id"] == "vfqiwthdnlkynebk"
    assert office["fan_entity_id"] == "fan.office_fan"
    assert office["light_entity_id"] == "light.office_fan_light"
    assert office["supported"] is True

    tv = next(f for f in fans if f["device_id"] == "bf_tv_456")
    assert tv["fan_entity_id"] == "fan.tv_room_fan"
    assert tv["light_entity_id"] == "light.tv_room_fan_light"


def test_tuya_ble_fans_api_endpoint(tmp_path, monkeypatch):
    _write_storage(
        tmp_path,
        entries=[
            {
                "entry_id": "e_office",
                "domain": "tuya_local",
                "title": "Office Fan",
                "data": {
                    "device_id": "bf_office_123",
                    "local_key": "secret_office_key",
                    "product_id": "vfqiwthdnlkynebk",
                },
            }
        ],
        entities=[
            {"config_entry_id": "e_office", "entity_id": "fan.office_fan"},
            {"config_entry_id": "e_office", "entity_id": "light.office_fan_light"},
        ],
    )
    monkeypatch.setenv("HA_CONFIG_DIR", str(tmp_path))
    client = server.app.test_client()
    resp = client.get("/api/tuya_ble_fans")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert len(payload["fans"]) == 1
    assert payload["fans"][0]["fan_entity_id"] == "fan.office_fan"


def test_github_sync_includes_tuya_ble_fan_component():
    assert (
        str(github_sync._managed_path("repo-main/esphome/external_components/tuya_ble_fan/__init__.py"))
        == "external_components/tuya_ble_fan/__init__.py"
    )
    assert (
        str(github_sync._managed_path("repo-main/esphome/lib/tuya_ble_fan.yaml"))
        == "lib/tuya_ble_fan.yaml"
    )


def test_find_ble_fan_hosts_detects_existing_device_yamls(tmp_path):
    esphome_dir = tmp_path / "esphome"
    esphome_dir.mkdir()
    (esphome_dir / "office-cyd.yaml").write_text(
        "packages:\n"
        "  tuya_ble_fan: !include lib/tuya_ble_fan.yaml\n"
        "tuya_ble_fan:\n"
        "  fans:\n"
        "    - name: Office Fan\n"
        "      device_id: bf_office_123\n"
        "      local_key: secret\n",
        encoding="utf-8",
    )
    (esphome_dir / "living-cyd.yaml").write_text(
        "esphome:\n"
        "  name: living-cyd\n",
        encoding="utf-8",
    )

    hosts = server.find_ble_fan_hosts(str(esphome_dir))
    assert hosts == {"bf_office_123": ["office-cyd.yaml"]}


def test_generate_tuya_ble_credentials():
    dev_id1, key1 = server.generate_tuya_ble_credentials()
    dev_id2, key2 = server.generate_tuya_ble_credentials()
    assert len(dev_id1) == 22
    assert dev_id1.startswith("bf")
    assert len(key1) == 16
    assert dev_id1 != dev_id2
    assert key1 != key2


def test_aggregate_ble_scan_sightings_ranks_by_rssi_and_matches_ha():
    sightings = [
        {
            "cyd_filename": "hall-cyd.yaml",
            "cyd_name": "hall-cyd",
            "friendly_name": "Hall CYD",
            "mac": "aa:bb:cc:dd:ee:01",
            "addr_type": 0,
            "rssi": -78,
            "bound": "false",
            "uuid": "1122334455667788",
            "product_id": "hceemlamlwxpufpa",
        },
        {
            "cyd_filename": "sahar-cyd.yaml",
            "cyd_name": "sahar-cyd",
            "friendly_name": "Sahar CYD",
            "mac": "AA:BB:CC:DD:EE:01",
            "addr_type": 0,
            "rssi": -54,
            "bound": False,
            "uuid": "1122334455667788",
            "product_id": "hceemlamlwxpufpa",
        },
        {
            "cyd_filename": "office-cyd.yaml",
            "cyd_name": "office-cyd",
            "friendly_name": "Office CYD",
            "mac": "B8:06:0D:54:04:F6",
            "addr_type": 1,
            "rssi": -62,
            "bound": "true",
            "uuid": "9fdb2c8416a6872a",
            "product_id": "",
        },
    ]
    ha_fans = [
        {
            "name": "Office Fan",
            "device_id": "bf_office_123",
            "local_key": "1234567890abcdef",
            "product_id": "hceemlamlwxpufpa",
            "mac_address": "B8:06:0D:54:04:F6",
            "fan_entity_id": "fan.office_fan",
            "light_entity_id": "light.office_light",
        }
    ]
    hosted_by_id = {"bf_office_123": ["office-cyd.yaml"]}

    ranked = server.aggregate_ble_scan_sightings(
        sightings, tuya_local_fans=ha_fans, hosted_by_id=hosted_by_id
    )
    assert len(ranked) == 2

    # Strongest RSSI (-54) first
    first = ranked[0]
    assert first["mac"] == "AA:BB:CC:DD:EE:01"
    assert first["bound"] is False
    assert first["best_cyd"]["cyd_filename"] == "sahar-cyd.yaml"
    assert first["best_rssi"] == -54
    assert [s["cyd_filename"] for s in first["sightings"]] == ["sahar-cyd.yaml", "hall-cyd.yaml"]
    assert first["matched_ha_fan"] is None

    second = ranked[1]
    assert second["mac"] == "B8:06:0D:54:04:F6"
    assert second["bound"] is True
    assert second["matched_ha_fan"]["device_id"] == "bf_office_123"
    assert second["hosted_by"] == ["office-cyd.yaml"]


def test_extract_device_api_info_resolves_secret(tmp_path):
    (tmp_path / "secrets.yaml").write_text("api_enc_key: mySecretKeyBase64==\n", encoding="utf-8")
    dev_yaml = tmp_path / "sahar-cyd.yaml"
    dev_yaml.write_text(
        "esphome:\n  name: sahar-cyd\n"
        "api:\n  encryption:\n    key: !secret api_enc_key\n"
        "tile_ui:\n  screens: []\n",
        encoding="utf-8",
    )
    secrets_map = server._load_esphome_secrets(str(tmp_path))
    info = server._extract_device_api_info(str(dev_yaml), secrets_map)
    assert info["api_key"] == "mySecretKeyBase64=="


def test_add_ble_fan_to_device_yaml_preserves_tags_and_upserts(tmp_path):
    dev_yaml = tmp_path / "sahar-cyd.yaml"
    dev_yaml.write_text(
        "substitutions:\n"
        "  device_name: sahar-cyd\n"
        "packages:\n"
        "  device_base: !include lib/2432s028.yaml\n"
        "  ble_proxy: !include lib/ble_proxy.yaml\n"
        "wifi:\n"
        "  ssid: !secret wifi_ssid\n"
        "tile_ui:\n"
        "  screens: []\n",
        encoding="utf-8",
    )

    fans1 = server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Sahar Fan",
        "device_id": "bf00000000000000000001",
        "local_key": "0123456789abcdef",
        "product_id": "hceemlamlwxpufpa",
        "mac_address": "AA:BB:CC:DD:EE:01",
        "uuid": "1122334455667788",
        "expose_to_ha": True,
    })
    assert len(fans1) == 1
    text1 = dev_yaml.read_text(encoding="utf-8")
    assert "tuya_ble_fan: !include lib/tuya_ble_fan.yaml" in text1
    assert 'ble_max_connections: "2"' in text1
    assert "ssid: !secret wifi_ssid" in text1
    assert "idle_disconnect_s: 0" in text1

    # Add a second fan -> idle_disconnect_s switches to 30
    fans2 = server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Hall Fan",
        "device_id": "bf00000000000000000002",
        "local_key": "fedcba9876543210",
        "mac_address": "AA:BB:CC:DD:EE:02",
    })
    assert len(fans2) == 2
    text2 = dev_yaml.read_text(encoding="utf-8")
    assert "idle_disconnect_s: 30" in text2

    # Upsert first fan by device_id -> still 2 fans, updated name
    fans3 = server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Sahar Bedroom Fan",
        "device_id": "bf00000000000000000001",
        "local_key": "0123456789abcdef",
        "mac_address": "AA:BB:CC:DD:EE:01",
    })
    assert len(fans3) == 2
    assert fans3[0]["name"] == "Sahar Bedroom Fan"

