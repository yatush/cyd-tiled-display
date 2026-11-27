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
    assert 'display_buffer_size: "20%"' in text1
    assert "ssid: !secret wifi_ssid" in text1
    assert "max_connections: 1" in text1
    assert "idle_disconnect_s: 0" in text1

    # Add a second fan (with ble_proxy: 2 fan slots + 1 proxy = 3 total, still persistent!)
    fans2 = server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Hall Fan",
        "device_id": "bf00000000000000000002",
        "local_key": "fedcba9876543210",
        "mac_address": "AA:BB:CC:DD:EE:02",
    })
    assert len(fans2) == 2
    text2 = dev_yaml.read_text(encoding="utf-8")
    assert 'ble_max_connections: "3"' in text2
    assert 'display_buffer_size: "15%"' in text2
    assert "max_connections: 2" in text2
    assert "idle_disconnect_s: 0" in text2

    # Add a third fan (with ble_proxy: exceeds 2 fan slots -> shared slots, idle_disconnect_s: 30)
    fans3 = server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Guest Fan",
        "device_id": "bf00000000000000000003",
        "local_key": "1111222233334444",
        "mac_address": "AA:BB:CC:DD:EE:03",
    })
    assert len(fans3) == 3
    text3 = dev_yaml.read_text(encoding="utf-8")
    assert "max_connections: 2" in text3
    assert "idle_disconnect_s: 30" in text3

    # Upsert first fan by device_id -> still 3 fans, updated name
    fans4 = server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Sahar Bedroom Fan",
        "device_id": "bf00000000000000000001",
        "local_key": "0123456789abcdef",
        "mac_address": "AA:BB:CC:DD:EE:01",
    })
    assert len(fans4) == 3
    assert fans4[0]["name"] == "Sahar Bedroom Fan"


def test_add_ble_fan_preserves_backslashes_comments_and_secrets(tmp_path):
    dev_yaml = tmp_path / "office-cyd.yaml"
    dev_yaml.write_text(
        "packages: # inline comment\n"
        "  device_base: !include lib/3248s035.yaml\n"
        "  tuya_ble_fan: !include lib/tuya_ble_fan.yaml\n"
        "tuya_ble_fan:\n"
        "# column-0 comment inside block\n"
        "  idle_disconnect_s: 0\n"
        "  fans:\n"
        "    - name: Existing Fan\n"
        "      device_id: bf_existing_0000000001\n"
        "      local_key: !secret office_fan_key\n"
        "      product_id: hceemlamlwxpufpa\n"
        "wifi:\n"
        "  ssid: !secret wifi_ssid\n",
        encoding="utf-8",
    )

    fans = server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Backslash Fan",
        "device_id": "bf_new_000000000000002",
        "local_key": r"ab\1cd\gef\\9012",
        "mac_address": "AA:BB:CC:DD:EE:99",
    })
    assert len(fans) == 2
    text = dev_yaml.read_text(encoding="utf-8")
    # Existing !secret must be preserved, not turned into null
    assert "!secret 'office_fan_key'" in text or "!secret office_fan_key" in text
    assert "local_key: null" not in text
    # wifi section after tuya_ble_fan must remain intact
    assert "wifi:\n  ssid: !secret wifi_ssid" in text
    # Backslashes in new key must survive round-trip
    parsed = server.yaml.load(text, Loader=server.generate_tiles_api.create_safe_yaml_loader())
    assert parsed["tuya_ble_fan"]["fans"][1]["local_key"] == r"ab\1cd\gef\\9012"


def test_extract_device_api_info_after_tile_ui_and_custom_port(tmp_path):
    (tmp_path / "secrets.yaml").write_text("my_api_key: KeyAfterTileUi==\n", encoding="utf-8")
    dev_yaml = tmp_path / "custom-cyd.yaml"
    dev_yaml.write_text(
        "substitutions:\n  api_port: \"6054\"\n"
        "tile_ui:\n  screens:\n    - id: main\n"
        "api:\n  encryption:\n    key: !secret my_api_key\n",
        encoding="utf-8",
    )
    secrets_map = server._load_esphome_secrets(str(tmp_path))
    info = server._extract_device_api_info(str(dev_yaml), secrets_map)
    assert info["api_key"] == "KeyAfterTileUi=="
    assert info["api_port"] == 6054


