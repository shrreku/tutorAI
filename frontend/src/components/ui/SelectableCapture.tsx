import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

type SelectionAnchor = {
  text: string;
  x: number;
  y: number;
};

interface SelectableCaptureProps {
  children: ReactNode;
  onCapture: (text: string) => void;
  className?: string;
}

function serializeNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent || '';
  }

  if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) {
    return '';
  }

  if (node.nodeType === Node.ELEMENT_NODE) {
    const element = node as HTMLElement;
    const source = element.dataset.noteSource;
    if (source) return source;
    if (element.tagName === 'BR') return '\n';
  }

  const children = Array.from(node.childNodes).map(serializeNode).join('');
  if (node.nodeType !== Node.ELEMENT_NODE) return children;

  const element = node as HTMLElement;
  if (['P', 'DIV', 'LI', 'BLOCKQUOTE'].includes(element.tagName)) {
    return `${children}\n`;
  }

  return children;
}

function normalizeSelection(text: string) {
  return text
    .replace(/\u00a0/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+\n/g, '\n')
    .trim();
}

export default function SelectableCapture({ children, onCapture, className }: SelectableCaptureProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState<SelectionAnchor | null>(null);

  const clearSelectionState = useCallback(() => {
    setAnchor(null);
  }, []);

  const extractSelectedText = useCallback(() => {
    const selection = window.getSelection();
    const container = containerRef.current;
    if (!selection || !container || selection.rangeCount === 0 || selection.isCollapsed) {
      clearSelectionState();
      return;
    }

    const range = selection.getRangeAt(0);
    const commonAncestor = range.commonAncestorContainer;
    if (!container.contains(commonAncestor)) {
      clearSelectionState();
      return;
    }

    const fragment = range.cloneContents();
    const rawText = normalizeSelection(serializeNode(fragment));
    if (!rawText || rawText.length < 2) {
      clearSelectionState();
      return;
    }

    const rect = range.getBoundingClientRect();
    if (!rect.width && !rect.height) {
      clearSelectionState();
      return;
    }

    setAnchor({
      text: rawText,
      x: rect.right,
      y: rect.top - 8,
    });
  }, [clearSelectionState]);

  useEffect(() => {
    const handleSelectionChange = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) {
        clearSelectionState();
      }
    };

    const handleScroll = () => clearSelectionState();

    document.addEventListener('selectionchange', handleSelectionChange);
    window.addEventListener('scroll', handleScroll, true);
    window.addEventListener('resize', handleScroll);

    return () => {
      document.removeEventListener('selectionchange', handleSelectionChange);
      window.removeEventListener('scroll', handleScroll, true);
      window.removeEventListener('resize', handleScroll);
    };
  }, [clearSelectionState]);

  const buttonStyle = useMemo(() => {
    if (!anchor) return undefined;
    return {
      left: `${Math.max(12, anchor.x - 132)}px`,
      top: `${Math.max(12, anchor.y - 40)}px`,
    };
  }, [anchor]);

  return (
    <>
      <div
        ref={containerRef}
        className={className}
        onMouseUp={extractSelectedText}
        onKeyUp={extractSelectedText}
        onTouchEnd={extractSelectedText}
      >
        {children}
      </div>
      {anchor ? (
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            onCapture(anchor.text);
            window.getSelection()?.removeAllRanges();
            clearSelectionState();
          }}
          className="fixed z-[95] inline-flex items-center rounded-full border border-gold/25 bg-card px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.12em] text-gold shadow-lg transition-colors hover:bg-gold/10"
          style={buttonStyle}
        >
          Add to notes
        </button>
      ) : null}
    </>
  );
}
