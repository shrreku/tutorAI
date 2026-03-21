import { memo, type ReactNode } from 'react';
import katex from 'katex';

type StructuredContentBlock = {
  block_type: string;
  content: string;
  metadata?: Record<string, unknown>;
};

type RichTutorContentProps = {
  content: string;
  structuredContent?: StructuredContentBlock[] | null;
};

function renderMath(expression: string, displayMode: boolean, key: string) {
  const normalized = expression.trim();
  if (!normalized) return null;
  const sourceText = displayMode ? `$$${normalized}$$` : `$${normalized}$`;

  try {
    const html = katex.renderToString(normalized, {
      throwOnError: false,
      displayMode,
      strict: 'ignore',
      output: 'html',
      trust: false,
    });

    return (
      <span
        key={key}
        className={displayMode ? 'block tutor-math-display' : 'inline tutor-math-inline'}
        data-note-source={sourceText}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return (
      <code
        key={key}
        data-note-source={sourceText}
        className={displayMode
          ? 'tutor-math-display block overflow-x-auto rounded-xl border border-gold/15 bg-gold/[0.04] px-3 py-2 font-mono text-[0.95em] text-foreground'
          : 'tutor-math-inline rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground'}
      >
        {normalized}
      </code>
    );
  }
}

function normalizeInlineText(text: string) {
  return text.replace(/\u200B|\u200C|\u200D|\uFEFF/g, '');
}

function findInlineMathEnd(text: string, start: number) {
  for (let index = start; index < text.length; index += 1) {
    if (text[index] !== '$') continue;
    if (text[index - 1] === '\\') continue;
    return index;
  }
  return -1;
}

function renderInline(text: string): ReactNode[] {
  const normalizedText = normalizeInlineText(text);
  const tokens: ReactNode[] = [];
  let cursor = 0;
  let key = 0;

  const pushText = (value: string) => {
    if (!value) return;
    tokens.push(<span key={`text-${key++}`}>{value}</span>);
  };

  while (cursor < normalizedText.length) {
    if (normalizedText.startsWith('$$', cursor)) {
      const closingIndex = normalizedText.indexOf('$$', cursor + 2);
      if (closingIndex > cursor + 2) {
        tokens.push(renderMath(normalizedText.slice(cursor + 2, closingIndex), true, `math-${key++}`));
        cursor = closingIndex + 2;
        continue;
      }
    }

    if (normalizedText.startsWith('\\[', cursor)) {
      const closingIndex = normalizedText.indexOf('\\]', cursor + 2);
      if (closingIndex > cursor + 2) {
        tokens.push(renderMath(normalizedText.slice(cursor + 2, closingIndex), true, `math-${key++}`));
        cursor = closingIndex + 2;
        continue;
      }
    }

    if (normalizedText.startsWith('\\(', cursor)) {
      const closingIndex = normalizedText.indexOf('\\)', cursor + 2);
      if (closingIndex > cursor + 2) {
        tokens.push(renderMath(normalizedText.slice(cursor + 2, closingIndex), false, `math-${key++}`));
        cursor = closingIndex + 2;
        continue;
      }
    }

    if (normalizedText[cursor] === '$') {
      const closingIndex = findInlineMathEnd(normalizedText, cursor + 1);
      if (closingIndex > cursor + 1) {
        tokens.push(renderMath(normalizedText.slice(cursor + 1, closingIndex), false, `math-${key++}`));
        cursor = closingIndex + 1;
        continue;
      }
    }

    if (normalizedText[cursor] === '`') {
      const closingIndex = normalizedText.indexOf('`', cursor + 1);
      if (closingIndex > cursor + 1) {
        tokens.push(
          <code key={`code-${key++}`} className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
            {normalizedText.slice(cursor + 1, closingIndex)}
          </code>,
        );
        cursor = closingIndex + 1;
        continue;
      }
    }

    if (normalizedText.startsWith('**', cursor)) {
      const closingIndex = normalizedText.indexOf('**', cursor + 2);
      if (closingIndex > cursor + 2) {
        tokens.push(
          <strong key={`strong-${key++}`} className="font-ui font-semibold text-foreground">
            {renderInline(normalizedText.slice(cursor + 2, closingIndex))}
          </strong>,
        );
        cursor = closingIndex + 2;
        continue;
      }
    }

    if (normalizedText[cursor] === '*') {
      const closingIndex = normalizedText.indexOf('*', cursor + 1);
      if (closingIndex > cursor + 1) {
        tokens.push(
          <em key={`em-${key++}`} className="italic">
            {renderInline(normalizedText.slice(cursor + 1, closingIndex))}
          </em>,
        );
        cursor = closingIndex + 1;
        continue;
      }
    }

    let nextCursor = cursor + 1;
    while (nextCursor < normalizedText.length) {
      if (
        normalizedText.startsWith('$$', nextCursor)
        || normalizedText.startsWith('\\[', nextCursor)
        || normalizedText.startsWith('\\(', nextCursor)
        || normalizedText[nextCursor] === '$'
        || normalizedText[nextCursor] === '`'
        || normalizedText.startsWith('**', nextCursor)
        || normalizedText[nextCursor] === '*'
      ) {
        break;
      }
      nextCursor += 1;
    }

    pushText(normalizedText.slice(cursor, nextCursor));
    cursor = nextCursor;
  }

  return tokens;
}

function renderMarkdown(content: string): ReactNode {
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  const blocks: ReactNode[] = [];

  let paragraph: string[] = [];
  let bulletItems: string[] = [];
  let orderedItems: string[] = [];
  let codeFence: string[] = [];
  let codeLanguage = '';
  let inCodeFence = false;
  let mathFence: string[] = [];
  let mathFenceDelimiter: '$$' | '\\[' | null = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`} className="reading-copy text-base leading-8 text-foreground/95">
        {renderInline(paragraph.join(' '))}
      </p>,
    );
    paragraph = [];
  };

  const flushBullets = () => {
    if (!bulletItems.length) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="ml-1 space-y-2 pl-5 text-base text-foreground/95 marker:text-gold list-disc">
        {bulletItems.map((item, index) => (
          <li key={`bullet-${index}`} className="reading-copy leading-8">
            {renderInline(item)}
          </li>
        ))}
      </ul>,
    );
    bulletItems = [];
  };

  const flushOrdered = () => {
    if (!orderedItems.length) return;
    blocks.push(
      <ol key={`ol-${blocks.length}`} className="ml-1 space-y-2 pl-5 text-base text-foreground/95 marker:text-gold list-decimal">
        {orderedItems.map((item, index) => (
          <li key={`ordered-${index}`} className="reading-copy leading-8">
            {renderInline(item)}
          </li>
        ))}
      </ol>,
    );
    orderedItems = [];
  };

  const flushCode = () => {
    if (!codeFence.length) return;
    blocks.push(
      <div key={`code-${blocks.length}`} className="overflow-hidden rounded-2xl border border-border/70 bg-card/80">
        {codeLanguage ? (
          <div className="border-b border-border/50 px-3 py-2 font-ui text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {codeLanguage}
          </div>
        ) : null}
        <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-6 text-foreground">
          <code>{codeFence.join('\n')}</code>
        </pre>
      </div>,
    );
    codeFence = [];
    codeLanguage = '';
  };

  const flushMathFence = () => {
    if (!mathFence.length) return;
    blocks.push(
      <div key={`math-${blocks.length}`} className="my-2 overflow-x-auto rounded-2xl border border-gold/15 bg-gold/[0.03] px-3 py-3">
        {renderMath(mathFence.join('\n'), true, `math-block-${blocks.length}`)}
      </div>,
    );
    mathFence = [];
    mathFenceDelimiter = null;
  };

  const flushAll = () => {
    flushParagraph();
    flushBullets();
    flushOrdered();
    flushCode();
    flushMathFence();
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\t/g, '  ');
    const trimmed = line.trim();

    if (inCodeFence) {
      if (trimmed.startsWith('```')) {
        inCodeFence = false;
        flushCode();
      } else {
        codeFence.push(rawLine);
      }
      continue;
    }

    if (mathFenceDelimiter) {
      const isClosingMathFence =
        (mathFenceDelimiter === '$$' && trimmed === '$$')
        || (mathFenceDelimiter === '\\[' && trimmed === '\\]');
      if (isClosingMathFence) {
        flushMathFence();
      } else {
        mathFence.push(rawLine);
      }
      continue;
    }

    if (trimmed.startsWith('```')) {
      flushParagraph();
      flushBullets();
      flushOrdered();
      inCodeFence = true;
      codeLanguage = trimmed.slice(3).trim();
      continue;
    }

    if (trimmed === '$$' || trimmed === '\\[') {
      flushParagraph();
      flushBullets();
      flushOrdered();
      mathFenceDelimiter = trimmed as '$$' | '\\[';
      continue;
    }

    const singleLineDisplayMath = trimmed.match(/^\$\$(.+)\$\$$/) || trimmed.match(/^\\\[(.+)\\\]$/);
    if (singleLineDisplayMath) {
      flushAll();
      blocks.push(
        <div key={`math-inline-block-${blocks.length}`} className="my-2 overflow-x-auto rounded-2xl border border-gold/15 bg-gold/[0.03] px-3 py-3">
          {renderMath(singleLineDisplayMath[1], true, `math-inline-block-${blocks.length}`)}
        </div>,
      );
      continue;
    }

    if (/^#{1,3}\s+/.test(trimmed)) {
      flushAll();
      const heading = trimmed.replace(/^#{1,3}\s+/, '');
      const level = trimmed.match(/^#+/)?.[0].length ?? 1;
      const headingClass = level === 1
        ? 'editorial-title text-3xl text-foreground'
        : level === 2
          ? 'font-reading text-2xl text-foreground'
          : 'font-ui text-sm uppercase tracking-[0.12em] text-muted-foreground';
      blocks.push(
        <div key={`heading-${blocks.length}`} className={headingClass}>
          {renderInline(heading)}
        </div>,
      );
      continue;
    }

    const orderedMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      flushBullets();
      orderedItems.push(orderedMatch[2]);
      continue;
    }

    if (/^[-*•]\s+/.test(trimmed)) {
      flushParagraph();
      flushOrdered();
      bulletItems.push(trimmed.replace(/^[-*•]\s+/, ''));
      continue;
    }

    if (/^>\s?/.test(trimmed)) {
      flushAll();
      blocks.push(
        <blockquote key={`quote-${blocks.length}`} className="border-l-2 border-gold/30 pl-4 reading-copy text-base italic text-muted-foreground">
          {renderInline(trimmed.replace(/^>\s?/, ''))}
        </blockquote>,
      );
      continue;
    }

    if (!trimmed) {
      flushAll();
      continue;
    }

    paragraph.push(trimmed);
  }

  flushAll();

  if (!blocks.length) {
    return <p className="reading-copy text-base leading-8 text-foreground/95">{renderInline(content)}</p>;
  }

  return <div className="tutor-rich-content space-y-4">{blocks}</div>;
}

