import { useState, useEffect } from 'react';

export function useSidebarResizing() {
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('leftSidebarWidth');
    return saved ? parseInt(saved, 10) : 256;
  });
  const [rightSidebarWidth, setRightSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('rightSidebarWidth');
    return saved ? parseInt(saved, 10) : 320;
  });
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  useEffect(() => {
    localStorage.setItem('leftSidebarWidth', leftSidebarWidth.toString());
  }, [leftSidebarWidth]);

  useEffect(() => {
    localStorage.setItem('rightSidebarWidth', rightSidebarWidth.toString());
  }, [rightSidebarWidth]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDraggingLeft) {
        setLeftSidebarWidth(Math.max(200, Math.min(600, e.clientX)));
      } else if (isDraggingRight) {
        setRightSidebarWidth(Math.max(200, Math.min(600, window.innerWidth - e.clientX)));
      }
    };

    const handleMouseUp = () => {
      setIsDraggingLeft(false);
      setIsDraggingRight(false);
    };

    if (isDraggingLeft || isDraggingRight) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    } else {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDraggingLeft, isDraggingRight]);

  return {
    leftSidebarWidth,
    rightSidebarWidth,
    setIsDraggingLeft,
    setIsDraggingRight,
    isDraggingLeft,
    isDraggingRight
  };
}
