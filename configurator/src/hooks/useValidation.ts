import { useState, useEffect, useRef } from 'react';
import { Config } from '../types';
import { generateYaml } from '../utils/yamlGenerator';
import { apiFetch } from '../utils/api';

/** Parse JSON from a Response safely – returns null when the body is empty or not valid JSON. */
async function safeJson(response: Response): Promise<any | null> {
  try {
    const text = await response.text();
    if (!text || !text.trim()) return null;
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function useValidation(config: Config) {
  const [isValidating, setIsValidating] = useState(false);
  const [validationStatus, setValidationStatus] = useState<{success: boolean, error?: string} | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationOutput, setGenerationOutput] = useState<{success?: boolean, cpp?: string[], error?: string, type?: string} | null>(null);
  
  const lastValidationTimeRef = useRef<number>(0);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsValidating(true);

    const runValidation = async () => {
      lastValidationTimeRef.current = Date.now();
      try {
        const yamlContent = generateYaml(config);
        const response = await apiFetch('/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/yaml' },
          body: yamlContent
        });
        
        if (!isMounted) return;

        const result = await safeJson(response);
        if (!result) {
          setValidationStatus({ success: false, error: `Server error (HTTP ${response.status})` });
        } else if (result.error) {
          setValidationStatus({ success: false, error: result.error });
        } else {
          setValidationStatus({ success: true });
        }
      } catch (err) {
        if (!isMounted) return;
        setValidationStatus({ success: false, error: 'Connection error' });
      } finally {
        if (isMounted) {
          setIsValidating(false);
        }
      }
    };

    const now = Date.now();
    const timeSinceLast = now - lastValidationTimeRef.current;
    const minInterval = 1000;

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    if (timeSinceLast >= minInterval) {
      runValidation();
    } else {
      const delay = minInterval - timeSinceLast;
      timeoutRef.current = setTimeout(runValidation, delay);
    }

    return () => {
      isMounted = false;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [config]);

  const handleGenerate = async (onSuccess?: () => void) => {
    setIsGenerating(true);
    setGenerationOutput(null);
    if (onSuccess) onSuccess();
    try {
      const yamlContent = generateYaml(config);
      const response = await apiFetch('/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/yaml' },
        body: yamlContent
      });
      const result = await safeJson(response);
      if (!result) {
        setGenerationOutput({ error: `Server returned an empty response (HTTP ${response.status}). The server may be starting up or restarting.`, type: 'network_error' });
      } else {
        setGenerationOutput(result);
      }
    } catch (err) {
      setGenerationOutput({ error: (err as Error).message, type: 'network_error' });
    } finally {
      setIsGenerating(false);
    }
  };

  return {
    isValidating,
    validationStatus,
    isGenerating,
    generationOutput,
    handleGenerate,
    setGenerationOutput
  };
}
