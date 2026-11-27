import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, X, Zap } from 'lucide-react';
import {
  Config,
  DetachedSwitchBinding,
  DetachedSwitchSuggestion,
  DiscoveredShellyDevice,
  HeadlessHubConfig,
} from '../types';
import { apiFetch } from '../utils/api';
import { collectReferencedEntityIds } from '../utils/bleFanUtils';
import {
  DeployProgressState,
  ShellyDeviceListSection,
} from './shelly/ShellyDeviceListSection';
import {
  DetachedSwitchesSection,
  HubFanOption,
} from './shelly/DetachedSwitchesSection';

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
  const syncStatusRef = useRef<HTMLDivElement>(null);
  const [deployResults, setDeployResults] = useState<any[]>([]);
  const [deployProgress, setDeployProgress] = useState<DeployProgressState | null>(null);
  const deployCancelRef = useRef(false);

  const cydReferencedEntities = useMemo(() => collectReferencedEntityIds(config), [config]);

  const allHubFans = useMemo<HubFanOption[]>(() => {
    const out: HubFanOption[] = [];
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

  const handleSelectUsed = () => {
    const dsMacs = new Set(detachedSwitches.map(d => d.mac_address));
    setSelectedMacs(
      new Set(
        devices
          .filter(
            d =>
              !!d.ip &&
              ((d.used_by_cyds && d.used_by_cyds.length > 0) ||
                dsMacs.has(d.mac_address) ||
                (d.entities || []).some(e => cydReferencedEntities.has(e.entity_id)))
          )
          .map(d => d.mac_address)
      )
    );
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
          setDeployProgress(prev =>
            prev ? { ...prev, cancelled: true, currentName: '', currentIp: '' } : null
          );
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
        input_channel: firstDev?.detached_channels?.[0] ?? firstDev?.available_inputs?.[0] ?? 0,
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
        const liveHubs: string[] = Array.isArray(data.live_pushed_hubs)
          ? data.live_pushed_hubs
          : [];
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
      setTimeout(
        () => syncStatusRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }),
        50
      );
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
                Dynamic real-time discovery on all headless hubs — zero per-hub Shelly assignment
                needed.
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

          <ShellyDeviceListSection
            devices={devices}
            selectedMacs={selectedMacs}
            cydReferencedEntities={cydReferencedEntities}
            rpcPassword={rpcPassword}
            isLoading={isLoading}
            isDeploying={isDeploying}
            deployProgress={deployProgress}
            deployResults={deployResults}
            onRefresh={loadFromHa}
            onSelectUsed={handleSelectUsed}
            onSelectAll={() =>
              setSelectedMacs(new Set(devices.filter(d => !!d.ip).map(d => d.mac_address)))
            }
            onSelectNone={() => setSelectedMacs(new Set())}
            onToggleMac={toggleSelectMac}
            onRpcPasswordChange={setRpcPassword}
            onDeploy={handleDeployScript}
            onCancelDeploy={() => {
              deployCancelRef.current = true;
            }}
          />

          <DetachedSwitchesSection
            devices={devices}
            allHubFans={allHubFans}
            hubCount={hubs.length}
            detachedSwitches={detachedSwitches}
            unacceptedSuggestions={unacceptedSuggestions}
            isSyncing={isSyncing}
            syncMessage={syncMessage}
            syncError={syncError}
            syncStatusRef={syncStatusRef}
            onAddEmpty={handleAddEmptyBinding}
            onAcceptSuggestion={handleAcceptSuggestion}
            onUpdateBindings={setDetachedSwitches}
            onSyncHubs={handleSyncHubs}
          />
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
