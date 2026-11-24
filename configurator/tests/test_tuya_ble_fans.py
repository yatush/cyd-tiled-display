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
