import { useState, useEffect } from 'react';
import { Folder, File, ChevronRight, ChevronLeft, Home } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface FileItem {
  name: string;
  is_dir: boolean;
  path: string;
}

export const FileExplorer = ({ onSelect, onSelectDir, currentPath = '' }: { 
  onSelect: (path: string) => void,
  onSelectDir?: (path: string) => void,
  currentPath?: string 
}) => {
  const [path, setPath] = useState(currentPath || 'monitor_config');
  const [items, setItems] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = async (targetPath: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/files?path=${encodeURIComponent(targetPath)}`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items);
        setPath(data.current_path);
      } else {
        setError('Failed to load files');
      }
    } catch (err) {
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles(path);
  }, []);

  const handleDirClick = (dirPath: string) => {
    fetchFiles(dirPath);
  };

  const handleFileClick = (filePath: string) => {
    onSelect(filePath);
  };

  const goUp = () => {
    const parts = path.split('/').filter(Boolean);
    parts.pop();
    fetchFiles(parts.join('/'));
  };

  return (
    <div className="flex flex-col h-full bg-white border rounded-lg overflow-hidden shadow-sm">
      <div className="bg-slate-50 p-2 border-b flex items-center gap-2 text-xs font-medium text-slate-600">
        <button onClick={() => fetchFiles('')} className="p-1 hover:bg-slate-200 rounded transition-colors">
          <Home size={14} />
        </button>
        <button onClick={goUp} disabled={!path} className="p-1 hover:bg-slate-200 rounded disabled:opacity-30 transition-colors">
          <ChevronLeft size={14} />
        </button>
        <div className="flex-1 truncate bg-white border px-2 py-1 rounded text-[10px] font-mono">
          /config/esphome/{path}
        </div>
        {onSelectDir && (
          <button 
            onClick={() => onSelectDir(path)}
            className="px-2 py-1 bg-blue-600 text-white rounded text-[10px] font-bold hover:bg-blue-700 transition-colors"
          >
            Select Folder
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-1">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-slate-400 text-xs">
            Loading...
          </div>
        ) : error ? (
          <div className="p-4 text-red-500 text-xs text-center">
            {error}
          </div>
        ) : (
          <div className="space-y-0.5">
            {items.map((item) => (
              <button
                key={item.path}
                onClick={() => item.is_dir ? handleDirClick(item.path) : handleFileClick(item.path)}
                className={`w-full flex items-center gap-2 p-2 rounded text-left transition-colors ${
                  item.is_dir ? 'hover:bg-blue-50 text-slate-700' : 'hover:bg-slate-100 text-slate-600'
                }`}
              >
                {item.is_dir ? (
                  <Folder size={14} className="text-blue-500 fill-blue-50" />
                ) : (
                  <File size={14} className="text-slate-400" />
                )}
                <span className="text-xs truncate flex-1">{item.name}</span>
                {item.is_dir && <ChevronRight size={12} className="text-slate-300" />}
              </button>
            ))}
            {items.length === 0 && (
              <div className="p-8 text-center text-slate-400 text-xs italic">
                Empty directory
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