def test_discover_tuya_ble_fans_reads_device_registry_mac_and_isolates_localtuya(tmp_path):
    storage = tmp_path / ".storage"
    storage.mkdir()
    (storage / "core.config_entries").write_text(json.dumps({
        "data": {
            "entries": [
                {
                    "entry_id": "e_tuya",
                    "domain": "tuya_local",
                    "title": "Office Fan",
                    "data": {
                        "device_id": "bf_office_123",
                        "local_key": "0123456789abcdef",
                        "product_id": "hceemlamlwxpufpa",
                    },
                },
                {
                    "entry_id": "e_lt",
                    "domain": "localtuya",
                    "title": "LocalTuya Hub",
                    "data": {
                        "devices": {
                            "lt_fan_1": {"friendly_name": "LT Fan", "local_key": "aaaaaaaaaaaaaaaa"},
                            "lt_plug_1": {"friendly_name": "LT Plug", "local_key": "bbbbbbbbbbbbbbbb"},
                        }
                    },
                },
            ]
        }
    }), encoding="utf-8")
    (storage / "core.entity_registry").write_text(json.dumps({
        "data": {
            "entities": [
                {"config_entry_id": "e_tuya", "entity_id": "fan.office_fan", "unique_id": "bf_office_123_fan"},
                {"config_entry_id": "e_lt", "entity_id": "fan.lt_fan", "unique_id": "local_lt_fan_1_1"},
                {"config_entry_id": "e_lt", "entity_id": "switch.lt_plug", "unique_id": "local_lt_plug_1_1"},
            ]
        }
    }), encoding="utf-8")
    (storage / "core.device_registry").write_text(json.dumps({
        "data": {
            "devices": [
                {
                    "config_entries": ["e_tuya"],
                    "identifiers": [["tuya_local", "bf_office_123"]],
                    "connections": [["mac", "b8:06:0d:54:04:f6"]],
                }
            ]
        }
    }), encoding="utf-8")

    fans = server.discover_tuya_ble_fans(str(tmp_path))
    by_id = {f["device_id"]: f for f in fans}
    assert "bf_office_123" in by_id
    assert by_id["bf_office_123"]["mac_address"] == "B8:06:0D:54:04:F6"
    assert "lt_fan_1" in by_id
    assert "lt_plug_1" not in by_id


def test_ble_fan_vault_persists_after_yaml_and_ha_removal(tmp_path):
    esphome_dir = tmp_path / "esphome"
    esphome_dir.mkdir()
    ha_dir = tmp_path / "ha"
    ha_dir.mkdir()
    dev_yaml = esphome_dir / "office-cyd.yaml"
    dev_yaml.write_text(
        "substitutions:\n  device_name: office-cyd\npackages:\n  device_base: !include lib/3248s035.yaml\n",
        encoding="utf-8",
    )

    server.add_ble_fan_to_device_yaml(str(dev_yaml), {
        "name": "Office Fan",
        "device_id": "bf_office_vault_001",
        "local_key": "vault_secret_key",
        "mac_address": "b8:06:0d:54:04:f6",
        "uuid": "9fdb2c8416a6872a",
        "fan_entity_id": "fan.office_cyd_office_fan",
        "light_entity_id": "light.office_cyd_office_fan_light",
    })

    # Simulate deleting the fan from the CYD YAML (and having no HA Tuya integration)
    dev_yaml.write_text(
        "substitutions:\n  device_name: office-cyd\npackages:\n  device_base: !include lib/3248s035.yaml\n",
        encoding="utf-8",
    )

    known = server.get_all_known_tuya_ble_fans(str(ha_dir), str(esphome_dir))
    assert len(known) == 1
    assert known[0]["device_id"] == "bf_office_vault_001"
    assert known[0]["local_key"] == "vault_secret_key"
    assert known[0]["mac_address"] == "B8:06:0D:54:04:F6"
    assert known[0]["uuid"] == "9fdb2c8416a6872a"
    assert (esphome_dir / ".cyd_ble_fans.json").is_file()


