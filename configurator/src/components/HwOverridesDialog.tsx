import React, { useState, useEffect } from 'react';
import { X, Save, RefreshCw, CheckCircle, AlertTriangle, ChevronRight } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface OverrideChange {
  key: string;
  value: unknown;
}

interface OverrideEntry {
  component_type: string;
  id: string;
  id_found: boolean;
  changes: OverrideChange[];
}

interface ValidationResult {
  overrides: OverrideEntry[];
  parse_error: string | null;
}

interface HwOverridesDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** Called after a successful save so the caller can refresh its validation state */
  onSaved?: () => void;
}

const HW_OVERRIDES_PATH = 'lib/hw_overrides.yaml';

function ValidationDisplay({ result }: { result: ValidationResult }) {
  if (result.parse_error) {
    return (
      <div className="mt-3 p-3 rounded-lg bg-red-50 border border-red-200">
        <div className="flex items-center gap-1.5 text-red-700 font-bold text-xs mb-1">
          <AlertTriangle size={13} /> Parse error
        </div>
        <pre className="text-[10px] text-red-600 whitespace-pre-wrap font-mono">{result.parse_error}</pre>
      </div>
    );
  }

  if (result.overrides.length === 0) {
    return (
      <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-500 flex items-center gap-2">
        <CheckCircle size={13} className="text-slate-400" />
        No active overrides found — all lines are comments.
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2">
      {result.overrides.map((entry, i) => (
        <div
          key={i}
          className={`p-3 rounded-lg border text-xs ${
            entry.id_found
              ? 'bg-green-50 border-green-200'
              : 'bg-yellow-50 border-yellow-200'
          }`}
        >
          <div className="flex items-center gap-1.5 font-bold mb-1.5">
            {entry.id_found
              ? <CheckCircle size={13} className="text-green-600 flex-shrink-0" />
              : <AlertTriangle size={13} className="text-yellow-600 flex-shrink-0" />
            }
            <span className={entry.id_found ? 'text-green-800' : 'text-yellow-800'}>
              {entry.component_type}
            </span>
            <ChevronRight size={11} className="text-slate-400" />
            <span className="font-mono">{entry.id}</span>
            {!entry.id_found && (
              <span className="ml-auto text-yellow-700 font-normal">ID not found — may fail to compile</span>
            )}
          </div>
          <div className="space-y-0.5 pl-5">
            {entry.changes.map((c, j) => (
              <div key={j} className="font-mono text-slate-600">
                <span className="text-slate-400">{c.key}:</span>{' '}
                <span className="text-slate-800">{String(c.value)}</span>
              </div>
            ))}
            {entry.changes.length === 0 && (
              <div className="text-slate-400 italic">no keys</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export const HwOverridesDialog: React.FC<HwOverridesDialogProps> = ({ isOpen, onClose, onSaved }) => {
  const [content, setContent] = useState('');
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);


  useEffect(() => {
    if (!isOpen) return;
    setLoadState('loading');
    setValidationResult(null);
    setSaveError(null);
    apiFetch(`/load?path=${encodeURIComponent(HW_OVERRIDES_PATH)}&raw=1`)
      .then(async r => {
        if (r.ok) {
          setContent(await r.text());
        } else {
          // File doesn't exist yet — start with empty content
          setContent('');
        }
        setLoadState('ready');
      })
      .catch(() => {
        setContent('');
        setLoadState('ready');
      });
  }, [isOpen]);

  const handleValidate = async () => {
    setValidating(true);
    setValidationResult(null);
    try {
      const res = await apiFetch('/hw_overrides/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml_text: content }),
      });
      if (res.ok) {
        setValidationResult(await res.json());
      }
    } finally {
      setValidating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await apiFetch('/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config: content, path: HW_OVERRIDES_PATH, raw: true }),
      });
      if (res.ok) {
        onSaved?.();
        onClose();
      } else {
        const err = await res.json().catch(() => ({}));
        setSaveError(err.error || 'Save failed');
      }
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-[300] p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[85vh] animate-in fade-in zoom-in duration-200"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b bg-slate-50 flex-shrink-0">
          <h2 className="font-bold text-slate-800">Hardware Overrides</h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-200 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 min-h-0">
          <p className="text-xs text-slate-500">
            Edit <span className="font-mono text-slate-700">lib/hw_overrides.yaml</span>. Use ESPHome's{' '}
            <span className="font-mono text-slate-700">!extend</span> tag to override any component by its ID.
            This file is never overwritten by the configurator.
          </p>

          {loadState === 'loading' && (
            <div className="flex items-center gap-2 text-slate-500 text-sm py-8 justify-center">
              <RefreshCw size={16} className="animate-spin" /> Loading…
            </div>
          )}

          {loadState !== 'loading' && (
            <textarea
              className="w-full flex-1 font-mono text-xs border border-slate-200 rounded-lg p-3 resize-none focus:outline-none focus:border-blue-400 bg-slate-50 min-h-[280px]"
              value={content}
              onChange={e => { setContent(e.target.value); setValidationResult(null); }}
              spellCheck={false}
            />
          )}

          {validationResult && <ValidationDisplay result={validationResult} />}

          {saveError && (
            <div className="p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">{saveError}</div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 p-4 border-t bg-slate-50 flex-shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={handleValidate}
              disabled={validating || loadState !== 'ready'}
              className="flex items-center gap-2 px-3 py-2 text-xs font-bold border border-slate-300 rounded-lg hover:bg-slate-100 disabled:opacity-50 transition-colors text-slate-700"
            >
              {validating
                ? <><RefreshCw size={13} className="animate-spin" /> Checking…</>
                : <><CheckCircle size={13} /> Check Overrides</>
              }
            </button>

          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || loadState !== 'ready'}
              className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
