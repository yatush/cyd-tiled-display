import { useState, useEffect, useCallback } from 'react';

export interface YamlDraft {
  text: string;
  initialText: string;
  baseSnapshot: string;
}

export function useYamlDraft<T>({
  itemId,
  currentItem,
  generateYaml,
}: {
  itemId: string | undefined;
  currentItem: T | null | undefined;
  generateYaml: (item: T) => string;
}) {
  const [mode, setMode] = useState<'form' | 'yaml'>('form');
  const [drafts, setDrafts] = useState<Record<string, YamlDraft>>({});
  const [error, setError] = useState('');

  useEffect(() => {
    setError('');
  }, [itemId]);

  const draft = itemId ? drafts[itemId] : undefined;
  const yamlText = itemId && currentItem && mode === 'yaml'
    ? draft?.text ?? generateYaml(currentItem)
    : '';

  const updateText = useCallback((text: string) => {
    if (!itemId || !currentItem) return;
    const initialText = draft?.initialText ?? generateYaml(currentItem);
    setDrafts(current => {
      const next = { ...current };
      if (text === initialText) {
        delete next[itemId];
      } else {
        next[itemId] = {
          text,
          initialText,
          baseSnapshot: draft?.baseSnapshot ?? JSON.stringify(currentItem),
        };
      }
      return next;
    });
    setError('');
  }, [itemId, currentItem, draft, generateYaml]);

  const discard = useCallback(() => {
    if (!itemId) return;
    setDrafts(current => {
      const next = { ...current };
      delete next[itemId];
      return next;
    });
    setError('');
  }, [itemId]);

  const discardById = useCallback((id: string) => {
    setDrafts(current => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  }, []);

  const isStale = Boolean(draft && currentItem && draft.baseSnapshot !== JSON.stringify(currentItem));
  const hasDrafts = Object.keys(drafts).length > 0;
  const getOrphanDrafts = useCallback(
    (validIds: Set<string>) => Object.entries(drafts).filter(([id]) => !validIds.has(id)),
    [drafts]
  );

  return {
    mode,
    setMode,
    draft,
    yamlText,
    error,
    setError,
    updateText,
    discard,
    discardById,
    isStale,
    hasDrafts,
    getOrphanDrafts,
  };
}