def test_espnow_network_key_and_headless_hub_crud(tmp_path):
    key1 = server.get_or_create_espnow_network_key(str(tmp_path))
    assert key1 == "cyd_espnow_default"
    # Calling again returns the exact same deterministic default key
    assert server.get_or_create_espnow_network_key(str(tmp_path)) == key1

    # Saving fans to vault preserves espnow_network_key
    fan_a = {
        "name": "Bedroom Fan",
        "device_id": "bf_hub_test_00000001",
        "local_key": "0123456789abcdef",
        "fan_entity_id": "fan.bedroom_fan",
        "light_entity_id": "light.bedroom_light",
        "mac_address": "AA:BB:CC:DD:EE:11",
    }
    server.save_ble_fans_to_vault([fan_a], str(tmp_path))
    assert server.get_or_create_espnow_network_key(str(tmp_path)) == key1

    # Create a headless hub hosting fan_a
    res, err, status = server.save_ble_hub_yaml(
        {
            "name": "Bedroom BLE Hub",
            "board": "seeed_xiao_esp32c3",
            "fallback_channel": 6,
            "fans": [fan_a],
        },
        esphome_dir=str(tmp_path),
    )
    assert status == 200 and err is None
    assert res["filename"] == "bedroom-ble-hub.yaml"
    assert res["name"] == "bedroom-ble-hub"
    assert res["board"] == "seeed_xiao_esp32c3"
    assert res["fallback_channel"] == 6
    assert res["network_key"] == key1

    # Verify _parse_device_yaml recognizes headless hubs as OTA-capable managed devices
    meta = server._parse_device_yaml(str(tmp_path / "bedroom-ble-hub.yaml"))
    assert meta is not None
    assert meta["is_headless_hub"] is True
    assert meta["has_ota"] is True
    assert meta["address"] == "bedroom-ble-hub.local"
    assert server._classify_batch_device(meta, online=True)[0] == "pending"

    hubs = server.list_ble_hubs(str(tmp_path))
    assert len(hubs) == 1
    assert hubs[0]["filename"] == "bedroom-ble-hub.yaml"
    assert hubs[0]["board"] == "seeed_xiao_esp32c3"
    assert hubs[0]["fans"][0]["fan_entity_id"] == "fan.bedroom_fan"

    # Trying to assign the same fan to a second hub MUST fail with 409 Conflict
    res2, err2, status2 = server.save_ble_hub_yaml(
        {
            "name": "Hallway Hub",
            "board": "esp32dev",
            "fans": [fan_a],
        },
        esphome_dir=str(tmp_path),
    )
    assert status2 == 409 and res2 is None
    assert len(err2["conflicts"]) == 1
    assert err2["conflicts"][0]["host_file"] == "bedroom-ble-hub.yaml"

    # Reassigning moves fan_a atomically from bedroom-ble-hub.yaml to hallway-hub.yaml
    res3, err3, status3 = server.save_ble_hub_yaml(
        {
            "name": "Hallway Hub",
            "board": "esp32dev",
            "fans": [fan_a],
            "reassign": True,
        },
        esphome_dir=str(tmp_path),
    )
    assert status3 == 200 and err3 is None
    assert res3["migrated_from"] == ["bedroom-ble-hub.yaml"]

    hubs_after = {h["filename"]: h for h in server.list_ble_hubs(str(tmp_path))}
    assert len(hubs_after["bedroom-ble-hub.yaml"]["fans"]) == 0
    assert len(hubs_after["hallway-hub.yaml"]["fans"]) == 1


def test_reassign_fan_from_cyd_strips_local_ble_package(tmp_path):
    cyd_yaml = tmp_path / "living_cyd.yaml"
    cyd_yaml.write_text(
        "packages:\n"
        "  device_base: !include lib/2432s028.yaml\n"
        "  tuya_ble_fan: !include lib/tuya_ble_fan.yaml\n"
        "tuya_ble_fan:\n"
        "  max_connections: 1\n"
        "  idle_disconnect_s: 0\n"
        "  fans:\n"
        "    - name: Living Fan\n"
        "      device_id: bf_cyd_migrate_0001\n"
        "      local_key: fedcba9876543210\n"
        "      fan_entity_id: fan.living_fan\n"
        "tile_ui:\n"
        "  screens: []\n",
        encoding="utf-8",
    )

    fan = {
        "name": "Living Fan",
        "device_id": "bf_cyd_migrate_0001",
        "local_key": "fedcba9876543210",
        "fan_entity_id": "fan.living_fan",
    }
    res, err, status = server.save_ble_hub_yaml(
        {
            "name": "Living Hub",
            "board": "esp32-c3-devkitm-1",
            "fans": [fan],
            "reassign": True,
        },
        esphome_dir=str(tmp_path),
    )
    assert status == 200 and err is None
    assert res["migrated_from"] == ["living_cyd.yaml"]

    cyd_text = cyd_yaml.read_text(encoding="utf-8")
    assert "tuya_ble_fan:" not in cyd_text
    assert "lib/tuya_ble_fan.yaml" not in cyd_text
    assert "tile_ui:" in cyd_text


