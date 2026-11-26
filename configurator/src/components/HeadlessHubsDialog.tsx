import React, { useState, useEffect } from 'react';
import {
  X,
  Radio,
  Plus,
  Trash2,
  Cpu,
  Check,
  AlertTriangle,
  Download,
  Edit3,
  Loader2,
  ArrowRightLeft,
  Wind,
} from 'lucide-react';
import { BleFanConfig, GreeAcConfig, HeadlessHubConfig, TuyaBleCandidate } from '../types';
import { apiFetch } from '../utils/api';
import { deriveDefaultBleEntityIds, slugifyEspHomeId } from '../utils/bleFanUtils';

const BOARD_PRESETS = [
  { value: 'seeed_xiao_esp32c3', label: 'Seeed XIAO ESP32-C3 (seeed_xiao_esp32c3)' },
  { value: 'esp32dev', label: 'ESP32 DevKit / WROOM (esp32dev)' },
  { value: 'esp32-c3-devkitm-1', label: 'ESP32-C3 DevKitM-1 (esp32-c3-devkitm-1)' },
  { value: 'esp32-s3-devkitc-1', label: 'ESP32-S3 DevKitC-1 (esp32-s3-devkitc-1)' },
  { value: 'seeed_xiao_esp32s3', label: 'Seeed XIAO ESP32-S3 (seeed_xiao_esp32s3)' },
  { value: 'esp32-c6-devkitc-1', label: 'ESP32-C6 DevKitC-1 (esp32-c6-devkitc-1)' },
];

const GREE_AC_MODELS = [
  { value: 'generic', label: 'Generic Gree (default)' },
  { value: 'yaa', label: 'YAA (YAA1FB / YAA1FBF)' },
  { value: 'yac', label: 'YAC (YAC1FB / YAC1FBF)' },
  { value: 'yac1fb9', label: 'YAC1FB9' },
  { value: 'yan', label: 'YAN (YAN1F1)' },
  { value: 'yag', label: 'YAG (YAG1FB)' },
  { value: 'yx1ff', label: 'YX1FF' },
  { value: 'ybofb', label: 'YBOFB' },
];

const DEFAULT_GREE_AC: GreeAcConfig = {
  enabled: false,
  name: '',
  model: 'generic',
  tx_pin: 'GPIO4',
  rx_pin: 'GPIO5',
  supports_cool: true,
  supports_heat: true,
  dump_ir: false,
};

interface ConflictItem {
  device_id: string;
  fan_name: string;
  fan_entity_id: string;
  host_file: string;
}

interface HeadlessHubsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  hubs: HeadlessHubConfig[];
  networkKey: string;
  tuyaBleCandidates: TuyaBleCandidate[];
  bleFanHosts: Record<string, string[]>;
  onHubsChanged: () => void;
  onInstallHub?: (filename: string) => void;
}

