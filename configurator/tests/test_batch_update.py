import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import types

CONFIGURATOR_DIR = Path(__file__).resolve().parents[1]
if str(CONFIGURATOR_DIR) not in sys.path:
    sys.path.insert(0, str(CONFIGURATOR_DIR))

if 'aioesphomeapi' not in sys.modules:
    _stub_api = types.ModuleType('aioesphomeapi')
    _stub_api.APIClient = object
    sys.modules['aioesphomeapi'] = _stub_api

if 'api_proxy' not in sys.modules:
    _stub_proxy = types.ModuleType('api_proxy')
    _stub_proxy.run_proxy_thread = lambda *a, **kw: None
    sys.modules['api_proxy'] = _stub_proxy

import server


class BatchUpdateTests(unittest.TestCase):
    def test_parse_device_yaml_detects_cyd_and_ota(self):
        with tempfile.TemporaryDirectory() as tmp:
            cyd_path = os.path.join(tmp, 'living_cyd.yaml')
            with open(cyd_path, 'w') as f:
                f.write("""
substitutions:
  device_name: living_cyd
  friendly_name: Living CYD
packages:
  device_base: !include lib/3248s035_base.yaml
  lib: !include lib/lib.yaml
esphome:
  name: $device_name
ota:
  - platform: esphome
wifi:
  use_address: 192.168.1.20
tile_ui:
  screens: []
""")
            meta = server._parse_device_yaml(cyd_path)
            self.assertIsNotNone(meta)
            self.assertTrue(meta['is_cyd'])
            self.assertTrue(meta['has_ota'])
            self.assertEqual(meta['screen_type'], '3248s035')
            self.assertEqual(meta['address'], '192.168.1.20')

            non_cyd_path = os.path.join(tmp, 'smart_plug.yaml')
            with open(non_cyd_path, 'w') as f:
                f.write("""
esphome:
  name: smart_plug
  friendly_name: Smart Plug
ota:
  - platform: esphome
""")
            non_cyd = server._parse_device_yaml(non_cyd_path)
            self.assertIsNotNone(non_cyd)
            self.assertFalse(non_cyd['is_cyd'])
            self.assertTrue(non_cyd['has_ota'])

            no_ota_cyd = os.path.join(tmp, 'usb_only_cyd.yaml')
            with open(no_ota_cyd, 'w') as f:
                f.write("""
esphome:
  name: usb_cyd
packages:
  device_base: !include lib/2432s028_base.yaml
tile_ui:
  screens: []
""")
            no_ota = server._parse_device_yaml(no_ota_cyd)
            self.assertIsNotNone(no_ota)
            self.assertTrue(no_ota['is_cyd'])
            self.assertFalse(no_ota['has_ota'])

    def test_classify_batch_device(self):
        st, reason = server._classify_batch_device({'is_cyd': False, 'has_ota': True}, online=True)
        self.assertEqual(st, 'skipped')
        self.assertIn('CYD', reason)

        st, reason = server._classify_batch_device({'is_cyd': True, 'has_ota': False}, online=True)
        self.assertEqual(st, 'skipped')
        self.assertIn('OTA', reason)

        st, reason = server._classify_batch_device({'is_cyd': True, 'has_ota': True}, online=False)
        self.assertEqual(st, 'skipped')
        self.assertIn('offline', reason.lower())

        st, _ = server._classify_batch_device({'is_cyd': True, 'has_ota': True}, online=True)
        self.assertEqual(st, 'pending')

    def test_batch_update_endpoints_full_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'cyd_online.yaml'), 'w') as f:
                f.write("""
esphome:
  name: cyd_online
  friendly_name: CYD Online
packages:
  device_base: !include lib/3248s035_base.yaml
ota:
  - platform: esphome
tile_ui:
  screens: []
""")
            with open(os.path.join(tmp, 'cyd_offline.yaml'), 'w') as f:
                f.write("""
esphome:
  name: cyd_offline
  friendly_name: CYD Offline
packages:
  device_base: !include lib/2432s028_base.yaml
ota:
  - platform: esphome
tile_ui:
  screens: []
""")
            with open(os.path.join(tmp, 'plug.yaml'), 'w') as f:
                f.write("""
esphome:
  name: plug
  friendly_name: Desk Plug
ota:
  - platform: esphome
""")
            with open(os.path.join(tmp, 'office_hub.yaml'), 'w') as f:
                f.write("""
substitutions:
  device_name: office-hub
  friendly_name: Office Hub
packages:
  hub_base: !include lib/headless_hub_base.yaml
espnow_fan_bridge:
  role: hub
""")

            class FakeProc:
                def __init__(self, rc=0, output="Compiling...\nSuccessfully uploaded program.\n"):
                    self.returncode = rc
                    self.stdout = io.StringIO(output)
                def poll(self):
                    return self.returncode
                def wait(self, timeout=None):
                    return self.returncode
                def terminate(self):
                    pass
                def kill(self):
                    pass

            def fake_check_online(dev):
                dev['online'] = dev['address'] in ('cyd_online.local', 'office-hub.local')
                return dev

            server._esphome_mod.batch_update_state = None
            client = server.app.test_client()

            with mock.patch.object(server._esphome_mod, 'BASE_DIR', tmp), \
                 mock.patch.object(server._esphome_mod, '_check_device_online', side_effect=fake_check_online), \
                 mock.patch.object(server._esphome_mod.subprocess, 'Popen', return_value=FakeProc()) as popen_mock:
                res = client.post('/api/esphome/batch_update/start')
                self.assertEqual(res.status_code, 200)

                # Wait for worker thread to complete
                deadline = time.time() + 5
                data = None
                while time.time() < deadline:
                    st_res = client.get('/api/esphome/batch_update/status?include_logs=cyd_online.yaml')
                    self.assertEqual(st_res.status_code, 200)
                    data = st_res.get_json()
                    if data['phase'] in ('completed', 'cancelled'):
                        break
                    time.sleep(0.05)

                self.assertEqual(data['phase'], 'completed')
                self.assertEqual(data['summary']['total'], 4)
                self.assertEqual(data['summary']['updated'], 2)
                self.assertEqual(data['summary']['skipped'], 2)
                self.assertEqual(data['summary']['failed'], 0)

                by_file = {d['filename']: d for d in data['devices']}
                self.assertEqual(by_file['cyd_online.yaml']['status'], 'updated')
                self.assertIn('Successfully uploaded program.', by_file['cyd_online.yaml']['logs'])
                self.assertEqual(by_file['office_hub.yaml']['status'], 'updated')
                self.assertTrue(by_file['office_hub.yaml']['is_headless_hub'])
                self.assertEqual(by_file['cyd_offline.yaml']['status'], 'skipped')
                self.assertIn('offline', by_file['cyd_offline.yaml']['reason'].lower())
                self.assertEqual(by_file['plug.yaml']['status'], 'skipped')
                self.assertIn('CYD', by_file['plug.yaml']['reason'])
                self.assertEqual(popen_mock.call_count, 2)


if __name__ == '__main__':
    unittest.main()
