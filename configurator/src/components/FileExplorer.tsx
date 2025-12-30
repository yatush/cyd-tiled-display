import { useState, useEffect } from 'react';
import { Folder, File, ChevronRight, ChevronLeft, Home, FolderPlus } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface FileItem {
  name: string;
  is_dir: boolean;
  path: string;
}

export const FileExplorer = ({ onSelect, onSelectDir, currentPath = '', selectedPath = '' }: { 
  onSelect: (path: string) => void,
  onSelectDir?: (path: string) => void,
  currentPath?: string,
  selectedPath?: string
}) => {
  const [path, setPath] = useState(currentPath || '');
  const [items, setItems] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isCreatingDir, setIsCreatingDir] = useState(false);
  const [newDirName, setNewDirName] = useState('');

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

  const handleCreateDir = async () => {
    if (!newDirName) return;
    const fullPath = path ? `${path}/${newDirName}` : newDirName;
    try {
      const res = await apiFetch('/mkdir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: fullPath })
      });
      if (res.ok) {
        setNewDirName('');
        setIsCreatingDir(false);
        fetchFiles(path);
      } else {
        alert('Failed to create directory');
      }
    } catch (err) {
      alert('Error creating directory');
    }
  };

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
        <div className="flex gap-1">
          <button 
            onClick={() => setIsCreatingDir(!isCreatingDir)}
            className="p-1 bg-slate-200 text-slate-600 rounded hover:bg-slate-300 transition-colors"
            title="New Folder"
          >
            <FolderPlus size={14} />
          </button>
          {onSelectDir && (
            <button 
              onClick={() => onSelectDir(path)}
              className="px-2 py-1 bg-blue-600 text-white rounded text-[10px] font-bold hover:bg-blue-700 transition-colors"
            >
              Select Folder
            </button>
          )}
        </div>
      </div>

      {isCreatingDir && (
        <div className="p-2 border-b bg-blue-50 flex gap-2">
          <input 
            type="text"
            value={newDirName}
            onChange={(e) => setNewDirName(e.target.value)}
            placeholder="Folder name..."
            className="flex-1 px-2 py-1 text-xs border rounded outline-none focus:ring-1 focus:ring-blue-500"
            autoFocus
            onKeyDown={(e) => e.key === 'Enter' && handleCreateDir()}
          />
          <button 
            onClick={handleCreateDir}
            className="px-2 py-1 bg-blue-600 text-white rounded text-[10px] font-bold"
          >
            Create
          </button>
          <button 
            onClick={() => setIsCreatingDir(false)}
            className="px-2 py-1 bg-slate-200 text-slate-600 rounded text-[10px] font-bold"
          >
            Cancel
          </button>
        </div>
      )}

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
                  item.is_dir 
                    ? 'hover:bg-blue-50 text-slate-700' 
                    : item.path === selectedPath
                      ? 'bg-blue-100 text-blue-700 border border-blue-200'
                      : 'hover:bg-slate-100 text-slate-600'
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
