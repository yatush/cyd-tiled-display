import React from 'react';
import { Loader2, RefreshCw, Upload, X, Zap } from 'lucide-react';
import { DiscoveredShellyDevice } from '../../types';

export interface DeployProgressState {
  done: number;
  total: number;
  currentName: string;
  currentIp: string;
  okCount: number;
  failCount: number;
  cancelled: boolean;
}

interface ShellyDeviceListSectionProps {
  devices: DiscoveredShellyDevice[];
  selectedMacs: Set<string>;
  cydReferencedEntities: Set<string>;
  rpcPassword: string;
  isLoading: boolean;
  isDeploying: boolean;
  deployProgress: DeployProgressState | null;
  deployResults: any[];
  onRefresh: () => void;
  onSelectUsed: () => void;
  onSelectAll: () => void;
  onSelectNone: () => void;
  onToggleMac: (mac: string) => void;
  onRpcPasswordChange: (val: string) => void;
  onDeploy: () => void;
  onCancelDeploy: () => void;
}

export const ShellyDeviceListSection: React.FC<ShellyDeviceListSectionProps> = ({
  devices,
  selectedMacs,
  cydReferencedEntities,
  rpcPassword,
  isLoading,
  isDeploying,
  deployProgress,
  deployResults,
  onRefresh,
  onSelectUsed,
  onSelectAll,
  onSelectNone,
  onToggleMac,
  onRpcPasswordChange,
  onDeploy,
  onCancelDeploy,
}) => {
  return (
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
          onClick={onRefresh}
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
            <span>Showing Shellys used on CYDs first ({selectedMacs.size} selected)</span>
            <div className="flex items-center gap-2 font-medium">
              <button
                type="button"
                onClick={onSelectUsed}
                className="text-emerald-700 hover:underline"
              >
                Select Used
              </button>
              <span className="text-slate-300">|</span>
              <button
                type="button"
                onClick={onSelectAll}
                className="text-slate-600 hover:underline"
              >
                All
              </button>
              <span className="text-slate-300">|</span>
              <button
                type="button"
                onClick={onSelectNone}
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
                    onChange={() => onToggleMac(dev.mac_address)}
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
                      {dev.model && <span className="text-[10px] text-slate-400">{dev.model}</span>}
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
          onChange={e => onRpcPasswordChange(e.target.value)}
          placeholder="Shelly RPC password (optional)"
          disabled={isDeploying}
          className="flex-1 min-w-[180px] text-xs px-2.5 py-1.5 border border-slate-300 rounded-lg bg-white disabled:opacity-50"
        />
        {isDeploying ? (
          <button
            type="button"
            onClick={onCancelDeploy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-red-700 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100"
          >
            <X size={13} />
            Cancel ({deployProgress?.done ?? 0}/{deployProgress?.total ?? 0})
          </button>
        ) : (
          <button
            type="button"
            onClick={onDeploy}
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
              {isDeploying && (
                <Loader2 size={12} className="animate-spin text-emerald-600 flex-shrink-0" />
              )}
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
                  <span className="text-red-600 font-semibold">
                    {deployProgress.failCount} failed
                  </span>
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
  );
};
