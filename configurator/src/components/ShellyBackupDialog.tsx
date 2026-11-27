import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
  X,
  Zap,
} from 'lucide-react';
import {
  Config,
  DetachedSwitchBinding,
  DetachedSwitchSuggestion,
  DiscoveredShellyDevice,
  HeadlessHubConfig,
} from '../types';
import { apiFetch } from '../utils/api';
import { collectReferencedEntityIds } from '../utils/bleFanUtils';

interface ShellyBackupDialogProps {
  isOpen: boolean;
  onClose: () => void;
  config: Config;
  hubs: HeadlessHubConfig[];
  networkKey: string;
  onSynced?: (devices: DiscoveredShellyDevice[]) => void;
}

export const ShellyBackupDialog: React.FC<ShellyBackupDialogProps> = ({
  isOpen,
  onClose,
  config,
  hubs,
  networkKey,
  onSynced,
}) => {
  const [devices, setDevices] = useState<DiscoveredShellyDevice[]>([]);
  const [suggestions, setSuggestions] = useState<DetachedSwitchSuggestion[]>([]);
  const [detachedSwitches, setDetachedSwitches] = useState<DetachedSwitchBinding[]>([]);
  const [selectedMacs, setSelectedMacs] = useState<Set<string>>(new Set());
  const [rpcPassword, setRpcPassword] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [isDeploying, setIsDeploying] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const syncStatusRef = useRef<HTMLDivElement | null>(null);
  const [deployResults, setDeployResults] = useState<any[]>([]);
  const [deployProgress, setDeployProgress] = useState<{
    done: number;
    total: number;
    currentName: string;
    currentIp: string;
    okCount: number;
    failCount: number;
    cancelled: boolean;
  } | null>(null);
  const deployCancelRef = useRef(false);

  const cydReferencedEntities = useMemo(() => collectReferencedEntityIds(config), [config]);

  const allHubFans = useMemo(() => {
    const out: Array<{
      name: string;
      device_id: string;
      light_entity_id: string;
      hub_name: string;
    }> = [];
    for (const hub of hubs) {
      for (const f of hub.fans || []) {
        out.push({
          name: f.name || f.device_id,
          device_id: f.device_id,
          light_entity_id: f.light_entity_id || '',
          hub_name: hub.name,
        });
      }
    }
    return out;
  }, [hubs]);

  const loadFromHa = async () => {
    setIsLoading(true);
    setError(null);
    setSyncMessage(null);
    setSyncError(null);
    try {
      const res = await apiFetch('/shelly/devices');
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || `Discovery failed (${res.status})`);
        return;
      }
      if (data.error && (!data.devices || data.devices.length === 0)) {
        setError(data.error);
      }
      const found: DiscoveredShellyDevice[] = Array.isArray(data.devices) ? data.devices : [];
      const dsList: DetachedSwitchBinding[] = Array.isArray(data.detached_switches)
        ? data.detached_switches
        : [];
      setDevices(found);
      setSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []);
      setDetachedSwitches(dsList);
      const dsMacs = new Set(dsList.map(d => d.mac_address));
      const usedWithIp = found.filter(
        d =>
          !!d.ip &&
          ((d.used_by_cyds && d.used_by_cyds.length > 0) ||
            dsMacs.has(d.mac_address) ||
            (d.entities || []).some(e => cydReferencedEntities.has(e.entity_id)))
      );
      setSelectedMacs(
        new Set(
          (usedWithIp.length > 0 ? usedWithIp : found.filter(d => !!d.ip)).map(d => d.mac_address)
        )
      );
      onSynced?.(found);
    } catch (e: any) {
      setError(e?.message || 'Failed to discover Shelly devices from Home Assistant');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadFromHa();
    }
  }, [isOpen]);

  const unacceptedSuggestions = useMemo(() => {
    return suggestions.filter(
      sug =>
        !detachedSwitches.some(
          ds =>
            ds.mac_address === sug.mac_address &&
            ds.input_channel === sug.input_channel &&
            ds.target_light_entity_id === sug.target_light_entity_id
        )
    );
  }, [suggestions, detachedSwitches]);

  const toggleSelectMac = (mac: string) => {
    setSelectedMacs(prev => {
      const next = new Set(prev);
      if (next.has(mac)) next.delete(mac);
      else next.add(mac);
      return next;
    });
  };

  const handleDeployScript = async () => {
    const targets = devices
      .filter(d => selectedMacs.has(d.mac_address) && d.ip)
      .map(d => ({ ip: d.ip, name: d.name, mac_address: d.mac_address }));
    if (targets.length === 0) {
      setError('Select at least one Shelly device with an IP address to deploy the script.');
      return;
    }
    deployCancelRef.current = false;
    setIsDeploying(true);
    setError(null);
    setDeployResults([]);
    let okCount = 0;
    let failCount = 0;

    try {
      for (let i = 0; i < targets.length; i++) {
        if (deployCancelRef.current) {
          setDeployProgress(prev => (prev ? { ...prev, cancelled: true, currentName: '', currentIp: '' } : null));
          break;
        }
        const target = targets[i];
        setDeployProgress({
          done: i,
          total: targets.length,
          currentName: target.name || target.ip,
          currentIp: target.ip,
          okCount,
          failCount,
          cancelled: false,
        });
        try {
          const res = await apiFetch('/shelly/deploy_script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              targets: [target],
              network_key: networkKey || 'cyd_espnow_default',
              password: rpcPassword || undefined,
            }),
          });
          const data = await res.json();
          const item =
            res.ok && Array.isArray(data.results) && data.results[0]
              ? data.results[0]
              : {
                  ip: target.ip,
                  name: target.name,
                  ok: false,
                  error: data.error || `HTTP ${res.status}`,
                };
          if (item.ok) okCount += 1;
          else failCount += 1;
          setDeployResults(prev => [...prev, item]);
        } catch (e: any) {
          failCount += 1;
          setDeployResults(prev => [
            ...prev,
            {
              ip: target.ip,
              name: target.name,
              ok: false,
              error: e?.message || 'Request failed',
            },
          ]);
        }
        setDeployProgress({
          done: i + 1,
          total: targets.length,
          currentName: i + 1 < targets.length ? targets[i + 1].name || targets[i + 1].ip : '',
          currentIp: i + 1 < targets.length ? targets[i + 1].ip : '',
          okCount,
          failCount,
          cancelled: false,
        });
      }
    } finally {
      setIsDeploying(false);
    }
  };

  const handleAcceptSuggestion = (sug: DetachedSwitchSuggestion) => {
    setDetachedSwitches(prev => [
      ...prev,
      {
        name: sug.name,
        mac_address: sug.mac_address,
        input_channel: sug.input_channel,
        target_fan_device_id: sug.target_fan_device_id,
        target_light_entity_id: sug.target_light_entity_id,
      },
    ]);
  };

  const handleAddEmptyBinding = () => {
    const firstDev = devices[0];
    const firstFan = allHubFans[0];
    setDetachedSwitches(prev => [
      ...prev,
      {
        name: firstDev?.name || '',
        mac_address: firstDev?.mac_address || '',
        input_channel: 0,
        target_fan_device_id: firstFan?.device_id || '',
        target_light_entity_id: firstFan?.light_entity_id || '',
      },
    ]);
  };

  const handleSyncHubs = async () => {
    setIsSyncing(true);
    setSyncError(null);
    setSyncMessage(null);
    try {
      const res = await apiFetch('/shelly/sync_detached_switches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detached_switches: detachedSwitches }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setSyncError(data.error || 'Failed to sync detached switches to hubs');
      } else {
        const updatedHubs: string[] = Array.isArray(data.updated_hubs) ? data.updated_hubs : [];
        const liveHubs: string[] = Array.isArray(data.live_pushed_hubs) ? data.live_pushed_hubs : [];
        if (liveHubs.length > 0 && liveHubs.length >= updatedHubs.length) {
          setSyncMessage(
            `Applied live to ${liveHubs.length} online hub${liveHubs.length === 1 ? '' : 's'} (${liveHubs.join(', ')}) and saved to YAML — no re-flash needed!`
          );
        } else if (liveHubs.length > 0) {
          setSyncMessage(
            `Applied live to ${liveHubs.join(', ')}. Saved YAML for ${updatedHubs.length} hub${updatedHubs.length === 1 ? '' : 's'} (offline/older hubs will pick up changes on next flash).`
          );
        } else if (updatedHubs.length > 0) {
          setSyncMessage(
            `Saved to ${updatedHubs.length} hub YAML${updatedHubs.length === 1 ? '' : 's'} (${updatedHubs.join(', ')}). Re-flash hubs once to enable live sync.`
          );
        } else {
          setSyncMessage('Saved. Create a Headless Hub to sync these rules.');
        }
        onSynced?.(devices);
      }
    } catch (e: any) {
      setSyncError(e?.message || 'Failed to sync detached switches');
    } finally {
      setIsSyncing(false);
      setTimeout(() => syncStatusRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999] p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-emerald-100 text-emerald-700 rounded-lg">
              <Zap size={18} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-800">
                Shelly Gen3/Gen4 Offline BLE Backup
              </h2>
              <p className="text-xs text-slate-500">
                Dynamic real-time discovery on all headless hubs — zero per-hub Shelly assignment needed.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-200/70"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          {error && (
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2 text-xs text-amber-800">
              <AlertTriangle size={15} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Section 1: Discovered Shellys + Script Deployment */}
          <div className="border border-emerald-200 bg-emerald-50/30 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h3 className="text-xs font-bold text-emerald-900 uppercase tracking-wide flex items-center gap-1.5">
                  <Zap size={13} className="text-emerald-600" />
                  1. Discovered Shelly Devices ({devices.length})
                </h3>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Every hub automatically discovers Shellys in BLE range (see each hub&apos;s{' '}
                  <code className="bg-white px-1 rounded border border-slate-200">Visible Shellys</code>{' '}
                  sensor in HA). Entities used on your CYD tiles link automatically on save.
                </p>
              </div>
              <button
                type="button"
                onClick={loadFromHa}
                disabled={isLoading}
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-emerald-700 bg-white border border-emerald-200 rounded-lg hover:bg-emerald-50 disabled:opacity-50 flex-shrink-0"
              >
                {isLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                Refresh from HA
              </button>
            </div>

            {isLoading && devices.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                <Loader2 size={14} className="animate-spin" /> Querying Home Assistant for Shelly devices...
              </div>
            ) : devices.length === 0 ? (
              <div className="py-4 text-center text-xs text-slate-500 bg-white rounded-lg border border-slate-200">
                No Shelly devices found in Home Assistant.
              </div>
            ) : (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px] text-slate-500 px-0.5">
                  <span>
                    Showing Shellys used on CYDs first ({selectedMacs.size} selected)
                  </span>
                  <div className="flex items-center gap-2 font-medium">
                    <button
                      type="button"
                      onClick={() => {
                        const dsMacs = new Set(detachedSwitches.map(d => d.mac_address));
                        setSelectedMacs(
                          new Set(
                            devices
                              .filter(
                                d =>
                                  !!d.ip &&
                                  ((d.used_by_cyds && d.used_by_cyds.length > 0) ||
                                    dsMacs.has(d.mac_address) ||
                                    (d.entities || []).some(e =>
                                      cydReferencedEntities.has(e.entity_id)
                                    ))
                              )
                              .map(d => d.mac_address)
                          )
                        );
                      }}
                      className="text-emerald-700 hover:underline"
                    >
                      Select Used
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedMacs(new Set(devices.filter(d => !!d.ip).map(d => d.mac_address)))
                      }
                      className="text-slate-600 hover:underline"
                    >
                      All
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() => setSelectedMacs(new Set())}
                      className="text-slate-600 hover:underline"
                    >
                      None
                    </button>
                  </div>
                </div>
                <div className="max-h-56 overflow-y-auto bg-white border border-slate-200 rounded-lg divide-y divide-slate-100">
                  {devices.map(dev => {
                    const cydNames = Array.from(
                      new Set([
                        ...(dev.used_by_cyds || []),
                        ...((dev.entities || []).some(e => cydReferencedEntities.has(e.entity_id)) &&
                        (!dev.used_by_cyds || dev.used_by_cyds.length === 0)
                          ? ['current CYD']
                          : []),
                      ])
                    );
                    const checked = selectedMacs.has(dev.mac_address);
                    return (
                      <label
                        key={dev.mac_address}
                        className="flex items-start gap-2.5 px-3 py-2 hover:bg-slate-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!dev.ip}
                          onChange={() => toggleSelectMac(dev.mac_address)}
                          className="mt-1 rounded text-emerald-600"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center flex-wrap gap-1.5">
                            <span className="text-xs font-semibold text-slate-800">{dev.name}</span>
                            {dev.area_name && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                                {dev.area_name}
                              </span>
                            )}
                            {dev.model && (
                              <span className="text-[10px] text-slate-400">{dev.model}</span>
                            )}
                            {dev.detached_channels && dev.detached_channels.length > 0 && (
                              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">
                                Detached (in:{dev.detached_channels.join(',')})
                              </span>
                            )}
                            {cydNames.map(cyd => (
                              <span
                                key={cyd}
                                className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700"
                              >
                                {cyd}
                              </span>
                            ))}
                          </div>
                          <div className="text-[10px] text-slate-500 font-mono">
                            {dev.mac_address} {dev.ip ? `• ${dev.ip}` : '• (no IP)'}
                          </div>
                          {dev.entities.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {dev.entities.map(ent => {
                                const onAnyCyd =
                                  (ent.cyd_devices && ent.cyd_devices.length > 0) ||
                                  cydReferencedEntities.has(ent.entity_id);
                                return (
                                  <span
                                    key={ent.entity_id}
                                    className={`text-[10px] px-1.5 py-0.5 rounded border ${
                                      onAnyCyd
                                        ? 'bg-emerald-50 border-emerald-200 text-emerald-800 font-medium'
                                        : 'bg-slate-50 border-slate-200 text-slate-500'
                                    }`}
                                  >
                                    {ent.entity_id} (ch:{ent.channel})
                                  </span>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <input
                type="password"
                value={rpcPassword}
                onChange={e => setRpcPassword(e.target.value)}
                placeholder="Shelly RPC password (optional)"
                disabled={isDeploying}
                className="flex-1 min-w-[180px] text-xs px-2.5 py-1.5 border border-slate-300 rounded-lg bg-white disabled:opacity-50"
              />
              {isDeploying ? (
                <button
                  type="button"
                  onClick={() => {
                    deployCancelRef.current = true;
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-red-700 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100"
                >
                  <X size={13} />
                  Cancel ({deployProgress?.done ?? 0}/{deployProgress?.total ?? 0})
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleDeployScript}
                  disabled={selectedMacs.size === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                >
                  <Upload size={13} />
                  Deploy Script to {selectedMacs.size} Selected
                </button>
              )}
            </div>

            {deployProgress && (
              <div className="bg-white border border-emerald-200 rounded-lg p-2.5 space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-medium text-slate-700 flex items-center gap-1.5 min-w-0 truncate">
                    {isDeploying && <Loader2 size={12} className="animate-spin text-emerald-600 flex-shrink-0" />}
                    {isDeploying
                      ? `Deploying ${deployProgress.done + 1} / ${deployProgress.total}: ${deployProgress.currentName} (${deployProgress.currentIp})`
                      : deployProgress.cancelled
                      ? `Cancelled at ${deployProgress.done} / ${deployProgress.total}`
                      : `Completed ${deployProgress.done} / ${deployProgress.total}`}
                  </span>
                  <span className="font-mono text-[10px] text-slate-500 flex-shrink-0 ml-2">
                    <span className="text-emerald-700 font-semibold">{deployProgress.okCount} ok</span>
                    {deployProgress.failCount > 0 && (
                      <>
                        {' · '}
                        <span className="text-red-600 font-semibold">{deployProgress.failCount} failed</span>
                      </>
                    )}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-200 ${
                      deployProgress.failCount > 0 && !isDeploying ? 'bg-amber-500' : 'bg-emerald-500'
                    }`}
                    style={{
                      width: `${Math.round(
                        (deployProgress.done / Math.max(1, deployProgress.total)) * 100
                      )}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {deployResults.length > 0 && (
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {deployResults.map((r, i) => (
                  <div
                    key={i}
                    className={`text-[11px] px-2.5 py-1.5 rounded-lg border ${
                      r.ok
                        ? r.zigbee_warning
                          ? 'bg-amber-50 border-amber-200 text-amber-800'
                          : 'bg-emerald-50 border-emerald-200 text-emerald-800'
                        : 'bg-red-50 border-red-200 text-red-700'
                    }`}
                  >
                    <span className="font-semibold">{r.name || r.ip}:</span>{' '}
                    {r.ok ? `Script #${r.script_id} deployed & running` : r.error}
                    {r.zigbee_warning && (
                      <span> — Zigbee (*ZB) firmware: outbound beacons work, BLE RX unsupported.</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section 2: Detached Wall Switches -> Fan Light */}
          <div className="border border-slate-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                  2. Detached Wall Switches → Light / Shelly Output (Offline Fallback)
                </h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  When HA or Shelly Wi-Fi is down, any hub hearing the wall switch&apos;s BLE beacon toggles the linked ceiling fan light or Shelly output (locally or via ESP-NOW).
                </p>
              </div>
              <button
                type="button"
                onClick={handleAddEmptyBinding}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 flex-shrink-0"
              >
                <Plus size={12} /> Add Rule
              </button>
            </div>

            {/* Auto-detected suggestions */}
            {unacceptedSuggestions.length > 0 && (
              <div className="bg-indigo-50/70 border border-indigo-200 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-indigo-800 flex items-center gap-1.5">
                    <Sparkles size={13} className="text-indigo-600" />
                    Auto-Detected Suggestions ({unacceptedSuggestions.length})
                  </span>
                  {unacceptedSuggestions.length > 1 && (
                    <button
                      type="button"
                      onClick={() => unacceptedSuggestions.forEach(handleAcceptSuggestion)}
                      className="text-[11px] font-semibold text-indigo-700 hover:underline"
                    >
                      Accept All
                    </button>
                  )}
                </div>
                {unacceptedSuggestions.map((sug, idx) => (
                  <div
                    key={`${sug.mac_address}-${sug.input_channel}-${idx}`}
                    className="flex items-center justify-between gap-2 bg-white border border-indigo-100 rounded-md px-2.5 py-1.5 text-xs"
                  >
                    <div className="min-w-0">
                      <span className="font-semibold text-slate-800">{sug.name}</span>{' '}
                      <span className="text-[11px] text-slate-500 font-mono">
                        (input:{sug.input_channel})
                      </span>{' '}
                      → <span className="font-medium text-indigo-700">{sug.target_light_entity_id}</span>
                      <div className="text-[10px] text-slate-400">{sug.reason}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleAcceptSuggestion(sug)}
                      className="flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded hover:bg-indigo-100 flex-shrink-0"
                    >
                      <Check size={11} /> Accept
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Active binding rows */}
            {detachedSwitches.length === 0 ? (
              <div className="py-3 text-center text-xs text-slate-400 bg-slate-50 rounded-lg border border-dashed border-slate-200">
                No detached wall switch rules configured.
              </div>
            ) : (
              <div className="space-y-2">
                {detachedSwitches.map((ds, idx) => (
                  <div
                    key={idx}
                    className="grid grid-cols-12 gap-2 items-center bg-slate-50 border border-slate-200 rounded-lg p-2"
                  >
                    <select
                      value={ds.mac_address}
                      onChange={e => {
                        const mac = e.target.value;
                        const found = devices.find(d => d.mac_address === mac);
                        const defaultCh =
                          found?.detached_channels?.[0] ?? found?.available_inputs?.[0] ?? 0;
                        setDetachedSwitches(prev =>
                          prev.map((x, i) =>
                            i === idx
                              ? {
                                  ...x,
                                  mac_address: mac,
                                  name: found ? found.name : x.name,
                                  input_channel: defaultCh,
                                }
                              : x
                          )
                        );
                      }}
                      className="col-span-5 text-xs px-2 py-1.5 border border-slate-300 rounded-md bg-white"
                    >
                      <option value="">Select Shelly wall switch...</option>
                      {ds.mac_address && !devices.some(d => d.mac_address === ds.mac_address) && (
                        <option value={ds.mac_address}>
                          {ds.name || ds.mac_address} ({ds.mac_address})
                        </option>
                      )}
                      {devices.map(d => (
                        <option key={d.mac_address} value={d.mac_address}>
                          {d.name} {d.area_name ? `[${d.area_name}]` : ''}
                        </option>
                      ))}
                    </select>

                    {(() => {
                      const selDev = devices.find(d => d.mac_address === ds.mac_address);
                      const baseChs =
                        selDev?.detached_channels && selDev.detached_channels.length > 0
                          ? selDev.detached_channels
                          : selDev?.available_inputs && selDev.available_inputs.length > 0
                          ? selDev.available_inputs
                          : selDev
                          ? [0]
                          : [0, 1, 2, 3];
                      const channelOptions = Array.from(new Set([...baseChs, ds.input_channel])).sort(
                        (a, b) => a - b
                      );
                      return (
                        <select
                          value={ds.input_channel}
                          disabled={channelOptions.length <= 1}
                          title="Physical Shelly SW input terminal (SW1 = input:0, SW2 = input:1, etc.)"
                          onChange={e =>
                            setDetachedSwitches(prev =>
                              prev.map((x, i) =>
                                i === idx ? { ...x, input_channel: Number(e.target.value) } : x
                              )
                            )
                          }
                          className="col-span-2 text-xs px-2 py-1.5 border border-slate-300 rounded-md bg-white disabled:bg-slate-100 disabled:text-slate-600"
                        >
                          {channelOptions.map(ch => (
                            <option key={ch} value={ch}>
                              SW{ch + 1} (in:{ch})
                            </option>
                          ))}
                        </select>
                      );
                    })()}

                    <select
                      value={
                        ds.target_fan_device_id.startsWith('shelly:')
                          ? ds.target_fan_device_id
                          : ds.target_light_entity_id || ds.target_fan_device_id
                      }
                      onChange={e => {
                        const val = e.target.value;
                        if (val.startsWith('shelly:')) {
                          const [, sMac, sChStr] = val.split(':');
                          const sCh = Number(sChStr || 0);
                          const sDev = devices.find(d => d.mac_address === sMac);
                          const sEnt = sDev?.entities.find(
                            ent => ent.kind !== 'cover' && ent.channel === sCh
                          );
                          setDetachedSwitches(prev =>
                            prev.map((x, i) =>
                              i === idx
                                ? {
                                    ...x,
                                    target_fan_device_id: val,
                                    target_light_entity_id: sEnt?.entity_id || '',
                                  }
                                : x
                            )
                          );
                          return;
                        }
                        const fan = allHubFans.find(
                          f => f.light_entity_id === val || f.device_id === val
                        );
                        setDetachedSwitches(prev =>
                          prev.map((x, i) =>
                            i === idx
                              ? {
                                  ...x,
                                  target_fan_device_id: fan?.device_id || '',
                                  target_light_entity_id: fan?.light_entity_id || val,
                                }
                              : x
                          )
                        );
                      }}
                      className="col-span-4 text-xs px-2 py-1.5 border border-slate-300 rounded-md bg-white"
                    >
                      <option value="">Select target light / output...</option>
                      {allHubFans.length > 0 && (
                        <optgroup label="Ceiling Fan Lights (Tuya BLE)">
                          {allHubFans.map(f => (
                            <option
                              key={`fan-${f.hub_name}-${f.device_id}`}
                              value={f.light_entity_id || f.device_id}
                            >
                              {f.name} ({f.hub_name})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {devices.some(d => d.entities.some(ent => ent.kind !== 'cover')) && (
                        <optgroup label="Shelly Outputs (BLE)">
                          {devices
                            .flatMap(d =>
                              d.entities
                                .filter(ent => ent.kind !== 'cover')
                                .map(ent => ({
                                  key: `shelly-${d.mac_address}-${ent.channel}-${ent.entity_id}`,
                                  value: `shelly:${d.mac_address}:${ent.channel}`,
                                  label: `${ent.name || d.name}${d.area_name ? ` [${d.area_name}]` : ''} (ch:${ent.channel})`,
                                }))
                            )
                            .sort((a, b) => a.label.localeCompare(b.label))
                            .map(opt => (
                              <option key={opt.key} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                        </optgroup>
                      )}
                    </select>

                    <button
                      type="button"
                      onClick={() =>
                        setDetachedSwitches(prev => prev.filter((_, i) => i !== idx))
                      }
                      className="col-span-1 flex justify-center text-slate-400 hover:text-red-500"
                      title="Remove rule"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div ref={syncStatusRef} className="space-y-2 pt-1">
              {syncError && (
                <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2 text-xs text-amber-800">
                  <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                  <span>{syncError}</span>
                </div>
              )}
              {syncMessage && (
                <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg flex items-start gap-2 text-xs text-emerald-800">
                  <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0" />
                  <span>{syncMessage}</span>
                </div>
              )}
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleSyncHubs}
                  disabled={isSyncing}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  {isSyncing ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                  Save &amp; Sync to All Hubs ({hubs.length})
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-100"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
