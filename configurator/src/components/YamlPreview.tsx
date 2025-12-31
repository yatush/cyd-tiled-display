import { useEffect, useRef, useMemo } from 'react';
import { Download } from 'lucide-react';
import { Config } from '../types';
import { generateYaml } from '../utils/yamlGenerator';

interface YamlPreviewProps {
  config: Config;
  activePageId: string;
  selectedTileId: string | null;
  onCopyYaml: () => void;
}

export const YamlPreview: React.FC<YamlPreviewProps> = ({ config, activePageId, selectedTileId, onCopyYaml }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeSectionRef = useRef<HTMLDivElement>(null);
  const selectedTileRef = useRef<HTMLDivElement>(null);

  const { lines, activeRange, selectedTileRange } = useMemo(() => {
    const yaml = generateYaml(config, true); // Include IDs for highlighting
    const lines = yaml.split('\n');
    
    let start = -1;
    let end = -1;

    // Find page range
    const escapedId = activePageId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const startPattern = new RegExp(`^\\s*-\\s*id:\\s*(["']?)${escapedId}\\1\\s*$`);
    
    for (let i = 0; i < lines.length; i++) {
      if (start === -1) {
        if (startPattern.test(lines[i])) {
          start = i;
        }
      } else {
        const line = lines[i];
        const trimmed = line.trim();
        if (trimmed.startsWith('- id:')) {
           end = i;
           break;
        }
        if (line.length > 0 && !line.startsWith(' ') && !line.startsWith('-')) {
            end = i;
            break;
        }
      }
    }
    if (start !== -1 && end === -1) end = lines.length;

    // Find selected tile range
    let tileStart = -1;
    let tileEnd = -1;
    if (selectedTileId) {
        const tileIdPattern = new RegExp(`^\\s*__id:\\s*(["']?)${selectedTileId}\\1\\s*$`);
        for (let i = start; i < end; i++) {
            if (tileIdPattern.test(lines[i])) {
                const idLineIndent = lines[i].search(/\S/);
                
                // Find start: first line backwards starting with '-' with indent < idLineIndent
                for (let j = i; j >= start; j--) {
                    const currentIndent = lines[j].search(/\S/);
                    if (lines[j].trim().startsWith('-') && currentIndent < idLineIndent) {
                        tileStart = j;
                        break;
                    }
                }

                if (tileStart !== -1) {
                    const startIndent = lines[tileStart].search(/\S/);
                    // Find end: first line forwards with indent <= startIndent
                    for (let j = tileStart + 1; j < end; j++) {
                        const trimmed = lines[j].trim();
                        if (trimmed.length === 0) continue;
                        
                        const currentIndent = lines[j].search(/\S/);
                        if (currentIndent < startIndent) {
                            tileEnd = j;
                            break;
                        }
                        if (currentIndent === startIndent) {
                            // If it's another list item or a new key at the same level, stop
                            tileEnd = j;
                            break;
                        }
                    }
                }
                if (tileEnd === -1) tileEnd = end;
                break;
            }
        }
    }

    return { lines, activeRange: { start, end }, selectedTileRange: { start: tileStart, end: tileEnd } };
  }, [config, activePageId, selectedTileId]);

  useEffect(() => {
    const target = (selectedTileId && selectedTileRef.current) ? selectedTileRef.current : activeSectionRef.current;
    if (target && containerRef.current) {
      setTimeout(() => {
          target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 100);
    }
  }, [activePageId, selectedTileId, activeRange.start, selectedTileRange.start]);

  return (
    <div className="absolute inset-0 overflow-hidden bg-slate-50">
      <div className="absolute top-4 right-6 z-10">
        <button 
          onClick={onCopyYaml}
          className="flex items-center gap-2 bg-slate-900/90 text-white px-3 py-1.5 rounded hover:bg-slate-800 text-xs font-medium transition-colors shadow-lg backdrop-blur-sm"
        >
          <Download size={14} /> Copy YAML
        </button>
      </div>
      <div className="h-full p-4 overflow-auto" ref={containerRef}>
        <div className="font-mono text-sm">
          {lines.map((line, i) => {
            const trimmed = line.trim();
            if (trimmed.startsWith('__id:') || trimmed.startsWith('- __id:')) return null; // Hide internal ID

            const isActive = i >= activeRange.start && i < activeRange.end;
            const isSelected = i >= selectedTileRange.start && i < selectedTileRange.end;
            const isStart = i === activeRange.start;
            const isTileStart = i === selectedTileRange.start;
            
            return (
              <div 
                key={i} 
                ref={isTileStart ? selectedTileRef : (isStart ? activeSectionRef : null)}
                className={`${isSelected ? 'bg-blue-200 border-l-4 border-blue-600 -ml-1' : (isActive ? 'bg-blue-50' : '')} px-2 whitespace-pre-wrap transition-colors duration-200`}
              >
                {line || '\n'}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