def test_headless_hub_with_gree_ir_ac_roundtrip_and_tx_only(tmp_path):
    # 1. Gree IR AC hub (TX + RX + dump_ir debug)
    res, err, status = server.save_ble_hub_yaml(
        {
            "name": "Office Hub",
            "board": "seeed_xiao_esp32c3",
            "fans": [],
            "gree_ac": {
                "enabled": True,
                "name": "Office AC",
                "model": "yaa",
                "tx_pin": "GPIO4",
                "rx_pin": "GPIO5",
                "supports_cool": True,
                "supports_heat": True,
                "dump_ir": True,
            },
        },
        esphome_dir=str(tmp_path),
    )
    assert status == 200 and err is None
    assert res["filename"] == "office-hub.yaml"
    assert res["gree_ac"]["name"] == "Office AC"
    assert res["gree_ac"]["model"] == "yaa"
    assert res["gree_ac"]["dump_ir"] is True

    text = (tmp_path / "office-hub.yaml").read_text(encoding="utf-8")
    assert "relation: via" in text
    assert "platform: gree" in text
    assert "device_id: gree_ac_device" in text
    assert "name: None" in text
    assert "name: null" not in text
    assert "remote_transmitter:" in text
    assert "remote_receiver:" in text
    assert "receiver_id: ir_receiver" in text
    assert "- raw" in text
    assert "on_raw:" in text
    assert "gree_ir_debug_protocol" in text
    assert "IR Debug Protocol" in text

    # Round-trip via list_ble_hubs
    hubs = server.list_ble_hubs(str(tmp_path))
    assert len(hubs) == 1
    assert hubs[0]["gree_ac"] == {
        "enabled": True,
        "name": "Office AC",
        "model": "yaa",
        "tx_pin": "GPIO4",
        "rx_pin": "GPIO5",
        "supports_cool": True,
        "supports_heat": True,
        "dump_ir": True,
    }

    # 2. TX-only mode (blank rx_pin omits remote_receiver, receiver_id, and debug sensor)
    res2, err2, status2 = server.save_ble_hub_yaml(
        {
            "filename": "office-hub.yaml",
            "name": "Office Hub",
            "board": "seeed_xiao_esp32c3",
            "fans": [],
            "gree_ac": {
                "enabled": True,
                "name": "Office AC",
                "model": "generic",
                "tx_pin": "GPIO4",
                "rx_pin": "",
                "supports_cool": True,
                "supports_heat": False,
                "dump_ir": False,
            },
        },
        esphome_dir=str(tmp_path),
    )
    assert status2 == 200 and err2 is None
    text2 = (tmp_path / "office-hub.yaml").read_text(encoding="utf-8")
    assert "remote_transmitter:" in text2
    assert "remote_receiver:" not in text2
    assert "receiver_id:" not in text2
    assert "gree_ir_debug_protocol" not in text2
    hubs2 = server.list_ble_hubs(str(tmp_path))
    assert hubs2[0]["gree_ac"]["rx_pin"] == ""
    assert hubs2[0]["gree_ac"]["supports_heat"] is False


