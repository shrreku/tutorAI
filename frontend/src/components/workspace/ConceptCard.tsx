/**
 * Concept card component (PROD-010).
 *
 * Renders a structured concept explanation card within the tutor chat,
 * highlighting definition, key points, and related concepts.
 */

import { useState } from 'react';
import { Lightbulb, ChevronDown, ChevronRight, BookOpen } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface ConceptCardData {
  concept_id: string;
  title: string;
  definition: string;
  key_points?: string[];
  related_concepts?: string[];
  mastery_score?: number;
  example?: string;
}

interface ConceptCardProps {
  data: ConceptCardData;
  compact?: boolean;
}

export default function ConceptCard({ data, compact = false }: ConceptCardProps) {
  const [expanded, setExpanded] = useState(!compact);

  const masteryPct = data.mastery_score != null ? Math.round(data.mastery_score * 100) : null;
  const masteryColor =
    masteryPct != null && masteryPct >= 70 ? 'text-emerald-500' :
    masteryPct != null && masteryPct >= 40 ? 'text-amber-500' :
    'text-red-400';

  return (
    <div className="rounded-xl border border-gold/20 bg-gold/[0.03] overflow-hidden animate-fade-up">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-gold/[0.04] transition-colors"
      >
        <div className="w-7 h-7 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
          <Lightbulb className="w-3.5 h-3.5 text-gold" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground truncate">{data.title}</p>
          {!expanded && (
            <p className="text-[11px] text-muted-foreground truncate mt-0.5">{data.definition}</p>
          )}
        </div>
        {masteryPct != null && (
          <span className={cn('text-[10px] font-medium shrink-0', masteryColor)}>
            {masteryPct}%
          </span>
        )}
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gold/10">
          {/* Definition */}
          <p className="text-sm text-foreground/90 leading-relaxed pt-3">
            {data.definition}
          </p>

          {/* Key points */}
          {data.key_points && data.key_points.length > 0 && (
            <div className="space-y-1.5">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Key Points
              </h4>
              <ul className="space-y-1">
                {data.key_points.map((point, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-foreground/80">
                    <span className="text-gold mt-1 shrink-0">&#8226;</span>
                    <span className="leading-relaxed">{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Example */}
          {data.example && (
            <div className="rounded-lg bg-muted/30 border border-border/30 px-3 py-2.5">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                Example
              </h4>
              <p className="text-xs text-foreground/80 leading-relaxed">{data.example}</p>
            </div>
          )}

          {/* Related concepts */}
          {data.related_concepts && data.related_concepts.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <BookOpen className="w-3 h-3 text-muted-foreground shrink-0" />
              {data.related_concepts.map((c) => (
                <span
                  key={c}
                  className="px-2 py-0.5 rounded-full bg-muted/40 border border-border/30 text-[10px] text-muted-foreground"
                >
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
