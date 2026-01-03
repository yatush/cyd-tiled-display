import { useState, useEffect, useRef } from 'react';

export const IconPicker = ({ value, onChange, icons, onFocus }: { value: string, onChange: (v: string) => void, icons: {value: string, label: string, char?: string}[], onFocus?: () => void }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const wrapperRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
      if (isOpen && searchInputRef.current) {
          searchInputRef.current.focus();
      }
  }, [isOpen]);

  const filteredIcons = icons.filter(icon => 
    icon.label.toLowerCase().includes(search.toLowerCase())
  );

  const getDisplayChar = (val: string) => {
      let cleanVal = val;
      if (cleanVal.startsWith('"') && cleanVal.endsWith('"')) {
          cleanVal = cleanVal.slice(1, -1);
      }

      const found = icons.find(i => i.value === cleanVal);
      if (found && found.char) return found.char;
      // Fallback for manual entry or if char not found
      if (cleanVal.startsWith('\\U')) {
          try {
              const hex = cleanVal.substring(2);
              return String.fromCodePoint(parseInt(hex, 16));
          } catch (e) { return cleanVal; }
      }
      return cleanVal;
  };

  const selectedIcon = icons.find(i => i.value === value);
  const displayLabel = selectedIcon ? selectedIcon.label : (value || 'Select icon...');

  return (
    <div className="relative" ref={wrapperRef}>
      <div 
        className="flex gap-2 items-center border rounded p-1 bg-white cursor-pointer hover:border-blue-400"
        onClick={() => {
            setIsOpen(!isOpen);
            if (!isOpen && onFocus) onFocus();
        }}
      >
        <div className="w-6 h-6 flex-shrink-0 flex items-center justify-center bg-slate-100 rounded text-lg" style={{ fontFamily: '"Material Symbols Outlined"' }}>
            {getDisplayChar(value)}
        </div>
        <span className="text-xs flex-1 truncate text-slate-700">{displayLabel}</span>
      </div>
      
      {isOpen && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border rounded shadow-lg p-2 w-64">
            <input 
                ref={searchInputRef}
                type="text"
                className="w-full border rounded p-1 text-xs mb-2"
                placeholder="Search icons..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onClick={(e) => e.stopPropagation()}
            />
            <div className="grid grid-cols-5 gap-1 max-h-48 overflow-y-auto">
                {filteredIcons.map((icon, idx) => (
                    <button
                        key={idx}
                        className="flex flex-col items-center justify-center p-1 hover:bg-blue-50 rounded aspect-square"
                        onClick={() => {
                            onChange(icon.value);
                            setIsOpen(false);
                        }}
                        title={icon.label}
                    >
                        <span className="text-xl" style={{ fontFamily: '"Material Symbols Outlined"' }}>{getDisplayChar(icon.value)}</span>
                    </button>
                ))}
            </div>
             {filteredIcons.length === 0 && (
                <div className="p-2 text-center text-xs text-slate-400">No icons found</div>
            )}
        </div>
      )}
    </div>
  );
};

export const ColorPicker = ({ value, onChange, colors, onFocus }: { value: string, onChange: (v: string) => void, colors: {id: string, value: string}[], onFocus?: () => void }) => {
    const [isOpen, setIsOpen] = useState(false);
    const wrapperRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const getPreviewColor = (val: string) => {
        const found = colors.find(c => c.id === val);
        if (found) return found.value;
        
        const match = val.match(/Color\((\d+),\s*(\d+),\s*(\d+)\)/);
        if (match) {
            const r = parseInt(match[1]);
            const g = parseInt(match[2]);
            const b = parseInt(match[3]);
            return `rgb(${r},${g},${b})`;
        }
        return '#fff';
    };

    const getHexForPicker = (val: string) => {
        const found = colors.find(c => c.id === val);
        if (found) {
             // Try to convert found value (which might be hex or rgb) to hex
             if (found.value.startsWith('#')) return found.value;
             // If it's rgb(), parse it
             const rgbMatch = found.value.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
             if (rgbMatch) {
                 const r = parseInt(rgbMatch[1]);
                 const g = parseInt(rgbMatch[2]);
                 const b = parseInt(rgbMatch[3]);
                 return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
             }
             return '#000000';
        }

        const match = val.match(/Color\((\d+),\s*(\d+),\s*(\d+)\)/);
        if (match) {
            const r = parseInt(match[1]);
            const g = parseInt(match[2]);
            const b = parseInt(match[3]);
            return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
        }
        return '#000000';
    };

    const hexToColorFunc = (hex: string) => {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return \`Color(\${r},\${g},\${b})\`;
    };

    const previewColor = getPreviewColor(value);
    const pickerValue = getHexForPicker(value);

    return (
        <div className="relative" ref={wrapperRef}>
            <div 
                className="flex gap-2 items-center border rounded p-1 bg-white cursor-pointer hover:border-blue-400"
                onClick={() => {
                    setIsOpen(!isOpen);
                    if (!isOpen && onFocus) onFocus();
                }}
            >
                <div 
                    className="w-4 h-4 rounded border border-slate-200 shadow-sm" 
                    style={{ backgroundColor: previewColor }}
                />
                <span className="text-xs flex-1 truncate">{value || 'Select color...'}</span>
            </div>
            
            {isOpen && (
                <div className="absolute z-50 top-full left-0 w-64 mt-1 max-h-64 overflow-y-auto bg-white border rounded shadow-lg p-2">
                    <div className="mb-2 pb-2 border-b">
                        <label className="block text-[10px] text-slate-500 uppercase mb-1">Custom Color</label>
                        <div className="flex gap-2 items-center">
                            <input 
                                type="color" 
                                className="w-8 h-8 p-0 border-0 rounded cursor-pointer"
                                value={pickerValue}
                                onChange={(e) => {
                                    onChange(hexToColorFunc(e.target.value));
                                }}
                            />
                            <span className="text-xs text-slate-600 font-mono flex-1 truncate">
                                {value.startsWith('Color(') ? value : 'Pick custom...'}
                            </span>
                            <button 
                                className="px-2 py-1 bg-blue-500 text-white text-xs rounded hover:bg-blue-600"
                                onClick={() => setIsOpen(false)}
                            >
                                Pick
                            </button>
                        </div>
                    </div>

                    <label className="block text-[10px] text-slate-500 uppercase mb-1">Presets</label>
                    <div className="space-y-1">
                        {colors.map(c => (
                            <div 
                                key={c.id}
                                className="flex items-center gap-2 p-1 hover:bg-blue-50 cursor-pointer rounded"
                                onClick={() => {
                                    onChange(c.id);
                                    setIsOpen(false);
                                }}
                            >
                                <div 
                                    className="w-4 h-4 rounded border border-slate-200" 
                                    style={{ backgroundColor: c.value }}
                                />
                                <span className="text-xs">{c.id}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