export const HeadlessHubsDialog: React.FC<HeadlessHubsDialogProps> = ({
  isOpen,
  onClose,
  hubs,
  networkKey,
  tuyaBleCandidates,
  bleFanHosts,
  onHubsChanged,
  onInstallHub,
}) => {
  const [editingFilename, setEditingFilename] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const [name, setName] = useState('');
  const [friendlyName, setFriendlyName] = useState('');
  const [board, setBoard] = useState('seeed_xiao_esp32c3');
  const [customBoard, setCustomBoard] = useState('');
  const [fallbackChannel, setFallbackChannel] = useState(1);
  const [hubNetworkKey, setHubNetworkKey] = useState(networkKey || 'cyd_espnow_default');
  const [selectedFanIds, setSelectedFanIds] = useState<Set<string>>(new Set());
  const [greeAc, setGreeAc] = useState<GreeAcConfig>({ ...DEFAULT_GREE_AC });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);

  useEffect(() => {
    if (!isOpen) {
      setIsCreating(false);
      setEditingFilename(null);
      setError(null);
      setConflicts([]);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const isPresetBoard = BOARD_PRESETS.some(p => p.value === board);

  const startCreate = () => {
    setIsCreating(true);
    setEditingFilename(null);
    setName('');
    setFriendlyName('');
    setBoard('seeed_xiao_esp32c3');
    setCustomBoard('');
    setFallbackChannel(1);
    setHubNetworkKey(networkKey || 'cyd_espnow_default');
    setSelectedFanIds(new Set());
    setGreeAc({ ...DEFAULT_GREE_AC });
    setError(null);
    setConflicts([]);
  };

  const startEdit = (hub: HeadlessHubConfig) => {
    setIsCreating(false);
    setEditingFilename(hub.filename);
    setName(hub.name);
    setFriendlyName(hub.friendly_name || hub.name);
    const matchesPreset = BOARD_PRESETS.some(p => p.value === hub.board);
    setBoard(matchesPreset ? hub.board : '__custom__');
    setCustomBoard(matchesPreset ? '' : hub.board);
    setFallbackChannel(hub.fallback_channel || 1);
    setHubNetworkKey(hub.network_key || networkKey || 'cyd_espnow_default');
    setSelectedFanIds(new Set((hub.fans || []).map(f => f.device_id)));
    setGreeAc(
      hub.gree_ac && hub.gree_ac.enabled
        ? { ...DEFAULT_GREE_AC, ...hub.gree_ac, enabled: true }
        : { ...DEFAULT_GREE_AC }
    );
    setError(null);
    setConflicts([]);
  };

  const cancelEdit = () => {
    setIsCreating(false);
    setEditingFilename(null);
    setError(null);
    setConflicts([]);
  };

  const toggleFan = (deviceId: string) => {
    setSelectedFanIds(prev => {
      const next = new Set(prev);
      if (next.has(deviceId)) next.delete(deviceId);
      else next.add(deviceId);
      return next;
    });
    setConflicts([]);
    setError(null);
  };

  const buildSelectedFans = (): BleFanConfig[] => {
    const existingHub = editingFilename ? hubs.find(h => h.filename === editingFilename) : undefined;
    const byId = new Map<string, BleFanConfig>();
    for (const c of tuyaBleCandidates) {
      const defaults = deriveDefaultBleEntityIds(c.name || c.device_id);
      byId.set(c.device_id, {
        name: c.name,
        device_id: c.device_id,
        local_key: c.local_key,
        product_id: c.product_id || '',
        mac_address: c.mac_address || '',
        uuid: c.uuid || '',
        fan_entity_id: c.fan_entity_id || defaults.fan_entity_id,
        light_entity_id: c.light_entity_id || defaults.light_entity_id,
        expose_to_ha: true,
      });
    }
    if (existingHub) {
      for (const f of existingHub.fans || []) {
        if (!byId.has(f.device_id)) byId.set(f.device_id, f);
      }
    }
    const out: BleFanConfig[] = [];
    for (const id of selectedFanIds) {
      const item = byId.get(id);
      if (item) out.push(item);
    }
    return out;
  };

  const handleSave = async (reassign: boolean = false) => {
    const effectiveBoard = board === '__custom__' ? customBoard.trim() : board;
    if (!name.trim()) {
      setError('Hub name is required.');
      return;
    }
    if (!effectiveBoard) {
      setError('Board identifier is required.');
      return;
    }
    if (greeAc.enabled && !greeAc.name.trim()) {
      setError('Gree AC name is required when Gree IR AC control is enabled.');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const res = await apiFetch('/ble_hubs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: editingFilename || undefined,
          name: name.trim(),
          friendly_name: friendlyName.trim() || name.trim(),
          board: effectiveBoard,
          fallback_channel: fallbackChannel,
          network_key: hubNetworkKey.trim() || 'cyd_espnow_default',
          fans: buildSelectedFans(),
          gree_ac: greeAc.enabled ? { ...greeAc, name: greeAc.name.trim() } : null,
          reassign,
        }),
      });
      const data = await res.json();
      if (res.status === 409 && Array.isArray(data.conflicts)) {
        setConflicts(data.conflicts);
        setError(data.error || 'One or more fans are already hosted on another device.');
        return;
      }
      if (!res.ok) {
        setError(data.error || 'Failed to save headless hub.');
        return;
      }
      setIsCreating(false);
      setEditingFilename(null);
      setConflicts([]);
      onHubsChanged();
    } catch (e: any) {
      setError(e?.message || 'Network error saving hub.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (hub: HeadlessHubConfig) => {
    if (!confirm(`Delete headless hub "${hub.friendly_name}" (${hub.filename})?`)) return;
    try {
      const res = await apiFetch(`/ble_hubs/${encodeURIComponent(hub.filename)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        onHubsChanged();
      } else {
        const data = await res.json();
        alert(data.error || 'Failed to delete hub.');
      }
    } catch {
      alert('Failed to delete hub.');
    }
  };

  const showEditor = isCreating || editingFilename !== null;

  return (
    <div className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-slate-50">
          <div className="flex items-center gap-2.5">
            <Radio className="text-indigo-600" size={20} />
            <div>
              <h2 className="text-base font-bold text-slate-800">Headless BLE Fan Hubs (ESP-NOW)</h2>
              <p className="text-xs text-slate-500">
                Dedicated ESP32 hubs handle BLE reception &amp; HA entities; CYDs talk to them directly over ESP-NOW.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {networkKey && (
            <div className="text-[11px] bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2 flex items-center justify-between text-indigo-800">
              <span>
                Shared ESP-NOW Network Key (auto-synced to all Hubs &amp; CYDs):{' '}
                <code className="font-mono font-bold bg-white/80 px-1.5 py-0.5 rounded">{networkKey}</code>
              </span>
            </div>
          )}

          {!showEditor ? (
            <>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500">
                  Configured Hubs ({hubs.length})
                </span>
                <button
                  onClick={startCreate}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                >
                  <Plus size={14} /> New Headless Hub
                </button>
              </div>

              {hubs.length === 0 ? (
                <div className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
                  <Cpu size={28} className="mx-auto mb-2 text-slate-300" />
                  <p className="font-medium text-slate-700">No headless hubs configured yet</p>
                  <p className="text-xs mt-1">
                    Create a hub for any ESP32 / XIAO ESP32-C3 board, assign your Tuya BLE fans, and flash it.
                  </p>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {hubs.map(hub => (
                    <div
                      key={hub.filename}
                      className="border rounded-lg p-3.5 bg-slate-50/70 flex flex-col gap-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <div className="font-semibold text-sm text-slate-800 flex items-center gap-2">
                            {hub.friendly_name || hub.name}
                            <span className="text-[11px] font-mono bg-slate-200/80 text-slate-700 px-1.5 py-0.5 rounded">
                              {hub.board}
                            </span>
                            <span className="text-[11px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">
                              fallback ch {hub.fallback_channel}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-500 font-mono mt-0.5">{hub.filename}</div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {onInstallHub && (
                            <button
                              onClick={() => onInstallHub(hub.filename)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-emerald-600 text-white rounded-md hover:bg-emerald-700"
                              title="Compile & Flash this Hub"
                            >
                              <Download size={12} /> Install
                            </button>
                          )}
                          <button
                            onClick={() => startEdit(hub)}
                            className="p-1.5 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-md"
                            title="Edit Hub"
                          >
                            <Edit3 size={14} />
                          </button>
                          <button
                            onClick={() => handleDelete(hub)}
                            className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md"
                            title="Delete Hub"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {hub.gree_ac && hub.gree_ac.enabled && (
                          <span className="inline-flex items-center gap-1 text-[11px] bg-cyan-50 border border-cyan-200 px-2 py-0.5 rounded-full text-cyan-800 font-medium">
                            <Wind size={11} />
                            AC: {hub.gree_ac.name} ({hub.gree_ac.model}, TX {hub.gree_ac.tx_pin}
                            {hub.gree_ac.rx_pin ? ` / RX ${hub.gree_ac.rx_pin}` : ''})
                          </span>
                        )}
                        {hub.fans.length === 0 && !(hub.gree_ac && hub.gree_ac.enabled) ? (
                          <span className="text-[11px] text-slate-400 italic">No fans or AC assigned yet</span>
                        ) : (
                          hub.fans.map(f => (
                            <span
                              key={f.device_id}
                              className="text-[11px] bg-white border border-slate-200 px-2 py-0.5 rounded-full text-slate-700"
                            >
                              {f.name || f.fan_entity_id}
                            </span>
                          ))
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">Hub Name (slug)</label>
                  <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    disabled={editingFilename !== null}
                    placeholder="e.g. office-ble-hub"
                    className="w-full px-2.5 py-1.5 text-sm border rounded-md disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">Friendly Name</label>
                  <input
                    type="text"
                    value={friendlyName}
                    onChange={e => setFriendlyName(e.target.value)}
                    placeholder="e.g. Office BLE Hub"
                    className="w-full px-2.5 py-1.5 text-sm border rounded-md"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-600 mb-1">ESP32 Board</label>
                  <select
                    value={isPresetBoard ? board : '__custom__'}
                    onChange={e => setBoard(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-sm border rounded-md bg-white"
                  >
                    {BOARD_PRESETS.map(p => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                    <option value="__custom__">Custom PlatformIO board ID...</option>
                  </select>
                  {board === '__custom__' && (
                    <input
                      type="text"
                      value={customBoard}
                      onChange={e => setCustomBoard(e.target.value)}
                      placeholder="e.g. esp32-c3-supermini"
                      className="w-full mt-1.5 px-2.5 py-1.5 text-sm border rounded-md font-mono"
                    />
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    Offline Fallback Ch
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={13}
                    value={fallbackChannel}
                    onChange={e => setFallbackChannel(Math.max(1, Math.min(13, Number(e.target.value) || 1)))}
                    className="w-full px-2.5 py-1.5 text-sm border rounded-md"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  ESP-NOW Network Key <span className="font-normal text-slate-400">(must match CYD; default works across machines)</span>
                </label>
                <input
                  type="text"
                  value={hubNetworkKey}
                  onChange={e => setHubNetworkKey(e.target.value)}
                  placeholder="cyd_espnow_default"
                  className="w-full px-2.5 py-1.5 text-sm font-mono border rounded-md"
                />
              </div>

              {/* Gree IR AC Control */}
              <div className="border border-cyan-200 bg-cyan-50/40 rounded-lg p-3 space-y-3">
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="flex items-center gap-2 text-xs font-bold text-cyan-900">
                    <Wind size={14} className="text-cyan-600" />
                    Gree IR AC Control (TX + RX state sync)
                  </span>
                  <input
                    type="checkbox"
                    checked={greeAc.enabled}
                    onChange={e =>
                      setGreeAc(prev => ({
                        ...prev,
                        enabled: e.target.checked,
                        name: prev.name || (friendlyName ? `${friendlyName.replace(/\s*hub\s*/i, ' ').trim()} AC` : ''),
                      }))
                    }
                    className="rounded text-cyan-600"
                  />
                </label>

                {greeAc.enabled && (
                  <div className="space-y-2.5 pt-2 border-t border-cyan-200/70">
                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                          AC Name
                        </label>
                        <input
                          type="text"
                          value={greeAc.name}
                          onChange={e => setGreeAc(prev => ({ ...prev, name: e.target.value }))}
                          placeholder="e.g. Office AC"
                          className="w-full px-2 py-1.5 text-xs border rounded-md bg-white"
                        />
                        {greeAc.name.trim() && (
                          <div className="text-[10px] text-cyan-700 font-mono mt-0.5">
                            HA entity: climate.{slugifyEspHomeId(greeAc.name)}
                          </div>
                        )}
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                          Gree Protocol Model
                        </label>
                        <select
                          value={greeAc.model}
                          onChange={e => setGreeAc(prev => ({ ...prev, model: e.target.value }))}
                          className="w-full px-2 py-1.5 text-xs border rounded-md bg-white"
                        >
                          {GREE_AC_MODELS.map(m => (
                            <option key={m.value} value={m.value}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                          IR TX Pin <span className="font-normal text-slate-400">(XIAO D2 = GPIO4)</span>
                        </label>
                        <input
                          type="text"
                          value={greeAc.tx_pin}
                          onChange={e => setGreeAc(prev => ({ ...prev, tx_pin: e.target.value }))}
                          placeholder="GPIO4"
                          className="w-full px-2 py-1.5 text-xs font-mono border rounded-md bg-white"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                          IR RX Pin <span className="font-normal text-slate-400">(XIAO D3 = GPIO5; blank = TX-only)</span>
                        </label>
                        <input
                          type="text"
                          value={greeAc.rx_pin}
                          onChange={e => setGreeAc(prev => ({ ...prev, rx_pin: e.target.value }))}
                          placeholder="GPIO5"
                          className="w-full px-2 py-1.5 text-xs font-mono border rounded-md bg-white"
                        />
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-700 pt-0.5">
                      <label className="inline-flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={greeAc.supports_cool}
                          onChange={e => setGreeAc(prev => ({ ...prev, supports_cool: e.target.checked }))}
                          className="rounded text-cyan-600"
                        />
                        Cool
                      </label>
                      <label className="inline-flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={greeAc.supports_heat}
                          onChange={e => setGreeAc(prev => ({ ...prev, supports_heat: e.target.checked }))}
                          className="rounded text-cyan-600"
                        />
                        Heat
                      </label>
                      <label
                        className="inline-flex items-center gap-1.5 cursor-pointer text-slate-600"
                        title="Logs decoded Gree IR frames to esphome logs when you press buttons on your physical remote"
                      >
                        <input
                          type="checkbox"
                          checked={greeAc.dump_ir}
                          onChange={e => setGreeAc(prev => ({ ...prev, dump_ir: e.target.checked }))}
                          className="rounded text-cyan-600"
                        />
                        Log received IR codes (debug)
                      </label>
                    </div>
                  </div>
                )}
              </div>

              {/* Fan assignment checklist */}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  Assigned BLE Fans (1 host per fan enforced)
                </label>
                {tuyaBleCandidates.length === 0 ? (
                  <p className="text-xs text-slate-400 italic">
                    No BLE fans in vault yet. Pair a fan first or load a device with BLE fans.
                  </p>
                ) : (
                  <div className="border rounded-lg divide-y max-h-52 overflow-y-auto">
                    {tuyaBleCandidates.map(fan => {
                      const checked = selectedFanIds.has(fan.device_id);
                      const hosts = (bleFanHosts[fan.device_id] || []).filter(
                        h => !editingFilename || h.toLowerCase() !== editingFilename.toLowerCase()
                      );
                      return (
                        <label
                          key={fan.device_id}
                          className="flex items-center justify-between px-3 py-2 hover:bg-slate-50 cursor-pointer text-xs"
                        >
                          <div className="flex items-center gap-2.5">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleFan(fan.device_id)}
                              className="rounded text-indigo-600"
                            />
                            <div>
                              <div className="font-medium text-slate-800">{fan.name}</div>
                              <div className="text-[10px] text-slate-400 font-mono">
                                {fan.fan_entity_id || fan.device_id}
                              </div>
                            </div>
                          </div>
                          {hosts.length > 0 && (
                            <span className="text-[10px] bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">
                              Hosted on {hosts.join(', ')}
                            </span>
                          )}
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              {error && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900 space-y-2">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={15} className="text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold">{error}</div>
                      {conflicts.length > 0 && (
                        <ul className="mt-1 list-disc list-inside text-[11px]">
                          {conflicts.map((c, idx) => (
                            <li key={idx}>
                              <strong>{c.fan_name}</strong> is currently hosted on <code>{c.host_file}</code>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                  {conflicts.length > 0 && (
                    <button
                      onClick={() => handleSave(true)}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-amber-600 text-white rounded-md hover:bg-amber-700"
                    >
                      <ArrowRightLeft size={13} /> Move Fan(s) to This Hub
                    </button>
                  )}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t">
                <button
                  onClick={cancelEdit}
                  className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-md"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleSave(false)}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                  Save Hub YAML
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
