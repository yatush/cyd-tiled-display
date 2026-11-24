import React, { useState } from 'react';
import {
  Bluetooth,
  CheckCircle2,
  Loader2,
  Radar,
  Radio,
  AlertTriangle,
  X,
  Plus,
  Link2,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import { BleFanConfig, TuyaBleCandidate } from '../types';

export interface BleScanSighting {
  cyd_filename: string;
  cyd_name: string;
  friendly_name: string;
  rssi: number;
}

export interface DiscoveredBleFan {
  mac: string;
  addr_type: number;
  bound: boolean;
  uuid: string;
  product_id: string;
  best_cyd: BleScanSighting | null;
  best_rssi: number;
  sightings: BleScanSighting[];
  hosted_by: string[];
  matched_ha_fan: {
    name: string;
    device_id: string;
    local_key: string;
    product_id: string;
    fan_entity_id: string;
    light_entity_id: string;
  } | null;
}

export interface ScannedCydStatus {
  cyd_filename: string;
  cyd_name: string;
  friendly_name: string;
  status: 'ok' | 'unsupported' | 'offline' | 'error';
  error?: string;
  sightings_count: number;
}

interface FindBleFansDialogProps {
  isOpen: boolean;
  onClose: () => void;
  tuyaBleCandidates: TuyaBleCandidate[];
  onFanAdded: (
    targetCyd: string,
    updatedFans: BleFanConfig[],
    hostedBy: Record<string, string[]>
  ) => void;
}

interface RowFormState {
  targetCyd: string;
  name: string;
  blinkConfirm: boolean;
  selectedHaDeviceId: string;
  manualDeviceId: string;
  manualLocalKey: string;
  busy: boolean;
  statusText?: string;
  errorText?: string;
  done?: boolean;
}

export const FindBleFansDialog: React.FC<FindBleFansDialogProps> = ({
  isOpen,
  onClose,
  tuyaBleCandidates,
  onFanAdded,
}) => {
  const [durationS, setDurationS] = useState(10);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [cyds, setCyds] = useState<ScannedCydStatus[]>([]);
  const [fans, setFans] = useState<DiscoveredBleFan[]>([]);
  const [haFans, setHaFans] = useState<TuyaBleCandidate[]>(tuyaBleCandidates);
  const [hasScanned, setHasScanned] = useState(false);
  const [rowState, setRowState] = useState<Record<string, RowFormState>>({});

  if (!isOpen) return null;

  const updateRow = (mac: string, patch: Partial<RowFormState>) => {
    setRowState(prev => ({
      ...prev,
      [mac]: {
        ...(prev[mac] || {
          targetCyd: '',
          name: '',
          blinkConfirm: true,
          selectedHaDeviceId: '',
          manualDeviceId: '',
          manualLocalKey: '',
          busy: false,
        }),
        ...patch,
      },
    }));
  };

  const handleScan = async () => {
    setScanning(true);
    setScanError(null);
    try {
      const res = await apiFetch('/tuya_ble/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration_s: durationS }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || `Scan failed (${res.status})`);
      }
      const discovered: DiscoveredBleFan[] = Array.isArray(data.fans) ? data.fans : [];
      const scannedCyds: ScannedCydStatus[] = Array.isArray(data.cyds) ? data.cyds : [];
      const latestHaFans: TuyaBleCandidate[] = Array.isArray(data.tuya_local_fans)
        ? data.tuya_local_fans
        : tuyaBleCandidates;

      setCyds(scannedCyds);
      setFans(discovered);
      setHaFans(latestHaFans);
      setHasScanned(true);

      const initialRows: Record<string, RowFormState> = {};
      for (const fan of discovered) {
        const defaultTarget =
          fan.best_cyd?.cyd_filename ||
          scannedCyds.find(c => c.status === 'ok')?.cyd_filename ||
          scannedCyds[0]?.cyd_filename ||
          '';
        const suffix = fan.mac.replace(/:/g, '').slice(-4);
        const defaultName = fan.matched_ha_fan?.name || `BLE Fan ${suffix}`;
        initialRows[fan.mac] = {
          targetCyd: defaultTarget,
          name: defaultName,
          blinkConfirm: true,
          selectedHaDeviceId: fan.matched_ha_fan?.device_id || '',
          manualDeviceId: '',
          manualLocalKey: '',
          busy: false,
        };
      }
      setRowState(initialRows);
    } catch (err: any) {
      setScanError(err?.message || 'Failed to scan CYD devices');
    } finally {
      setScanning(false);
    }
  };

  const handlePairAndAdd = async (fan: DiscoveredBleFan) => {
    const row = rowState[fan.mac];
    if (!row?.targetCyd) {
      updateRow(fan.mac, { errorText: 'Select a target CYD first' });
      return;
    }
    if (!fan.uuid) {
      updateRow(fan.mac, {
        errorText: 'Device advertisement did not include a readable UUID; cannot pair automatically.',
      });
      return;
    }

    updateRow(fan.mac, {
      busy: true,
      errorText: undefined,
      statusText: `Pairing via ${row.targetCyd}...`,
    });

    try {
      const pairRes = await apiFetch('/tuya_ble/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_cyd: row.targetCyd,
          mac: fan.mac,
          addr_type: fan.addr_type,
          uuid: fan.uuid,
          blink_confirm: row.blinkConfirm,
        }),
      });
      const pairData = await pairRes.json();
      if (!pairRes.ok || !pairData.ok) {
        throw new Error(pairData.error || 'BLE pairing failed');
      }

      updateRow(fan.mac, { statusText: `Saving to ${row.targetCyd}...` });

      const addRes = await apiFetch('/tuya_ble/add_to_device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_cyd: row.targetCyd,
          fan: {
            name: row.name.trim() || `BLE Fan ${fan.mac.replace(/:/g, '').slice(-4)}`,
            device_id: pairData.device_id,
            local_key: pairData.local_key,
            product_id: fan.product_id || '',
            mac_address: fan.mac,
            uuid: fan.uuid,
            expose_to_ha: true,
          },
        }),
      });
      const addData = await addRes.json();
      if (!addRes.ok || !addData.ok) {
        throw new Error(addData.error || 'Failed to save fan to target CYD config');
      }

      onFanAdded(row.targetCyd, addData.fans || [], addData.hosted_by || {});
      setFans(prev =>
        prev.map(f =>
          f.mac === fan.mac
            ? {
                ...f,
                bound: true,
                hosted_by: Array.from(new Set([...(f.hosted_by || []), row.targetCyd])),
              }
            : f
        )
      );
      updateRow(fan.mac, {
        busy: false,
        done: true,
        statusText: `Paired & added to ${row.targetCyd}. Compile & OTA flash ${row.targetCyd} to activate.`,
      });
    } catch (err: any) {
      updateRow(fan.mac, {
        busy: false,
        statusText: undefined,
        errorText: err?.message || 'Pairing failed',
      });
    }
  };

  const handleImportBoundAndAdd = async (fan: DiscoveredBleFan) => {
    const row = rowState[fan.mac];
    if (!row?.targetCyd) {
      updateRow(fan.mac, { errorText: 'Select a target CYD first' });
      return;
    }

    const haSource =
      fan.matched_ha_fan ||
      haFans.find(c => c.device_id === row.selectedHaDeviceId) ||
      null;

    const deviceId = (haSource?.device_id || row.manualDeviceId || '').trim();
    const localKey = (haSource?.local_key || row.manualLocalKey || '').trim();
    if (!deviceId || !localKey) {
      updateRow(fan.mac, {
        errorText: 'Select a Home Assistant tuya_local fan or enter device_id and local_key.',
      });
      return;
    }

    updateRow(fan.mac, {
      busy: true,
      errorText: undefined,
      statusText: `Adding to ${row.targetCyd}...`,
    });

    try {
      const addRes = await apiFetch('/tuya_ble/add_to_device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_cyd: row.targetCyd,
          fan: {
            name: row.name.trim() || haSource?.name || `BLE Fan ${fan.mac.replace(/:/g, '').slice(-4)}`,
            device_id: deviceId,
            local_key: localKey,
            product_id: fan.product_id || haSource?.product_id || '',
            mac_address: fan.mac,
            uuid: fan.uuid || '',
            fan_entity_id: haSource?.fan_entity_id || '',
            light_entity_id: haSource?.light_entity_id || '',
            expose_to_ha: true,
          },
        }),
      });
      const addData = await addRes.json();
      if (!addRes.ok || !addData.ok) {
        throw new Error(addData.error || 'Failed to save fan to target CYD config');
      }

      onFanAdded(row.targetCyd, addData.fans || [], addData.hosted_by || {});
      setFans(prev =>
        prev.map(f =>
          f.mac === fan.mac
            ? {
                ...f,
                hosted_by: Array.from(new Set([...(f.hosted_by || []), row.targetCyd])),
              }
            : f
        )
      );
      updateRow(fan.mac, {
        busy: false,
        done: true,
        statusText: `Added to ${row.targetCyd}. Compile & OTA flash ${row.targetCyd} to activate.`,
      });
    } catch (err: any) {
      updateRow(fan.mac, {
        busy: false,
        statusText: undefined,
        errorText: err?.message || 'Failed to add fan',
      });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[88vh] flex flex-col overflow-hidden border border-slate-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-sky-100 text-sky-700">
              <Bluetooth size={18} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-800">
                Find &amp; Pair BLE Fans (Whole-House Scan)
              </h2>
              <p className="text-[11px] text-slate-500">
                Scans on-demand across all online CYD displays, ranks by strongest RSSI, and saves directly into the best CYD&apos;s config.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200/70 rounded-lg"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scan controls */}
        <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3 bg-white">
          <div className="flex items-center gap-3">
            <button
              onClick={handleScan}
              disabled={scanning}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-60 shadow-sm"
            >
              {scanning ? <Loader2 size={14} className="animate-spin" /> : <Radar size={14} />}
              {scanning ? `Scanning all online CYDs (${durationS}s)...` : 'Scan All Online CYDs'}
            </button>
            <label className="flex items-center gap-1.5 text-xs text-slate-600">
              <span>Duration:</span>
              <select
                value={durationS}
                onChange={e => setDurationS(Number(e.target.value))}
                disabled={scanning}
                className="border border-slate-300 rounded px-2 py-1 text-xs bg-white"
              >
                <option value={6}>6s</option>
                <option value={10}>10s</option>
                <option value={15}>15s</option>
                <option value={20}>20s</option>
              </select>
            </label>
          </div>
          <span className="text-[11px] text-slate-400">
            Zero idle RAM overhead — CYDs only scan while this runs.
          </span>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {scanError && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700 flex items-center gap-2">
              <AlertTriangle size={14} className="shrink-0" />
              <span>{scanError}</span>
            </div>
          )}

          {/* Scanned CYDs status pills */}
          {cyds.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                CYD Scanners ({cyds.filter(c => c.status === 'ok').length}/{cyds.length} active)
              </div>
              <div className="flex flex-wrap gap-1.5">
                {cyds.map(c => (
                  <span
                    key={c.cyd_filename}
                    title={c.error || `${c.sightings_count} sighting(s)`}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] border ${
                      c.status === 'ok'
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                        : c.status === 'unsupported'
                        ? 'bg-amber-50 border-amber-200 text-amber-700'
                        : 'bg-slate-100 border-slate-200 text-slate-500'
                    }`}
                  >
                    <Radio size={10} />
                    <span className="font-medium">{c.friendly_name || c.cyd_name}</span>
                    {c.status === 'ok' && <span className="opacity-75">({c.sightings_count})</span>}
                    {c.status === 'unsupported' && <span className="opacity-75">(update FW)</span>}
                    {c.status === 'offline' && <span className="opacity-75">(offline)</span>}
                    {c.status === 'error' && <span className="opacity-75">(error)</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {!hasScanned && !scanning && (
            <div className="py-10 text-center text-slate-500 space-y-2">
              <Radar size={32} className="mx-auto text-sky-400 opacity-70" />
              <p className="text-sm font-medium text-slate-700">
                Click &ldquo;Scan All Online CYDs&rdquo; to discover nearby Tuya BLE fans
              </p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Unbound (factory-reset) fans can be paired directly without Smart Life. Already-bound fans can be imported from Home Assistant&apos;s <code className="bg-slate-100 px-1 rounded">tuya_local</code> integration.
              </p>
            </div>
          )}

          {hasScanned && fans.length === 0 && !scanning && (
            <div className="py-8 text-center text-slate-500 bg-slate-50 rounded-lg border border-slate-200 space-y-1.5">
              <p className="text-sm font-medium text-slate-700">No Tuya BLE fans detected</p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Note: FlyFan / Varin fans stop BLE advertising while connected to Wi-Fi. Ensure the fan is in BLE mode (Wi-Fi disconnected or factory-reset) and that your CYDs are running updated firmware.
              </p>
            </div>
          )}

          {/* Discovered fans list */}
          {fans.length > 0 && (
            <div className="space-y-3">
              {fans.map(fan => {
                const row = rowState[fan.mac] || {
                  targetCyd: fan.best_cyd?.cyd_filename || '',
                  name: '',
                  blinkConfirm: true,
                  selectedHaDeviceId: fan.matched_ha_fan?.device_id || '',
                  manualDeviceId: '',
                  manualLocalKey: '',
                  busy: false,
                };
                const otherSightings = fan.sightings.slice(1);
                const otherHosts = (fan.hosted_by || []).filter(h => h !== row.targetCyd);

                return (
                  <div
                    key={fan.mac}
                    className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm space-y-3"
                  >
                    {/* Top info row */}
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono text-xs font-bold text-slate-800">
                            {fan.mac}
                          </span>
                          {fan.bound ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                              Bound
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                              Unbound (Ready to Pair)
                            </span>
                          )}
                          {fan.matched_ha_fan && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-50 text-sky-700 border border-sky-200">
                              HA tuya_local: {fan.matched_ha_fan.name}
                            </span>
                          )}
                          {fan.hosted_by.length > 0 && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
                              Hosted on: {fan.hosted_by.join(', ')}
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-500 flex flex-wrap gap-3">
                          {fan.uuid && (
                            <span>
                              UUID: <code className="font-mono text-slate-700">{fan.uuid}</code>
                            </span>
                          )}
                          {fan.product_id && (
                            <span>
                              Product ID:{' '}
                              <code className="font-mono text-slate-700">{fan.product_id}</code>
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Best CYD + RSSI */}
                      <div className="text-right">
                        {fan.best_cyd && (
                          <div className="text-xs font-semibold text-sky-700">
                            Best: {fan.best_cyd.friendly_name} ({fan.best_cyd.rssi} dBm)
                          </div>
                        )}
                        {otherSightings.length > 0 && (
                          <div
                            className="text-[10px] text-slate-400"
                            title={otherSightings
                              .map(s => `${s.friendly_name} (${s.rssi} dBm)`)
                              .join(', ')}
                          >
                            Also seen by:{' '}
                            {otherSightings
                              .map(s => `${s.friendly_name} (${s.rssi} dBm)`)
                              .join(', ')}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Controls row */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 pt-2 border-t border-slate-100">
                      <div>
                        <label className="block text-[10px] font-medium text-slate-500 mb-0.5">
                          Fan Friendly Name
                        </label>
                        <input
                          type="text"
                          value={row.name}
                          onChange={e => updateRow(fan.mac, { name: e.target.value })}
                          placeholder="e.g. Sahar Fan"
                          disabled={row.busy}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded"
                        />
                      </div>

                      <div>
                        <label className="block text-[10px] font-medium text-slate-500 mb-0.5">
                          Target CYD Config
                        </label>
                        <select
                          value={row.targetCyd}
                          onChange={e => updateRow(fan.mac, { targetCyd: e.target.value })}
                          disabled={row.busy}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded bg-white"
                        >
                          {cyds.map(c => (
                            <option key={c.cyd_filename} value={c.cyd_filename}>
                              {c.friendly_name || c.cyd_name} ({c.cyd_filename})
                              {fan.best_cyd?.cyd_filename === c.cyd_filename ? ' ★ Best RSSI' : ''}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="flex flex-col justify-end">
                        {!fan.bound ? (
                          <div className="space-y-1.5">
                            <label className="flex items-center gap-1.5 text-[11px] text-slate-600 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={row.blinkConfirm}
                                onChange={e =>
                                  updateRow(fan.mac, { blinkConfirm: e.target.checked })
                                }
                                disabled={row.busy}
                                className="rounded text-sky-600"
                              />
                              <span>Blink light to confirm room</span>
                            </label>
                            <button
                              onClick={() => handlePairAndAdd(fan)}
                              disabled={row.busy || !row.targetCyd}
                              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60"
                            >
                              {row.busy ? (
                                <Loader2 size={13} className="animate-spin" />
                              ) : (
                                <Link2 size={13} />
                              )}
                              <span>
                                Pair &amp; Add to {row.targetCyd.replace(/\.yaml$/, '')}
                              </span>
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => handleImportBoundAndAdd(fan)}
                            disabled={row.busy || !row.targetCyd}
                            className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-60"
                          >
                            {row.busy ? (
                              <Loader2 size={13} className="animate-spin" />
                            ) : (
                              <Plus size={13} />
                            )}
                            <span>
                              Import &amp; Add to {row.targetCyd.replace(/\.yaml$/, '')}
                            </span>
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Bound fan credential selector when not auto-matched */}
                    {fan.bound && !fan.matched_ha_fan && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 pt-1.5 border-t border-slate-100 bg-slate-50/70 p-2 rounded">
                        <div>
                          <label className="block text-[10px] font-medium text-slate-500 mb-0.5">
                            Import from HA tuya_local
                          </label>
                          <select
                            value={row.selectedHaDeviceId}
                            onChange={e => {
                              const picked = haFans.find(c => c.device_id === e.target.value);
                              updateRow(fan.mac, {
                                selectedHaDeviceId: e.target.value,
                                name: picked?.name || row.name,
                              });
                            }}
                            disabled={row.busy}
                            className="w-full px-2 py-1 text-xs border border-slate-300 rounded bg-white"
                          >
                            <option value="">-- Enter manually or pick from HA --</option>
                            {haFans.map(c => (
                              <option key={c.device_id} value={c.device_id}>
                                {c.name} ({c.device_id.slice(0, 8)}…)
                              </option>
                            ))}
                          </select>
                        </div>
                        {!row.selectedHaDeviceId && (
                          <>
                            <div>
                              <label className="block text-[10px] font-medium text-slate-500 mb-0.5">
                                Device ID (manual)
                              </label>
                              <input
                                type="text"
                                value={row.manualDeviceId}
                                onChange={e =>
                                  updateRow(fan.mac, { manualDeviceId: e.target.value })
                                }
                                placeholder="22-char device_id"
                                disabled={row.busy}
                                className="w-full px-2 py-1 text-xs font-mono border border-slate-300 rounded bg-white"
                              />
                            </div>
                            <div>
                              <label className="block text-[10px] font-medium text-slate-500 mb-0.5">
                                Local Key (manual)
                              </label>
                              <input
                                type="password"
                                value={row.manualLocalKey}
                                onChange={e =>
                                  updateRow(fan.mac, { manualLocalKey: e.target.value })
                                }
                                placeholder="16-char local_key"
                                disabled={row.busy}
                                className="w-full px-2 py-1 text-xs font-mono border border-slate-300 rounded bg-white"
                              />
                            </div>
                          </>
                        )}
                      </div>
                    )}

                    {/* Duplicate host warning */}
                    {otherHosts.length > 0 && (
                      <div className="flex items-start gap-1.5 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5">
                        <AlertTriangle size={13} className="shrink-0 mt-0.5 text-amber-600" />
                        <span>
                          Already hosted by <strong>{otherHosts.join(', ')}</strong>. Avoid hosting the same BLE fan on two CYDs simultaneously.
                        </span>
                      </div>
                    )}

                    {/* Status / Error feedback */}
                    {row.statusText && (
                      <div
                        className={`flex items-center gap-1.5 text-xs rounded px-2.5 py-1.5 ${
                          row.done
                            ? 'bg-emerald-50 border border-emerald-200 text-emerald-800'
                            : 'bg-sky-50 border border-sky-200 text-sky-800'
                        }`}
                      >
                        {row.done ? (
                          <CheckCircle2 size={14} className="shrink-0 text-emerald-600" />
                        ) : (
                          <Loader2 size={14} className="shrink-0 animate-spin text-sky-600" />
                        )}
                        <span>{row.statusText}</span>
                      </div>
                    )}
                    {row.errorText && (
                      <div className="flex items-center gap-1.5 text-xs bg-red-50 border border-red-200 text-red-700 rounded px-2.5 py-1.5">
                        <AlertTriangle size={14} className="shrink-0" />
                        <span>{row.errorText}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <span className="text-[11px] text-slate-500">
            After adding a fan to a CYD, compile &amp; OTA flash that CYD so it takes ownership.
          </span>
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-slate-200 text-slate-700 hover:bg-slate-300"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