function renderStructuredBlock(block: StructuredContentBlock, index: number) {
  if (block.block_type === 'latex') {
    return (
      <div key={`structured-latex-${index}`} className="my-2 overflow-x-auto rounded-2xl border border-gold/15 bg-gold/[0.03] px-3 py-3">
        {renderMath(block.content, true, `structured-latex-${index}`)}
      </div>
    );
  }

  if (block.block_type === 'code') {
    return (
      <div key={`structured-code-${index}`} className="overflow-hidden rounded-2xl border border-border/70 bg-card/80">
        <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-6 text-foreground">
          <code>{block.content}</code>
        </pre>
      </div>
    );
  }

  if (block.block_type === 'concept_card' || block.block_type === 'checkpoint' || block.block_type === 'quiz_card') {
    const title = typeof block.metadata?.title === 'string'
      ? block.metadata.title
      : block.block_type.replace(/_/g, ' ');
    return (
      <div key={`structured-card-${index}`} className="rounded-2xl border border-gold/15 bg-gold/[0.04] px-4 py-3">
        <div className="font-ui text-[10px] uppercase tracking-[0.18em] text-gold">{title}</div>
        <div className="mt-2">{renderMarkdown(block.content)}</div>
      </div>
    );
  }

  return <div key={`structured-text-${index}`}>{renderMarkdown(block.content)}</div>;
}

function RichTutorContent({ content, structuredContent }: RichTutorContentProps) {
  if (structuredContent && structuredContent.length > 0) {
    return <div className="tutor-rich-content space-y-4">{structuredContent.map(renderStructuredBlock)}</div>;
  }

  return renderMarkdown(content);
}

export default memo(RichTutorContent);
