import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  X,
  RefreshCw,
  CheckCircle2,
  XCircle,
  SkipForward,
  Clock,
  Loader2,
  Ban,
  ChevronDown,
  ChevronRight,
  UploadCloud,
  Monitor,
  Terminal,
  AlertTriangle,
} from 'lucide-react';
import { apiFetch } from '../utils/api';

export type BatchDeviceStatus =
  | 'checking'
  | 'pending'
  | 'updating'
  | 'updated'
  | 'skipped'
  | 'failed'
  | 'cancelled';

export interface BatchDeviceEntry {
  filename: string;
  device_name: string;
  friendly_name: string;
  screen_type: string | null;
  address: string;
  is_cyd: boolean;
  has_ota: boolean;
  online: boolean | null;
  status: BatchDeviceStatus;
  reason: string;
  duration_s: number | null;
  log_count: number;
  last_log: string;
  logs?: string[];
}

export interface BatchUpdateSummary {
  total: number;
  updated: number;
  failed: number;
  skipped: number;
  cancelled: number;
  pending: number;
  updating: number;
}

export interface BatchUpdateState {
  phase: 'idle' | 'scanning' | 'pinging' | 'updating' | 'completed' | 'cancelled';
  message: string;
  current_filename: string | null;
  started_at?: number;
  finished_at?: number | null;
  devices: BatchDeviceEntry[];
  summary: BatchUpdateSummary;
}

interface BatchUpdateDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** If true, opening the dialog automatically kicks off a batch update if none is running */
  autoStart?: boolean;
  /** Keep DOM mounted while running in background */
  stayMounted?: boolean;
  /** Notify parent of active state and short progress label */
  onActiveChange?: (active: boolean, label?: string) => void;
}

const RUNNING_PHASES = new Set(['scanning', 'pinging', 'updating']);

