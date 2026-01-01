import { useState, useEffect } from 'react';
import { Config } from '../types';
import { generateYaml } from '../utils/yamlGenerator';
import { apiFetch } from '../utils/api';

export function useValidation(config: Config) {
  const [isValidating, setIsValidating] = useState(false);
  const [validationStatus, setValidationStatus] = useState<{success: boolean, error?: string} | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationOutput, setGenerationOutput] = useState<{success?: boolean, cpp?: string[], error?: string, type?: string} | null>(null);

  useEffect(() => {
    const timer = setTimeout(async () => {
      setIsValidating(true);
      try {
        const yamlContent = generateYaml(config);
        const response = await apiFetch('/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/yaml' },
          body: yamlContent
        });
        const result = await response.json();
        if (result.error) {
          setValidationStatus({ success: false, error: result.error });
        } else {
          setValidationStatus({ success: true });
        }
      } catch (err) {
        setValidationStatus({ success: false, error: 'Connection error' });
      } finally {
        setIsValidating(false);
      }
    }, 5000);

    return () => clearTimeout(timer);
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
      const result = await response.json();
      setGenerationOutput(result);
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
