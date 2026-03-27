import React, { useState, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { 
  ShieldCheck, 
  ShieldAlert, 
  Loader2, 
  Database, 
  Settings, 
  Undo2, 
  Redo2, 
  Play,
  Activity,
  Download,
  Upload,
  RefreshCw,
  FolderOpen,
  Monitor,
  Square,
  Wrench,
  X,
  ChevronDown
} from 'lucide-react';
import { ConnectionType, HaStatus } from '../hooks/useHaConnection';
import { apiFetch } from '../utils/api';

interface TopBarProps {
  haStatus: HaStatus;
  connectionType: ConnectionType;
  entityCount: number;
  onOpenSettings: () => void;
  onRefreshHa: () => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onGenerate: () => void;
  onOpenFileManagement: () => void;
  isGenerating: boolean;
  updateAvailable?: boolean;
  emulatorStatus: 'stopped' | 'running' | 'starting' | 'error';
  onStartEmulator: () => void;
  onStopEmulator: () => void;
  onOpenEmulator?: () => void;
  /** Current toolchain setup phase (from /api/toolchain/status) */
  toolchainPhase?: string;
  toolchainProgress?: number;
  toolchainMessage?: string;
  /** Open the Install dialog (used by the no_toolchain overlay CTA) */
  onOpenInstall?: () => void;
  /** Whether a newer toolchain build is available on GitHub */
  toolchainUpdateAvailable?: boolean;
  /** Local installed build ID (e.g. "2026.3.1-20260327-run45") */
  toolchainBuildId?: string;
}

export const TopBar: React.FC<TopBarProps> = ({
  haStatus,
  connectionType,
  entityCount,
  onOpenSettings,
  onRefreshHa,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onGenerate,
  onOpenFileManagement,
  isGenerating,
  updateAvailable,
  emulatorStatus,
  onStartEmulator,
  onStopEmulator,
  onOpenEmulator,
  toolchainPhase,
  toolchainProgress = 0,
  toolchainMessage,
  onOpenInstall,
  toolchainUpdateAvailable,
  toolchainBuildId,
}) => {
  const UPGRADING_PHASES = ['downloading', 'extracting', 'fixing', 'warming'];
  const isToolchainUpgrading = toolchainPhase != null && UPGRADING_PHASES.includes(toolchainPhase);
  const showToolchainIcon = toolchainPhase != null && toolchainPhase !== 'starting';

  // Short label from build ID: "2026.3.1-20260327-run45" → "run45"
  const buildTag = toolchainBuildId ? toolchainBuildId.split('-').pop() : null;

  const [showLog, setShowLog]         = useState(false);
  const [logContent, setLogContent]     = useState('');
  const [updateBtnState, setUpdateBtnState] = useState<'idle' | 'checking' | 'up_to_date'>('idle');

  const handleCheckUpdate = async () => {
    setUpdateBtnState('checking');
    try {
      const res = await apiFetch('/toolchain/download_latest', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'up_to_date') {
          setUpdateBtnState('up_to_date');
          setTimeout(() => setUpdateBtnState('idle'), 4000);
          return;
        }
      }
    } catch { /* ignore */ }
    setUpdateBtnState('idle');
  };
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showLog) return;
    const fetchLog = async () => {
      try {
        const res = await apiFetch('/toolchain/log?lines=400');
        if (res.ok) { const t = await res.text(); setLogContent(t); }
      } catch { /* ignore */ }
    };
    fetchLog();
    const id = setInterval(fetchLog, 2000);
    return () => clearInterval(id);
  }, [showLog]);

  useEffect(() => {
    if (showLog) logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logContent, showLog]);
  const getStatusIcon = () => {
    if (haStatus === 'idle') return <Loader2 size={18} className="animate-spin text-slate-400" />;
    if (haStatus === 'error') return <ShieldAlert size={18} className="text-red-500" />;
    if (haStatus === 'mock') return <Database size={18} className="text-amber-500" />;
    return <ShieldCheck size={18} className="text-emerald-500" />;
  };

  const getStatusText = () => {
    if (haStatus === 'idle') return 'Connecting...';
    if (haStatus === 'error') return 'Connection Error';
    if (connectionType === 'mock') return 'Mock Data Mode';
    if (connectionType === 'local') return 'Local HA Connected';
    return 'Remote HA Connected';
  };

  return (
    <div className="h-14 border-b bg-white flex items-center justify-between px-4 flex-shrink-0 z-10 shadow-sm">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-yellow-500 rounded flex items-center justify-center text-slate-900 font-bold">
            CYD
          </div>
          <span className="font-bold text-slate-700 hidden sm:inline">Tiled Display</span>
        </div>

        <div className="h-8 w-px bg-slate-200 hidden sm:block" />

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 rounded-full border border-slate-100">
            {getStatusIcon()}
            <span className="text-sm font-medium text-slate-600">{getStatusText()}</span>
            <button 
              onClick={onRefreshHa}
              className="ml-1 p-1 hover:bg-slate-200 rounded-full transition-colors text-slate-400 hover:text-slate-600"
              title="Refresh Entities"
            >
              <RefreshCw size={14} className={haStatus === 'idle' ? 'animate-spin' : ''} />
            </button>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 rounded-full border border-blue-100 text-blue-700">
            <Activity size={16} />
            <span className="text-sm font-bold">{entityCount} Entities</span>
          </div>

          {/* Toolchain badge — clickable to show log */}
          {showToolchainIcon && (
            <button
              onClick={() => setShowLog(true)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium transition-colors ${
                isToolchainUpgrading
                  ? 'bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100'
                  : toolchainUpdateAvailable
                  ? 'bg-amber-50 border-amber-300 text-amber-700 hover:bg-amber-100'
                  : toolchainPhase === 'ready'
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'
                  : toolchainPhase === 'building'
                  ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                  : 'bg-red-50 border-red-200 text-red-600 hover:bg-red-100'
              }`}
              title={toolchainUpdateAvailable && !isToolchainUpgrading ? 'Toolchain update downloading...' : 'Click to view toolchain log'}
            >
              <Wrench size={13} className={isToolchainUpgrading || toolchainPhase === 'building' ? 'animate-pulse' : ''} />
              <span className="hidden sm:inline">
                {isToolchainUpgrading
                  ? (toolchainPhase === 'warming' ? 'Warming cache' : 'Updating toolchain')
                  : toolchainUpdateAvailable
                  ? 'Update available'
                  : toolchainPhase === 'ready'
                  ? `Toolchain ready${buildTag ? ` · ${buildTag}` : ''}`
                  : toolchainPhase === 'building' ? 'Building toolchain' : 'Toolchain needed'}
              </span>
              {isToolchainUpgrading && <span className="font-mono">{toolchainProgress}%</span>}
              {(isToolchainUpgrading || toolchainUpdateAvailable) && toolchainPhase !== 'warming' && <Download size={11} className="opacity-70 animate-pulse" />}
              {!isToolchainUpgrading && !toolchainUpdateAvailable && <ChevronDown size={11} className="opacity-60" />}
            </button>
          )}

          {/* Toolchain log overlay — rendered via portal to escape TopBar stacking context */}
          {showLog && ReactDOM.createPortal(
            <div className="fixed inset-0 bg-black/50 z-[9999] flex items-center justify-center p-4 backdrop-blur-sm" onClick={() => setShowLog(false)}>
              <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[80vh]" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between px-4 py-3 border-b bg-slate-50 rounded-t-xl">
                  <div className="flex items-center gap-2 min-w-0">
                    <Wrench size={16} className="text-slate-500 flex-shrink-0" />
                    <span className="font-semibold text-slate-700 text-sm">Toolchain Setup Log</span>
                    {toolchainMessage && <span className="text-slate-400 text-xs truncate">— {toolchainMessage}</span>}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                    {toolchainPhase === 'no_toolchain' && onOpenInstall && (
                      <button
                        onClick={() => { setShowLog(false); onOpenInstall(); }}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-colors"
                      >
                        <Wrench size={13} />
                        Build locally
                      </button>
                    )}
                    {toolchainPhase === 'ready' && (
                      <button
                        onClick={handleCheckUpdate}
                        disabled={updateBtnState === 'checking'}
                        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                          updateBtnState === 'up_to_date'
                            ? 'bg-emerald-100 text-emerald-700 cursor-default'
                            : updateBtnState === 'checking'
                            ? 'bg-slate-100 text-slate-400 cursor-wait'
                            : 'bg-amber-100 hover:bg-amber-200 text-amber-700'
                        }`}
                      >
                        <Download size={13} className={updateBtnState === 'checking' ? 'animate-pulse' : ''} />
                        {updateBtnState === 'up_to_date' ? 'Up to date' : updateBtnState === 'checking' ? 'Checking...' : 'Update toolchain'}
                      </button>
                    )}
                    <button onClick={() => setShowLog(false)} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
                      <X size={16} />
                    </button>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto bg-slate-900 rounded-b-xl p-3">
                  <pre className="text-green-400 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all">
                    {logContent || 'No log output yet — toolchain_setup.py has not written anything.'}
                  </pre>
                  <div ref={logEndRef} />
                </div>
              </div>
            </div>,
            document.body
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center bg-slate-100 rounded-lg p-1 mr-2">
          <button
            onClick={onUndo}
            disabled={!canUndo}
            className="p-1.5 rounded hover:bg-white hover:shadow-sm disabled:opacity-30 transition-all"
            title="Undo (Ctrl+Z)"
          >
            <Undo2 size={18} className="text-slate-600" />
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo}
            className="p-1.5 rounded hover:bg-white hover:shadow-sm disabled:opacity-30 transition-all"
            title="Redo (Ctrl+Y)"
          >
            <Redo2 size={18} className="text-slate-600" />
          </button>
        </div>

        <div className="flex items-center bg-slate-100 rounded-lg p-1 mr-2">
          {emulatorStatus === 'running' ? (
            <div className="flex gap-1">
              <button
                onClick={onOpenEmulator}
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-blue-100 hover:bg-blue-200 text-blue-700 transition-all"
                title="View Emulator"
              >
                <Monitor size={16} />
                <span className="text-sm font-bold">View</span>
              </button>
              <button
                onClick={onStopEmulator}
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-red-100 hover:bg-red-200 text-red-700 transition-all"
                title="Stop Emulator"
              >
                <Square size={16} fill="currentColor" />
                <span className="text-sm font-bold">Stop</span>
              </button>
            </div>
          ) : (
            <button
              onClick={onStartEmulator}
              disabled={emulatorStatus === 'starting'}
              className={`flex items-center gap-2 px-3 py-1.5 rounded transition-all ${
                emulatorStatus === 'starting' 
                  ? 'bg-slate-200 text-slate-400' 
                  : 'bg-green-100 hover:bg-green-200 text-green-700'
              }`}
              title="Start Emulator"
            >
              {emulatorStatus === 'starting' ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
              <span className="text-sm font-bold">Emulator</span>
            </button>
          )}
        </div>

        <button
          onClick={onOpenFileManagement}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 transition-all shadow-sm"
          title="Manage Files (Local & HA)"
        >
          <FolderOpen size={18} />
          <span className="text-sm font-bold">File Management</span>
        </button>

        <button
          onClick={onOpenSettings}
          className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-slate-100 text-slate-600 transition-colors relative"
        >
          <Settings size={18} />
          <span className="text-sm font-medium hidden md:inline">Settings</span>
          {updateAvailable && (
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border border-white" />
          )}
        </button>
      </div>
    </div>
  );
};