export const BatchUpdateDialog: React.FC<BatchUpdateDialogProps> = ({
  isOpen,
  onClose,
  autoStart = true,
  stayMounted = false,
  onActiveChange,
}) => {
  const [state, setState] = useState<BatchUpdateState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const expandedFileRef = useRef<string | null>(null);
  const hasAutoStartedRef = useRef(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  expandedFileRef.current = expandedFile;

  const isRunning = state != null && RUNNING_PHASES.has(state.phase);

  const notifyParent = useCallback(
    (next: BatchUpdateState | null) => {
      if (!onActiveChange) return;
      if (!next || !RUNNING_PHASES.has(next.phase)) {
        onActiveChange(false, undefined);
        return;
      }
      const eligibleTotal =
        next.summary.updated + next.summary.failed + next.summary.updating + next.summary.pending;
      const done = next.summary.updated + next.summary.failed;
      let label = 'Scanning...';
      if (next.phase === 'pinging') label = 'Checking online...';
      else if (next.phase === 'updating') {
        label = eligibleTotal > 0 ? `Updating ${Math.min(done + 1, eligibleTotal)}/${eligibleTotal}` : 'Updating...';
      }
      onActiveChange(true, label);
    },
    [onActiveChange]
  );

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const inc = expandedFileRef.current;
      const qs = inc ? `?include_logs=${encodeURIComponent(inc)}` : '';
      const res = await apiFetch(`/esphome/batch_update/status${qs}`);
      if (!res.ok) return null;
      const data: BatchUpdateState = await res.json();
      setState(data);
      notifyParent(data);
      if (!RUNNING_PHASES.has(data.phase)) {
        setCancelling(false);
        stopPolling();
      }
      return data;
    } catch {
      return null;
    }
  }, [notifyParent, stopPolling]);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(() => {
      fetchStatus();
    }, 1500);
  }, [fetchStatus, stopPolling]);

  const startBatchUpdate = useCallback(async () => {
    setError(null);
    setCancelling(false);
    setExpandedFile(null);
    try {
      const res = await apiFetch('/esphome/batch_update/start', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || `Failed to start batch update (${res.status})`);
        return;
      }
      setState(data);
      notifyParent(data);
      startPolling();
    } catch (e) {
      setError(`Failed to start batch update: ${(e as Error).message}`);
    }
  }, [notifyParent, startPolling]);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await apiFetch('/esphome/batch_update/cancel', { method: 'POST' });
    } catch {
      // ignore
    }
  };

  // On mount: check if a batch update is already running (e.g. after page reload)
  useEffect(() => {
    fetchStatus().then((data) => {
      if (data && RUNNING_PHASES.has(data.phase)) {
        startPolling();
      }
    });
    return () => stopPolling();
  }, [fetchStatus, startPolling, stopPolling]);

  // When opened: attach to running job or auto-start a fresh batch update
  useEffect(() => {
    if (!isOpen) {
      hasAutoStartedRef.current = false;
      return;
    }
    let cancelled = false;
    (async () => {
      const current = await fetchStatus();
      if (cancelled) return;
      if (current && RUNNING_PHASES.has(current.phase)) {
        startPolling();
      } else if (autoStart && !hasAutoStartedRef.current) {
        hasAutoStartedRef.current = true;
        await startBatchUpdate();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, autoStart, fetchStatus, startPolling, startBatchUpdate]);

  // Fetch logs immediately when user expands a device row
  useEffect(() => {
    if (expandedFile) {
      fetchStatus();
    }
  }, [expandedFile, fetchStatus]);

  // Auto-scroll expanded logs when updating
  const expandedLogsCount = state?.devices.find((d) => d.filename === expandedFile)?.logs?.length ?? 0;
  useEffect(() => {
    if (expandedFile && isRunning) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [expandedLogsCount, expandedFile, isRunning]);

  if (!isOpen && !stayMounted) return null;
  if (!isOpen) return null;

  const summary = state?.summary || {
    total: 0,
    updated: 0,
    failed: 0,
    skipped: 0,
    cancelled: 0,
    pending: 0,
    updating: 0,
  };
  const eligibleTotal = summary.updated + summary.failed + summary.updating + summary.pending + summary.cancelled;
  const completedEligible = summary.updated + summary.failed + summary.cancelled;
  const progressPct =
    state?.phase === 'completed' || state?.phase === 'cancelled'
      ? 100
      : state?.phase === 'scanning'
      ? 10
      : state?.phase === 'pinging'
      ? 25
      : eligibleTotal > 0
      ? Math.round(25 + (completedEligible / eligibleTotal) * 75)
      : 50;

  const renderStatusBadge = (dev: BatchDeviceEntry) => {
    switch (dev.status) {
      case 'updated':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
            <CheckCircle2 size={13} /> Updated
          </span>
        );
      case 'updating':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700">
            <Loader2 size={13} className="animate-spin" /> Updating
          </span>
        );
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700">
            <Clock size={13} /> Queued
          </span>
        );
      case 'checking':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">
            <Loader2 size={13} className="animate-spin" /> Checking
          </span>
        );
      case 'skipped':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">
            <SkipForward size={13} /> Skipped
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
            <XCircle size={13} /> Failed
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
            <Ban size={13} /> Cancelled
          </span>
        );
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[250] p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-slate-50">
          <div className="flex items-center gap-2.5 min-w-0">
            <UploadCloud className="text-blue-600 flex-shrink-0" size={20} />
            <div className="min-w-0">
              <h2 className="font-bold text-slate-800 text-base">Update All CYD Devices (OTA)</h2>
              <p className="text-xs text-slate-500 truncate">
                {state?.message || 'Scans drive configs and updates all online CYD devices with OTA.'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-slate-200 rounded-full transition-colors text-slate-500"
            title={isRunning ? 'Hide (continues in background)' : 'Close'}
          >
            <X size={18} />
          </button>
        </div>

        {/* Progress / Summary Banner */}
        <div className="px-5 py-3 border-b bg-white space-y-2.5">
          {error && (
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs font-medium">
              <AlertTriangle size={15} className="flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Progress Bar */}
          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                state?.phase === 'cancelled'
                  ? 'bg-amber-500'
                  : summary.failed > 0 && !isRunning
                  ? 'bg-red-500'
                  : state?.phase === 'completed'
                  ? 'bg-emerald-500'
                  : 'bg-blue-600'
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>

          {/* Summary Pills */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 font-semibold">
              Total: {summary.total}
            </span>
            <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 font-semibold">
              Updated: {summary.updated}
            </span>
            <span className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-semibold">
              Skipped: {summary.skipped}
            </span>
            {summary.failed > 0 && (
              <span className="px-2.5 py-1 rounded-full bg-red-50 text-red-700 font-semibold">
                Failed: {summary.failed}
              </span>
            )}
            {summary.cancelled > 0 && (
              <span className="px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 font-semibold">
                Cancelled: {summary.cancelled}
              </span>
            )}
            {(summary.pending > 0 || summary.updating > 0) && (
              <span className="px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 font-semibold">
                Remaining: {summary.pending + summary.updating}
              </span>
            )}
          </div>
        </div>

        {/* Per-Device List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-slate-50/50">
          {!state || (state.devices.length === 0 && isRunning) ? (
            <div className="flex flex-col items-center justify-center py-12 text-slate-400 gap-2">
              <Loader2 size={24} className="animate-spin text-blue-500" />
              <span className="text-sm font-medium">{state?.message || 'Scanning devices...'}</span>
            </div>
          ) : state.devices.length === 0 ? (
            <div className="text-center py-12 text-slate-400 text-sm">
              No ESPHome device YAML files found on drive.
            </div>
          ) : (
            state.devices.map((dev) => {
              const isExpanded = expandedFile === dev.filename;
              const hasLogs = dev.log_count > 0;
              return (
                <div
                  key={dev.filename}
                  className={`rounded-lg border bg-white transition-all ${
                    dev.status === 'updating'
                      ? 'border-blue-300 ring-1 ring-blue-100'
                      : dev.status === 'failed'
                      ? 'border-red-200'
                      : dev.status === 'updated'
                      ? 'border-emerald-200'
                      : 'border-slate-200'
                  }`}
                >
                  <div className="p-3 flex items-center justify-between gap-3">
                    <div className="flex items-start gap-2.5 min-w-0 flex-1">
                      <Monitor
                        size={16}
                        className={`mt-0.5 flex-shrink-0 ${
                          dev.is_cyd ? 'text-blue-500' : 'text-slate-300'
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-sm text-slate-800 truncate">
                            {dev.friendly_name}
                          </span>
                          <span className="text-[11px] font-mono text-slate-400 truncate">
                            {dev.filename}
                          </span>
                          {dev.screen_type && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-mono">
                              {dev.screen_type}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-600 mt-0.5">{dev.reason}</div>
                        {dev.status === 'updating' && dev.last_log && (
                          <div className="text-[11px] font-mono text-blue-600 truncate mt-1">
                            {dev.last_log}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      {renderStatusBadge(dev)}
                      {hasLogs && (
                        <button
                          onClick={() => setExpandedFile(isExpanded ? null : dev.filename)}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-200 hover:bg-slate-100 text-[11px] font-medium text-slate-600 transition-colors"
                          title="Toggle compile/OTA logs"
                        >
                          <Terminal size={12} />
                          Logs
                          {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        </button>
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="border-t bg-slate-900 p-3 rounded-b-lg max-h-56 overflow-y-auto">
                      <pre className="text-[11px] font-mono text-green-400 whitespace-pre-wrap break-all leading-relaxed">
                        {dev.logs && dev.logs.length > 0
                          ? dev.logs.join('\n')
                          : 'Loading logs...'}
                      </pre>
                      <div ref={logsEndRef} />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t bg-slate-50 flex items-center justify-between gap-3">
          <div className="text-xs text-slate-500">
            {isRunning
              ? 'You can close this popup — updates continue in the background.'
              : state?.phase === 'completed' || state?.phase === 'cancelled'
              ? 'Final report ready.'
              : ''}
          </div>
          <div className="flex items-center gap-2">
            {isRunning ? (
              <>
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="px-3 py-1.5 rounded-lg bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 text-xs font-bold transition-colors disabled:opacity-50"
                >
                  {cancelling ? 'Cancelling...' : 'Cancel Remaining'}
                </button>
                <button
                  onClick={onClose}
                  className="px-3 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 text-slate-700 text-xs font-bold transition-colors"
                >
                  Run in Background
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={startBatchUpdate}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition-colors"
                >
                  <RefreshCw size={13} /> Run Again
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 text-slate-700 text-xs font-bold transition-colors"
                >
                  Close
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
