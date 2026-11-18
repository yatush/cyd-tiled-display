import { KeyboardEvent } from 'react';
import { YamlDraft } from '../hooks/useYamlDraft';

export function handleYamlKeyDown(
  event: KeyboardEvent<HTMLTextAreaElement>,
  text: string,
  onChangeText: (nextText: string) => void
) {
  if ((event.key !== 'Enter' && event.key !== 'Tab') || event.ctrlKey || event.metaKey || event.altKey) return;
  const input = event.currentTarget;
  const start = input.selectionStart;
  const end = input.selectionEnd;
  if (event.shiftKey && (event.key !== 'Tab' || start === end)) return;

  if (event.key === 'Tab' && start !== end) {
    const lineStart = text.lastIndexOf('\n', start - 1) + 1;
    const lastSelected = text[end - 1] === '\n' ? end - 1 : end;
    const lineEnd = text.indexOf('\n', lastSelected);
    const blockEnd = lineEnd === -1 ? text.length : lineEnd;
    const block = text.slice(lineStart, blockEnd).split('\n')
      .map(line => (event.shiftKey ? line.replace(/^ {1,2}/, '') : `  ${line}`)).join('\n');
    event.preventDefault();
    onChangeText(text.slice(0, lineStart) + block + text.slice(blockEnd));
    requestAnimationFrame(() => {
      input.selectionStart = lineStart;
      input.selectionEnd = lineStart + block.length;
    });
    return;
  }

  let insertion = '  ';
  if (event.key === 'Enter') {
    const line = text.slice(text.lastIndexOf('\n', start - 1) + 1, start);
    const spaces = line.match(/^ */)?.[0] ?? '';
    const extra = /:\s*$/.test(line) ? (/^\s*-\s+/.test(line) ? '    ' : '  ') : '';
    insertion = `\n${spaces}${extra}`;
  }
  event.preventDefault();
  onChangeText(text.slice(0, start) + insertion + text.slice(end));
  requestAnimationFrame(() => {
    input.selectionStart = input.selectionEnd = start + insertion.length;
  });
}

export const YamlModeToggle = ({
  mode,
  onChange,
  hasDraft,
  ariaLabel,
}: {
  mode: 'form' | 'yaml';
  onChange: (mode: 'form' | 'yaml') => void;
  hasDraft: boolean;
  ariaLabel: string;
}) => (
  <div className="flex gap-2" aria-label={ariaLabel}>
    <button
      type="button"
      onClick={() => onChange('form')}
      className={`px-3 py-1 rounded text-sm ${mode === 'form' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'}`}
    >Form</button>
    <button
      type="button"
      onClick={() => onChange('yaml')}
      className={`px-3 py-1 rounded text-sm ${mode === 'yaml' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'}`}
    >YAML{hasDraft ? ' *' : ''}</button>
  </div>
);

export const YamlEditorSection = ({
  id,
  label,
  hint,
  value,
  error,
  onChange,
  onApply,
  onCancel,
  minHeightClass = 'min-h-[300px]',
}: {
  id: string;
  label: string;
  hint: string;
  value: string;
  error: string;
  onChange: (text: string) => void;
  onApply: () => void;
  onCancel: () => void;
  minHeightClass?: string;
}) => (
  <div className="space-y-2">
    <label htmlFor={id} className="block text-xs font-medium text-slate-700">{label}</label>
    <p className="text-xs text-slate-500">{hint}</p>
    <textarea
      id={id}
      spellCheck={false}
      value={value}
      onChange={event => onChange(event.target.value)}
      onKeyDown={event => handleYamlKeyDown(event, value, onChange)}
      className={`w-full ${minHeightClass} border-2 border-slate-200 rounded-lg p-2 text-xs font-mono focus:border-blue-500 outline-none`}
    />
    {error && <p role="alert" className="text-xs text-red-600 whitespace-pre-wrap">{error}</p>}
    <div className="flex gap-2">
      <button type="button" onClick={onApply} className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm">Apply</button>
      <button type="button" onClick={onCancel} className="px-3 py-1.5 rounded bg-slate-100 text-slate-700 text-sm">Cancel</button>
    </div>
  </div>
);

export const OrphanDraftsBanner = ({
  tileDrafts,
  pageDrafts,
  onDiscardTile,
  onDiscardPage,
}: {
  tileDrafts: [string, YamlDraft][];
  pageDrafts: [string, YamlDraft][];
  onDiscardTile: (id: string) => void;
  onDiscardPage: (id: string) => void;
}) => {
  if (tileDrafts.length === 0 && pageDrafts.length === 0) return null;
  const renderGroup = (
    kind: 'tile' | 'page',
    items: [string, YamlDraft][],
    onDiscard: (id: string) => void
  ) => (
    <>
      <p>These YAML drafts belong to {kind}s no longer in the project. Copy or discard them before leaving.</p>
      {items.map(([id, orphan]) => (
        <details key={`${kind}-${id}`}>
          <summary className="cursor-pointer">Draft for removed {kind} {id}</summary>
          <textarea aria-label={`Draft for removed ${kind} ${id}`} readOnly value={orphan.text} className="w-full min-h-[100px] mt-1 p-1 font-mono border rounded bg-white" />
          <button
            type="button"
            className="underline"
            onClick={() => {
              if (!confirm('Discard this YAML draft?')) return;
              onDiscard(id);
            }}
          >Discard draft</button>
        </details>
      ))}
    </>
  );

  return (
    <div className="p-3 bg-amber-50 text-xs text-amber-800 space-y-2">
      {tileDrafts.length > 0 && renderGroup('tile', tileDrafts, onDiscardTile)}
      {pageDrafts.length > 0 && renderGroup('page', pageDrafts, onDiscardPage)}
    </div>
  );
};
