import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle, Download, Settings, Wrench } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

type ToolchainPhase =
  | 'starting'
  | 'downloading'
  | 'extracting'
  | 'fixing'
  | 'building'
  | 'ready'
  | 'error';

interface ToolchainStatus {
  phase:    ToolchainPhase;
  progress: number;   // 0-100
  message:  string;
  fallback: boolean;  // true when falling back to local compile
  error?:   string;
}

// ─── Phase metadata ──────────────────────────────────────────────────────────

const PHASE_ICON: Record<ToolchainPhase, React.ReactNode> = {
  starting:    <Settings  className="w-8 h-8 animate-spin text-blue-400" />,
  downloading: <Download  className="w-8 h-8 animate-bounce text-blue-400" />,
  extracting:  <Settings  className="w-8 h-8 animate-spin text-blue-400" />,
  fixing:      <Wrench    className="w-8 h-8 animate-pulse text-blue-400" />,
  building:    <Settings  className="w-8 h-8 animate-spin text-amber-400" />,
  ready:       <CheckCircle className="w-8 h-8 text-green-400" />,
  error:       <AlertTriangle className="w-8 h-8 text-red-400" />,
};

const PHASE_TITLE: Record<ToolchainPhase, string> = {
  starting:    'Checking toolchain...',
  downloading: 'Downloading toolchain',
  extracting:  'Extracting toolchain',
  fixing:      'Configuring toolchain',
  building:    'Building toolchain locally',
  ready:       'Toolchain ready',
  error:       'Toolchain setup failed',
};

// ─── Component ───────────────────────────────────────────────────────────────

interface ToolchainInitScreenProps {
  /** Called once the toolchain is ready and the UI can proceed. */
  onReady: () => void;
}

export function ToolchainInitScreen({ onReady }: ToolchainInitScreenProps) {
  const [status, setStatus] = useState<ToolchainStatus>({
    phase:    'starting',
    progress: 0,
    message:  'Checking toolchain status...',
    fallback: false,
  });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      while (!cancelled) {
        try {
          const res = await fetch('/api/toolchain/status');
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data: ToolchainStatus = await res.json();

          if (!cancelled) {
            setStatus(data);
            if (data.phase === 'ready') {
              // Short delay so users see the "ready" state before the UI appears
              await new Promise(r => setTimeout(r, 800));
              if (!cancelled) onReady();
              return;
            }
          }
        } catch {
          // Server not yet ready — keep polling
        }
        await new Promise(r => setTimeout(r, 2000));
      }
    }

    poll();
    return () => { cancelled = true; };
  }, [onReady]);

  const { phase, progress, message, fallback, error } = status;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/90 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4">

        {/* Icon + title */}
        <div className="flex items-center gap-4 mb-6">
          {PHASE_ICON[phase]}
          <div>
            <h2 className="text-white font-semibold text-lg leading-tight">
              {PHASE_TITLE[phase]}
            </h2>
            <p className="text-gray-400 text-sm mt-0.5">CYD Tiled Display</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mb-3">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-gray-300 text-sm truncate pr-4">{message}</span>
            <span className="text-gray-400 text-sm shrink-0 font-mono">{progress}%</span>
          </div>
          <div className="w-full h-2.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                phase === 'building' ? 'bg-amber-500' :
                phase === 'ready'    ? 'bg-green-500' :
                phase === 'error'    ? 'bg-red-500'   : 'bg-blue-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Fallback warning */}
        {fallback && phase !== 'ready' && (
          <div className="mt-4 flex gap-2.5 bg-amber-950/60 border border-amber-700/50 rounded-lg p-3">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-amber-300 text-xs leading-relaxed">
              <span className="font-semibold">No pre-built release available.</span>
              {' '}Building the toolchain locally — this takes 10–15 minutes
              on first install. Subsequent starts will be instant.
            </div>
          </div>
        )}

        {/* Error detail */}
        {phase === 'error' && error && (
          <div className="mt-4 bg-red-950/60 border border-red-700/50 rounded-lg p-3">
            <p className="text-red-300 text-xs font-mono break-all">{error}</p>
          </div>
        )}

        {/* Ready banner */}
        {phase === 'ready' && (
          <div className="mt-4 flex gap-2.5 bg-green-950/60 border border-green-700/50 rounded-lg p-3">
            <CheckCircle className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />
            <p className="text-green-300 text-xs leading-relaxed">
              Toolchain is ready. Loading configurator...
              {fallback && ' (toolchain was built locally this time; future updates will download faster)'}
            </p>
          </div>
        )}

        {/* Hint for long operations */}
        {(phase === 'downloading' || phase === 'extracting' || phase === 'building') && (
          <p className="mt-5 text-gray-600 text-xs text-center">
            You can check detailed logs in <span className="font-mono">/tmp/toolchain_setup.log</span>
          </p>
        )}
      </div>
    </div>
  );
}