def test_headless_hub_with_shelly_ble_bridge_and_detached_switches(tmp_path):
    res, err, status = server.save_ble_hub_yaml(
        {
            "name": "Living Hub",
            "board": "seeed_xiao_esp32c3",
            "fans": [],
            "shellys": [
                {
                    "name": "Living Ceiling",
                    "mac_address": "AA:BB:CC:DD:EE:01",
                    "channel": 0,
                    "kind": "light",
                    "entity_id": "light.living_ceiling",
                },
                {
                    "name": "Living Blind",
                    "mac_address": "AA:BB:CC:DD:EE:02",
                    "channel": 0,
                    "kind": "cover",
                    "entity_id": "cover.living_blind",
                },
            ],
            "detached_switches": [
                {
                    "name": "Living Wall Switch",
                    "mac_address": "AA:BB:CC:DD:EE:03",
                    "input_channel": 1,
                    "target_fan_device_id": "bf_living_fan_001",
                    "target_light_entity_id": "light.living_fan_light",
                }
            ],
        },
        esphome_dir=str(tmp_path),
    )
    assert status == 200 and err is None
    text = (tmp_path / "living-hub.yaml").read_text(encoding="utf-8")
    assert "shelly_ble_bridge:" in text
    assert "aabbccddee01" in text
    assert "cover.living_blind" in text
    assert "detached_switches:" in text
    assert "bf_living_fan_001" in text

    hubs = server.list_ble_hubs(str(tmp_path))
    assert len(hubs) == 1
    assert len(hubs[0]["shellys"]) == 2
    assert hubs[0]["shellys"][0]["mac_address"] == "aabbccddee01"
    assert hubs[0]["shellys"][1]["kind"] == "cover"
    assert len(hubs[0]["detached_switches"]) == 1
    assert hubs[0]["detached_switches"][0]["input_channel"] == 1


def test_deploy_shelly_script_chunking_and_zigbee_warning(monkeypatch):
    calls = []

    def fake_rpc(ip, method, params=None, password=None, timeout=6):
        calls.append((ip, method, params))
        if method == "Shelly.GetDeviceInfo":
            return {"fw_id": "20260101-123456/2.2.1-g4-ZB", "app": "S1G4ZB", "model": "S4SW-001X16EU", "mac": "AABBCCDDEE01"}
        if method == "Script.List":
            return {"scripts": []}
        if method == "Script.Create":
            return {"id": 3}
        return {}

    monkeypatch.setattr(server, "_shelly_rpc_call", fake_rpc)
    script = "x" * 2500
    res = server.deploy_shelly_script_to_device("192.168.1.50", script)
    assert res["ok"] is True
    assert res["script_id"] == 3
    assert res["zigbee_warning"] is True

    put_calls = [p for (_, m, p) in calls if m == "Script.PutCode"]
    assert len(put_calls) == 3
    assert put_calls[0]["append"] is False
    assert put_calls[1]["append"] is True
    assert put_calls[2]["append"] is True
    assert "".join(p["code"] for p in put_calls) == script
    assert any(m == "Script.Start" and p == {"id": 3} for (_, m, p) in calls)

    # Verify shipped shelly/cyd_ble_backup.js is pure ASCII (Shelly 2.2.1 rejects \uXXXX)
    tpl = server._load_shelly_script_template()
    assert tpl is not None and tpl.isascii()
    assert "BLE.AdvBuilder.reset()" in tpl


def test_shelly_ha_discovery_template_renders_in_sandbox():
    from jinja2.sandbox import SandboxedEnvironment

    env = SandboxedEnvironment()
    devices_meta = {
        "dev_cover": {
            "name_by_user": "Office Blind",
            "name": "Shelly 2PM Gen4",
            "model": "S4SW-002P16EU",
            "connections": {("mac", "AA:BB:CC:DD:EE:01")},
            "configuration_url": "http://192.168.1.40",
            "area_id": "office",
            "area_name": "Office",
            "entities": ["cover.office_blind", "sensor.office_blind_power"],
        },
        "dev_detached": {
            "name_by_user": None,
            "name": "Office Wall Switch",
            "model": "S4SW-001X16EU",
            "connections": {("mac", "AA:BB:CC:DD:EE:02")},
            "configuration_url": "http://192.168.1.41",
            "area_id": "office",
            "area_name": "Office",
            "entities": ["event.office_wall_switch_input_0"],
        },
    }
    entity_to_dev = {
        eid: did for did, meta in devices_meta.items() for eid in meta["entities"]
    }

    rendered = env.from_string(server._SHELLY_HA_DISCOVERY_TEMPLATE).render(
        integration_entities=lambda domain: list(entity_to_dev.keys()) if domain == "shelly" else [],
        device_id=lambda eid: entity_to_dev.get(eid),
        device_attr=lambda did, attr: devices_meta[did].get(attr),
        device_entities=lambda did: devices_meta[did]["entities"],
        state_attr=lambda eid, attr: f"Friendly {eid}" if attr == "friendly_name" else None,
        area_id=lambda did: devices_meta[did].get("area_id"),
        area_name=lambda did: devices_meta[did].get("area_name"),
    )
    parsed = json.loads(rendered)
    assert len(parsed) == 2
    by_mac = {d["mac"]: d for d in parsed}
    assert by_mac["AA:BB:CC:DD:EE:01"]["name"] == "Office Blind"
    assert by_mac["AA:BB:CC:DD:EE:01"]["area_name"] == "Office"
    assert len(by_mac["AA:BB:CC:DD:EE:01"]["entities"]) == 1
    assert by_mac["AA:BB:CC:DD:EE:02"]["name"] == "Office Wall Switch"
    assert by_mac["AA:BB:CC:DD:EE:02"]["input_entities"] == ["event.office_wall_switch_input_0"]


