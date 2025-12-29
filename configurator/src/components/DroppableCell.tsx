import { useDroppable } from '@dnd-kit/core';

export const DroppableCell = ({ x, y, children, onSelect }: { x: number, y: number, children?: React.ReactNode, onSelect?: () => void }) => {
  const { isOver, setNodeRef } = useDroppable({
    id: `cell-${x}-${y}`,
    data: { x, y }
  });

  return (
    <div 
      ref={setNodeRef}
      className={`relative border-2 border-dashed rounded flex items-center justify-center h-full w-full
        ${isOver ? 'bg-green-100 border-green-500' : 'border-slate-300 hover:bg-slate-50'}
      `}
      onClick={onSelect}
    >
      {children || <span className="text-slate-300 text-xs select-none pointer-events-none">Empty</span>}
    </div>
  );
};
