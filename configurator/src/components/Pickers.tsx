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
                        <span className="text-xl" style={{ fontFamily: '"Material Symbols Outlined"' }}>{icon.char || icon.value}</span>
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

    const selectedColor = colors.find(c => c.id === value);

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
                    style={{ backgroundColor: selectedColor ? selectedColor.value : '#fff' }}
                />
                <span className="text-xs flex-1">{value || 'Select color...'}</span>
            </div>
            
            {isOpen && (
                <div className="absolute z-50 top-full left-0 right-0 mt-1 max-h-48 overflow-y-auto bg-white border rounded shadow-lg">
                    {colors.map(c => (
                        <div 
                            key={c.id}
                            className="flex items-center gap-2 p-1 hover:bg-blue-50 cursor-pointer"
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
            )}
        </div>
    );
};
