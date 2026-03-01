import { useState } from 'react';
import { X } from 'lucide-react';

export const NewPageDialog = ({ isOpen, onClose, onAdd, existingIds }: { isOpen: boolean, onClose: () => void, onAdd: (id: string) => void, existingIds: string[] }) => {
  const [pageId, setPageId] = useState('');
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    const trimmedId = pageId.trim();

    // Validation
    if (!trimmedId) {
        setError('Page ID cannot be empty');
        return;
    }
    if (!/^[a-zA-Z0-9_]+$/.test(trimmedId)) {
        setError('Page ID can only contain letters, numbers, and underscores');
        return;
    }
    if (existingIds.includes(trimmedId)) {
        setError('Page ID already exists');
        return;
    }

    onAdd(trimmedId);
    setPageId('');
    setError('');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[200]" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-80 p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
            <h3 className="font-bold text-lg">Add New Page</h3>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
            </button>
        </div>
        
        <form onSubmit={handleSubmit}>
            <div className="mb-4">
                <label className="block text-xs font-medium text-slate-600 mb-1">Page ID</label>
                <input 
                    type="text" 
                    value={pageId}
                    onChange={e => {
                        setPageId(e.target.value);
                        setError('');
                    }}
                    className="w-full border rounded p-2 text-sm focus:ring-2 ring-blue-200 outline-none"
                    placeholder="e.g. settings_page"
                    autoFocus
                />
                {error && <p className="text-red-500 text-xs mt-1">{error}</p>}
            </div>
            
            <div className="flex justify-end gap-2">
                <button 
                    type="button" 
                    onClick={onClose}
                    className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 rounded"
                >
                    Cancel
                </button>
                <button 
                    type="submit"
                    className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                    Add Page
                </button>
            </div>
        </form>
      </div>
    </div>
  );
};