def test_detect_detached_switch_suggestions_and_sync_hubs(tmp_path):
    autos_file = tmp_path / "automations.yaml"
    autos_file.write_text(
        "- alias: Bedroom Wall Switch Toggles Fan Light\n"
        "  triggers:\n"
        "    - trigger: state\n"
        "      entity_id: event.bedroom_wall_switch_input_1\n"
        "  actions:\n"
        "    - action: light.toggle\n"
        "      target:\n"
        "        entity_id: light.bedroom_fan_light\n",
        encoding="utf-8",
    )

    devices = [
        {
            "ha_device_id": "ha_dev_1",
            "name": "Bedroom Wall Switch",
            "mac_address": "aabbccddee01",
            "area_name": "Bedroom",
            "entities": [],
            "input_entities": ["event.bedroom_wall_switch_input_1"],
            "detached_channels": [1],
        },
        {
            "ha_device_id": "ha_dev_2",
            "name": "Office Wall Switch",
            "mac_address": "aabbccddee02",
            "area_name": "Office",
            "entities": [],
            "input_entities": ["event.office_wall_switch_input_0"],
            "detached_channels": [0],
        },
        {
            "ha_device_id": "ha_dev_3",
            "name": "Office Attached Light Switch",
            "mac_address": "aabbccddee03",
            "area_name": "Office",
            "entities": [{"entity_id": "switch.office_desk", "kind": "switch", "channel": 0}],
            "input_entities": ["event.office_attached_input_0"],
            "detached_channels": [],
        },
        {
            "ha_device_id": "ha_dev_4",
            "name": "Office Roller Blind",
            "mac_address": "aabbccddee04",
            "area_name": "Office",
            "entities": [{"entity_id": "cover.office_blind", "kind": "cover", "channel": 0}],
            "input_entities": [],
            "detached_channels": [0],
        },
    ]
    fans = [
        {
            "name": "Bedroom Fan",
            "device_id": "bf_bedroom_01",
            "fan_entity_id": "fan.bedroom_fan",
            "light_entity_id": "light.bedroom_fan_light",
        },
        {
            "name": "Office Fan",
            "device_id": "bf_office_01",
            "fan_entity_id": "fan.office_fan",
            "light_entity_id": "light.office_fan_light",
        },
    ]

    sug = server.detect_detached_switch_suggestions(devices, fans, automations_path=str(autos_file))
    assert len(sug) == 2
    by_mac = {s["mac_address"]: s for s in sug}
    # Tier 1: exact automation match with input_channel=1
    assert by_mac["aabbccddee01"]["source"] == "automation"
    assert by_mac["aabbccddee01"]["input_channel"] == 1
    assert by_mac["aabbccddee01"]["target_light_entity_id"] == "light.bedroom_fan_light"
    # Tier 2: same HA area fallback ONLY for verified detached switch
    assert by_mac["aabbccddee02"]["source"] == "area"
    assert by_mac["aabbccddee02"]["input_channel"] == 0
    assert by_mac["aabbccddee02"]["target_light_entity_id"] == "light.office_fan_light"
    # Attached switches and covers MUST NOT be suggested
    assert "aabbccddee03" not in by_mac
    assert "aabbccddee04" not in by_mac

    # Sync detached switches across two hubs and verify visible_shellys_sensor is emitted
    server.save_ble_hub_yaml(
        {"name": "Hub A", "board": "seeed_xiao_esp32c3", "fans": [fans[0] | {"local_key": "0123456789abcdef"}]},
        esphome_dir=str(tmp_path),
    )
    server.save_ble_hub_yaml(
        {"name": "Hub B", "board": "seeed_xiao_esp32c3", "fans": [fans[1] | {"local_key": "fedcba9876543210"}]},
        esphome_dir=str(tmp_path),
    )
    updated = server.sync_detached_switches_to_all_hubs(
        [
            {
                "name": "Bedroom Wall Switch",
                "mac_address": "aabbccddee01",
                "input_channel": 1,
                "target_fan_device_id": "bf_bedroom_01",
                "target_light_entity_id": "light.bedroom_fan_light",
            }
        ],
        esphome_dir=str(tmp_path),
    )
    assert set(updated) == {"hub-a.yaml", "hub-b.yaml"}
    for fname in ("hub-a.yaml", "hub-b.yaml"):
        txt = (tmp_path / fname).read_text(encoding="utf-8")
        assert "visible_shellys_sensor:" in txt
        assert "Visible Shellys" in txt
        assert "aabbccddee01" in txt


