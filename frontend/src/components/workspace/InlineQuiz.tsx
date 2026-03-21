/**
 * Inline quiz card component (PROD-010).
 *
 * Renders a multiple-choice or freeform quiz question within the tutor chat.
 * Supports immediate feedback and mastery tracking.
 */

import { useState } from 'react';
import { Brain, CheckCircle2, XCircle, HelpCircle } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface QuizCardData {
  quiz_id: string;
  question: string;
  quiz_type: 'multiple_choice' | 'true_false' | 'freeform';
  options?: string[];
  correct_answer?: string;
  explanation?: string;
  concept_id?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
}

interface InlineQuizProps {
  data: QuizCardData;
  onAnswer?: (quizId: string, answer: string, isCorrect: boolean) => void;
}

type AnswerState = 'unanswered' | 'correct' | 'incorrect' | 'submitted';

export default function InlineQuiz({ data, onAnswer }: InlineQuizProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [freeformInput, setFreeformInput] = useState('');
  const [answerState, setAnswerState] = useState<AnswerState>('unanswered');
  const [showExplanation, setShowExplanation] = useState(false);

  const handleSubmit = () => {
    const answer = data.quiz_type === 'freeform' ? freeformInput.trim() : selected;
    if (!answer) return;

    let isCorrect = false;
    if (data.correct_answer) {
      isCorrect = answer.toLowerCase().trim() === data.correct_answer.toLowerCase().trim();
      setAnswerState(isCorrect ? 'correct' : 'incorrect');
    } else {
      setAnswerState('submitted');
    }

    setShowExplanation(true);
    onAnswer?.(data.quiz_id, answer, isCorrect);
  };

  const difficultyColor =
    data.difficulty === 'easy' ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20' :
    data.difficulty === 'hard' ? 'text-red-400 bg-red-400/10 border-red-400/20' :
    'text-amber-500 bg-amber-500/10 border-amber-500/20';

  const stateIcon =
    answerState === 'correct' ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> :
    answerState === 'incorrect' ? <XCircle className="w-4 h-4 text-red-400" /> :
    <Brain className="w-4 h-4 text-gold" />;

  const stateBorderColor =
    answerState === 'correct' ? 'border-emerald-500/30' :
    answerState === 'incorrect' ? 'border-red-400/30' :
    'border-purple-400/30';

  return (
    <div className={cn(
      'rounded-xl border-2 bg-card/50 overflow-hidden animate-fade-up transition-colors',
      stateBorderColor,
    )}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/20">
        {stateIcon}
        <span className="text-xs font-semibold text-foreground uppercase tracking-wider flex-1">
          Quick Check
        </span>
        {data.difficulty && (
          <span className={cn('text-[9px] px-2 py-0.5 rounded-full border font-medium', difficultyColor)}>
            {data.difficulty}
          </span>
        )}
      </div>

      {/* Question */}
      <div className="px-4 py-3 space-y-3">
        <p className="text-sm text-foreground leading-relaxed">{data.question}</p>

        {/* Multiple choice options */}
        {(data.quiz_type === 'multiple_choice' || data.quiz_type === 'true_false') && data.options && (
          <div className="space-y-1.5">
            {data.options.map((opt, i) => {
              const isSelected = selected === opt;
              const isCorrectOption = answerState !== 'unanswered' && data.correct_answer === opt;
              const isWrongSelected = answerState === 'incorrect' && isSelected;

              return (
                <button
                  key={i}
                  onClick={() => answerState === 'unanswered' && setSelected(opt)}
                  disabled={answerState !== 'unanswered'}
                  className={cn(
                    'w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all border flex items-center gap-2',
                    answerState === 'unanswered' && isSelected
                      ? 'bg-gold/10 border-gold/30 text-foreground'
                      : answerState === 'unanswered'
                      ? 'bg-card/50 border-border/40 text-muted-foreground hover:border-border'
                      : isCorrectOption
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-foreground'
                      : isWrongSelected
                      ? 'bg-red-400/10 border-red-400/30 text-foreground'
                      : 'bg-card/30 border-border/20 text-muted-foreground/60',
                  )}
                >
                  <span className={cn(
                    'w-5 h-5 rounded-full border flex items-center justify-center text-[10px] font-medium shrink-0',
                    answerState === 'unanswered' && isSelected
                      ? 'border-gold bg-gold/20 text-gold'
                      : isCorrectOption
                      ? 'border-emerald-500 bg-emerald-500/20 text-emerald-500'
                      : isWrongSelected
                      ? 'border-red-400 bg-red-400/20 text-red-400'
                      : 'border-border text-muted-foreground',
                  )}>
                    {String.fromCharCode(65 + i)}
                  </span>
                  <span className="flex-1">{opt}</span>
                  {isCorrectOption && (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  )}
                  {isWrongSelected && (
                    <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Freeform input */}
        {data.quiz_type === 'freeform' && answerState === 'unanswered' && (
          <input
            type="text"
            value={freeformInput}
            onChange={(e) => setFreeformInput(e.target.value)}
            placeholder="Type your answer..."
            className="w-full bg-card/50 border border-border/40 rounded-lg px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/40 outline-none focus:border-gold/40 transition-colors"
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          />
        )}

        {/* Submit button */}
        {answerState === 'unanswered' && (
          <button
            onClick={handleSubmit}
            disabled={data.quiz_type === 'freeform' ? !freeformInput.trim() : !selected}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            Check Answer
          </button>
        )}

        {/* Feedback */}
        {answerState !== 'unanswered' && (
          <div className={cn(
            'rounded-lg px-3 py-2.5 text-xs leading-relaxed',
            answerState === 'correct'
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
              : answerState === 'incorrect'
              ? 'bg-red-400/10 text-red-500 dark:text-red-400'
              : 'bg-muted/30 text-muted-foreground',
          )}>
            {answerState === 'correct' && 'Correct! '}
            {answerState === 'incorrect' && 'Not quite. '}
            {answerState === 'submitted' && 'Answer submitted. '}
            {data.correct_answer && answerState === 'incorrect' && (
              <span>The correct answer is: <strong>{data.correct_answer}</strong></span>
            )}
          </div>
        )}

        {/* Explanation */}
        {showExplanation && data.explanation && (
          <div className="rounded-lg bg-muted/20 border border-border/20 px-3 py-2.5">
            <div className="flex items-center gap-1.5 mb-1">
              <HelpCircle className="w-3 h-3 text-muted-foreground" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Explanation
              </span>
            </div>
            <p className="text-xs text-foreground/80 leading-relaxed">{data.explanation}</p>
          </div>
        )}
      </div>
    </div>
  );
}
