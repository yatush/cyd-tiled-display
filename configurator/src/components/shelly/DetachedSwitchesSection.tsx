import React from 'react';
import { AlertTriangle, Check, CheckCircle2, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react';
import {
  DetachedSwitchBinding,
  DetachedSwitchSuggestion,
  DiscoveredShellyDevice,
} from '../../types';

export interface HubFanOption {
  name: string;
  device_id: string;
  light_entity_id: string;
  hub_name: string;
}

interface DetachedSwitchesSectionProps {
  devices: DiscoveredShellyDevice[];
  allHubFans: HubFanOption[];
  hubCount: number;
  detachedSwitches: DetachedSwitchBinding[];
  unacceptedSuggestions: DetachedSwitchSuggestion[];
  isSyncing: boolean;
  syncMessage: string | null;
  syncError: string | null;
  syncStatusRef: React.RefObject<HTMLDivElement>;
  onAddEmpty: () => void;
  onAcceptSuggestion: (sug: DetachedSwitchSuggestion) => void;
  onUpdateBindings: React.Dispatch<React.SetStateAction<DetachedSwitchBinding[]>>;
  onSyncHubs: () => void;
}

export const DetachedSwitchesSection: React.FC<DetachedSwitchesSectionProps> = ({
  devices,
  allHubFans,
  hubCount,
  detachedSwitches,
  unacceptedSuggestions,
  isSyncing,
  syncMessage,
  syncError,
  syncStatusRef,
  onAddEmpty,
  onAcceptSuggestion,
  onUpdateBindings,
  onSyncHubs,
}) => {
  return (
    <div className="border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
            2. Detached Wall Switches → Light / Shelly Output (Offline Fallback)
          </h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            When HA or Shelly Wi-Fi is down, any hub hearing the wall switch&apos;s BLE beacon
            toggles the linked ceiling fan light or Shelly output (locally or via ESP-NOW).
          </p>
        </div>
        <button
          type="button"
          onClick={onAddEmpty}
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
                onClick={() => unacceptedSuggestions.forEach(onAcceptSuggestion)}
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
                onClick={() => onAcceptSuggestion(sug)}
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
          {detachedSwitches.map((ds, idx) => {
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
                    onUpdateBindings(prev =>
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

                <select
                  value={ds.input_channel}
                  disabled={channelOptions.length <= 1}
                  title="Physical Shelly SW input terminal (SW1 = input:0, SW2 = input:1, etc.)"
                  onChange={e =>
                    onUpdateBindings(prev =>
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
                      onUpdateBindings(prev =>
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
                    onUpdateBindings(prev =>
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
                  onClick={() => onUpdateBindings(prev => prev.filter((_, i) => i !== idx))}
                  className="col-span-1 flex justify-center text-slate-400 hover:text-red-500"
                  title="Remove rule"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })}
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
            onClick={onSyncHubs}
            disabled={isSyncing}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {isSyncing ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            Save &amp; Sync to All Hubs ({hubCount})
          </button>
        </div>
      </div>
    </div>
  );
};
