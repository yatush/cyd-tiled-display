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
  FolderOpen
} from 'lucide-react';
import { ConnectionType, HaStatus } from '../hooks/useHaConnection';

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
  updateAvailable
}) => {
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
