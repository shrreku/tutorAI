/**
 * Center tutor chat panel for the study workspace (PROD-009 / PROD-010).
 *
 * Renders the conversational tutoring interface with:
 *  - Turn history with student/tutor bubbles
 *  - Concept cards and checkpoint cards (PROD-010)
 *  - Message input with quick actions
 *  - Streaming indicator
 */

import { useRef, useEffect, useState, useCallback, type FormEvent } from 'react';
import {
  Sparkles, Send, Loader2, ArrowDown, Lightbulb, HelpCircle,
  CheckCircle2, Brain, RotateCcw, Clock3,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import type { Turn, CitationData } from '../../types/api';
import type { CheckpointRequestedPayload } from '../../types/session-events';
import RichTutorContent from '../ui/RichTutorContent';
import SelectableCapture from '../ui/SelectableCapture';

interface TutorPanelProps {
  turns: Turn[];
  isLoading: boolean;
  isSending: boolean;
  onSendMessage: (message: string) => void;
  onAddToNotes?: (text: string) => void;
  activeCheckpoint: CheckpointRequestedPayload | null;
  onCheckpointResponse?: (checkpointId: string, response: string) => void;
  sessionComplete: boolean;
  onEndSession?: () => void;
  quickActions?: Array<{ label: string; message: string; icon?: React.ReactNode }>;
}

function CheckpointCard({
  checkpoint,
  onRespond,
}: {
  checkpoint: CheckpointRequestedPayload;
  onRespond: (response: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [freeform, setFreeform] = useState('');

  const handleSubmit = () => {
    const response = selected || freeform.trim();
    if (response) onRespond(response);
  };

  return (
    <div className="rounded-[24px] border-2 border-gold/30 bg-gold/[0.04] p-4 space-y-3 animate-fade-up surface-scholarly">
      <div className="flex items-center gap-2">
        <Brain className="w-4 h-4 text-gold" />
        <span className="text-xs font-semibold text-gold uppercase tracking-wider font-ui">
          Understanding Check
        </span>
      </div>
      <p className="text-base text-foreground leading-relaxed reading-copy">{checkpoint.question}</p>

      {checkpoint.options.length > 0 && (
        <div className="space-y-1.5">
          {checkpoint.options.map((opt, i) => (
            <button
              key={i}
              onClick={() => setSelected(opt)}
              className={cn(
                'w-full text-left px-3 py-2 rounded-xl text-sm transition-all border reading-copy',
                selected === opt
                  ? 'bg-gold/10 border-gold/30 text-foreground'
                  : 'bg-card/50 border-border/40 text-muted-foreground hover:border-border',
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      {checkpoint.allow_freeform && (
        <input
          type="text"
          value={freeform}
          onChange={(e) => setFreeform(e.target.value)}
          placeholder="Or type your answer..."
          className="w-full bg-card/50 border border-border/40 rounded-xl px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-gold/40 reading-copy"
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
        />
      )}

      <button
        onClick={handleSubmit}
        disabled={!selected && !freeform.trim()}
        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed font-ui uppercase tracking-[0.08em]"
      >
        <CheckCircle2 className="w-3.5 h-3.5" />
        Submit
      </button>
    </div>
  );
}

function ConceptCard({ concepts, action }: { concepts: string[]; action?: string }) {
  if (concepts.length === 0) return null;
  return (
    <div className="flex items-center gap-2 flex-wrap my-1">
      <Lightbulb className="w-3 h-3 text-gold shrink-0" />
      {concepts.map((c) => (
        <span
          key={c}
          className="data-chip px-2 py-0.5 rounded-full bg-gold/[0.06] border border-gold/15 text-[10px] font-medium text-gold"
        >
          {c}
        </span>
      ))}
      {action && (
        <span className="text-[10px] text-muted-foreground italic reading-copy">{action}</span>
      )}
    </div>
  );
}

function CitationPills({ citations }: { citations: CitationData[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!citations.length) return null;

  return (
    <div className="mt-2 space-y-1">
      <div className="flex items-center gap-1.5 flex-wrap">
        {citations.map((c, i) => (
          <button
            key={c.citation_id}
            onClick={() => setExpanded(expanded === c.citation_id ? null : c.citation_id)}
            className={cn(
              'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all font-ui uppercase tracking-[0.06em]',
              expanded === c.citation_id
                ? 'bg-gold/15 border border-gold/30 text-gold'
                : 'bg-muted/50 border border-border/40 text-muted-foreground hover:border-gold/20 hover:text-foreground',
            )}
            title={c.section_heading || `Source ${i + 1}`}
          >
            <span className="w-3.5 h-3.5 rounded-full bg-gold/10 text-gold text-[9px] font-bold flex items-center justify-center">
              {i + 1}
            </span>
            {c.page_start != null && (
              <span>p.{c.page_start}{c.page_end != null && c.page_end !== c.page_start ? `\u2013${c.page_end}` : ''}</span>
            )}
            {c.page_start == null && c.section_heading && (
              <span className="truncate max-w-[80px]">{c.section_heading}</span>
            )}
          </button>
        ))}
      </div>
      {expanded && (() => {
        const c = citations.find(ci => ci.citation_id === expanded);
        if (!c) return null;
        return (
          <div className="rounded-lg border border-border/50 bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
            {c.section_heading && (
              <p className="font-reading text-base text-foreground/80 mb-1">{c.section_heading}</p>
            )}
            {c.snippet && (
              <p className="italic leading-relaxed line-clamp-3 reading-copy">&ldquo;{c.snippet}&rdquo;</p>
            )}
            <div className="flex items-center gap-3 mt-1.5 text-[10px] font-ui uppercase tracking-[0.06em]">
              {c.page_start != null && (
                <span>Page {c.page_start}{c.page_end != null && c.page_end !== c.page_start ? `\u2013${c.page_end}` : ''}</span>
              )}
              <span className="text-muted-foreground/50">
                Relevance: {Math.round(c.relevance_score * 100)}%
              </span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

export default function TutorPanel({
  turns,
  isLoading,
  isSending,
  onSendMessage,
  onAddToNotes,
  activeCheckpoint,
  onCheckpointResponse,
  sessionComplete,
  onEndSession,
  quickActions,
}: TutorPanelProps) {
  const [message, setMessage] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [turns.length, isSending, scrollToBottom]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      setShowScrollButton(scrollHeight - scrollTop - clientHeight > 200);
    };
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || isSending) return;
    onSendMessage(trimmed);
    setMessage('');
  };

  return (
    <div className="h-full flex flex-col relative">
      {/* Messages area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto px-4 py-5 space-y-4"
      >
        {/* Empty state */}
        {turns.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <div className="w-14 h-14 rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center mb-4">
              <Sparkles className="w-6 h-6 text-gold" />
            </div>
            <h3 className="font-reading text-4xl text-foreground mb-1">Shape this study block</h3>
            <p className="reading-copy text-base text-muted-foreground max-w-xl leading-relaxed">
              Start with a goal, ask for a walkthrough, or ask the tutor to turn your material into practice. This workspace is designed to help you learn, summarize, and produce study outputs in one place.
            </p>

            {/* Quick actions */}
            {quickActions && quickActions.length > 0 && (
              <div className="grid w-full max-w-2xl gap-2 mt-6 md:grid-cols-2">
                {quickActions.map((qa, i) => (
                  <button
                    key={i}
                    onClick={() => onSendMessage(qa.message)}
                    className="flex items-start gap-3 rounded-xl border border-border bg-card/90 px-4 py-3 text-left text-xs text-foreground transition-all hover:border-gold/30 hover:bg-gold/[0.04]"
                  >
                    <div className="mt-0.5 rounded-lg border border-gold/15 bg-gold/[0.06] p-2">
                      {qa.icon || <HelpCircle className="w-3 h-3 text-gold" />}
                    </div>
                    <div>
                      <p className="text-sm font-ui font-medium text-foreground uppercase tracking-[0.08em]">{qa.label}</p>
                      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground reading-copy">
                        {qa.message}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Turn messages */}
        {turns.map((turn: Turn) => (
          <div key={turn.turn_id} className="space-y-3">
            {/* Student bubble */}
            {turn.student_message?.trim() ? (
              <div className="flex justify-end">
                <div className="max-w-[88%] rounded-[22px] border border-gold/20 bg-gold/[0.06] px-4 py-3 text-sm text-foreground">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-gold/80 font-ui">
                    You asked
                  </p>
                  <p className="leading-relaxed whitespace-pre-wrap reading-copy text-base">{turn.student_message}</p>
                </div>
              </div>
            ) : null}

            {/* Tutor bubble */}
            {(turn.tutor_response?.trim() || turn.structured_content?.length) ? (
              <div className="flex justify-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-card border border-border flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles className="w-3.5 h-3.5 text-gold" />
                </div>
                <div className="max-w-[90%] space-y-2">
                  {/* Focus concepts */}
                  {turn.focus_concepts && turn.focus_concepts.length > 0 && (
                    <ConceptCard concepts={turn.focus_concepts} />
                  )}
                  <div className="rounded-[24px] border border-border bg-card/95 px-5 py-4 text-sm text-foreground leading-relaxed surface-scholarly">
                    <div className="mb-3 flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-muted-foreground font-ui">
                      <Clock3 className="h-3 w-3 text-gold" />
                      Tutor explanation
                    </div>
                    {onAddToNotes ? (
                      <SelectableCapture onCapture={onAddToNotes}>
                        <RichTutorContent
                          content={turn.tutor_response}
                          structuredContent={turn.structured_content}
                        />
                      </SelectableCapture>
                    ) : (
                      <RichTutorContent
                        content={turn.tutor_response}
                        structuredContent={turn.structured_content}
                      />
                    )}
                    {/* Citation pills */}
                    {turn.citations && turn.citations.length > 0 && (
                      <CitationPills citations={turn.citations} />
                    )}
                  </div>
                  {/* Step transition indicator */}
                  {turn.step_transition && (
                    <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground font-ui uppercase tracking-[0.08em]">
                      <RotateCcw className="w-2.5 h-2.5" />
                      <span>{turn.step_transition}</span>
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {/* Mastery update */}
            {turn.mastery_update && Object.keys(turn.mastery_update).length > 0 && (
              <div className="flex justify-center">
                <div className="flex items-center gap-2 rounded-full border border-border/30 bg-muted/30 px-3 py-1.5 font-ui uppercase tracking-[0.06em]">
                  <Brain className="w-3 h-3 text-gold" />
                  <span className="text-[10px] text-muted-foreground">
                    Mastery updated: {Object.entries(turn.mastery_update).map(
                      ([k, v]) => `${k} → ${Math.round((v as number) * 100)}%`
                    ).join(', ')}
                  </span>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Active checkpoint */}
        {activeCheckpoint && onCheckpointResponse && (
          <CheckpointCard
            checkpoint={activeCheckpoint}
            onRespond={(response) =>
              onCheckpointResponse(activeCheckpoint.checkpoint_id, response)
            }
          />
        )}

        {/* Sending indicator */}
        {isSending && (
          <div className="flex justify-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-card border border-border flex items-center justify-center shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-foreground animate-pulse" />
            </div>
            <div className="rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 text-foreground animate-spin" />
                <span className="text-xs text-muted-foreground font-ui uppercase tracking-[0.08em]">Building the next explanation…</span>
              </div>
            </div>
          </div>
        )}

        <div ref={scrollRef} />
      </div>

      {/* Scroll to bottom button */}
      {showScrollButton && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-20 left-1/2 -translate-x-1/2 z-10 p-2 rounded-full bg-card border border-border shadow-lg hover:bg-muted transition-colors"
        >
          <ArrowDown className="w-4 h-4 text-foreground" />
        </button>
      )}

      {/* Input area */}
      <div className="shrink-0 border-t border-border/40 bg-card/50 px-4 pb-4 pt-3">
        {sessionComplete ? (
          <div className="flex items-center justify-center gap-3 py-2">
            <span className="text-xs text-muted-foreground font-ui uppercase tracking-[0.08em]">Session complete</span>
            {onEndSession && (
              <button
                onClick={onEndSession}
                className="text-xs text-gold hover:underline font-ui uppercase tracking-[0.08em] font-medium"
              >
                View summary
              </button>
            )}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            {quickActions && quickActions.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {quickActions.slice(0, 4).map((qa, index) => (
                  <button
                    key={`${qa.label}-${index}`}
                    type="button"
                    onClick={() => setMessage(qa.message)}
                    className="rounded-full border border-border bg-card px-3 py-1.5 text-[11px] text-muted-foreground transition-colors hover:border-gold/20 hover:text-foreground font-ui uppercase tracking-[0.08em]"
                  >
                    {qa.label}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2">
              <div className="flex-1 relative">
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                placeholder="Ask a question or continue studying..."
                rows={1}
                className="w-full resize-none rounded-[20px] bg-card border border-border px-4 py-3 pr-12 text-base text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-gold/40 transition-colors leading-relaxed reading-copy"
                style={{ minHeight: '44px', maxHeight: '120px' }}
              />
              </div>
              <button
                type="submit"
                disabled={!message.trim() || isSending}
                className="shrink-0 w-11 h-11 rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center text-gold hover:bg-gold/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {isSending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