def test_probe_shelly_detached_channels_and_encode_blob(monkeypatch):
    responses = {
        "192.168.1.10": {
            "sys": {"device": {"profile": "switch"}},
            "input:0": {"type": "switch"},
            "input:1": {"type": "switch"},
            "switch:0": {"in_mode": "detached"},
            "switch:1": {"in_mode": "flip"},
        },
        "192.168.1.11": {
            "sys": {"device": {"profile": "cover"}},
            "input:0": {"type": "button"},
            "input:1": {"type": "button"},
        },
        "192.168.1.12": {
            "sys": {"device": {}},
            "input:0": {"type": "button"},
            "input:2": {"type": "switch"},
        },
        "192.168.1.13": {
            "sys": {"device": {"profile": "switch"}},
            "input:0": {"type": "button"},
            "switch:0": {"in_mode": "detached"},
        },
    }
    monkeypatch.setattr(server, "_shelly_rpc_call", lambda ip, method, timeout=1.2: responses[ip])
    assert server._probe_shelly_input_info("192.168.1.10") == ([0], [], [0, 1])
    assert server._probe_shelly_detached_channels("192.168.1.11") == []
    # input:0 is button mode (excluded), input:2 is switch mode (included)
    assert server._probe_shelly_input_info("192.168.1.12") == ([2], [0], [0, 2])
    # detached switch in button mode is excluded
    assert server._probe_shelly_input_info("192.168.1.13") == ([], [0], [0])

    blob = server._encode_detached_switches_blob([
        {
            "name": "Office | Switch",
            "mac_address": "AA:BB:CC:DD:EE:01",
            "input_channel": 1,
            "target_fan_device_id": "bf_office_01",
            "target_light_entity_id": "light.office_fan_light",
        }
    ])
    assert blob == "Office   Switch|aabbccddee01|1|bf_office_01|light.office_fan_light"



def test_collect_entity_to_cyds_map(tmp_path):
    (tmp_path / "office-cyd.yaml").write_text(
        "substitutions:\n"
        "  device_name: office-cyd\n"
        "tile_ui:\n"
        "  screens:\n"
        "    - id: main\n"
        "      tiles:\n"
        "        - ha_action:\n"
        "            entities: ['cover.o2|position', 'switch.l_mmd']\n",
        encoding="utf-8",
    )
    (tmp_path / "living-cyd.yaml").write_text(
        "substitutions:\n"
        "  device_name: living-cyd\n"
        "tile_ui:\n"
        "  screens:\n"
        "    - id: main\n"
        "      tiles:\n"
        "        - ha_action:\n"
        "            entities: ['cover.o2']\n",
        encoding="utf-8",
    )
    mapping = server._collect_entity_to_cyds_map(str(tmp_path))
    assert mapping["cover.o2"] == ["living-cyd", "office-cyd"]
    assert mapping["switch.l_mmd"] == ["office-cyd"]



