import { type ReactNode, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  EyeOff,
  FileJson,
  HelpCircle,
  RotateCcw,
  Sparkles,
  X,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import {
  ARTIFACT_TYPE_COLOR,
  ARTIFACT_TYPE_ICON,
} from '../icons/ArtifactCatalog';
import RichTutorContent from './RichTutorContent';
import SelectableCapture from './SelectableCapture';

type ArtifactPayload = unknown;

type QuizQuestion = {
  questionId: string;
  question: string;
  questionType: string;
  options: string[];
  correctAnswer: string;
  explanation: string;
  concept: string;
  difficulty: string;
};

type FlashcardItem = {
  front: string;
  back: string;
  concept: string;
  difficulty: string;
  studyHint: string;
};

type RevisionDay = {
  dayLabel: string;
  scheduledFor: string;
  focusConcepts: string[];
  activities: string[];
  rationale: string;
};

type QuizAnswerState = {
  answer: string;
  submitted: boolean;
  showExplanation: boolean;
};

export type QuizSubmissionSignal = {
  artifactKey: string;
  artifactTitle: string;
  questionId: string;
  question: string;
  concept: string;
  userAnswer: string;
  correctAnswer: string;
  explanation: string;
  wasCorrect: boolean;
};

type ArtifactViewerCardProps = {
  artifactKey?: string;
  type: string;
  title: string;
  payload?: ArtifactPayload;
  subtitle?: string;
  createdAt?: string;
  isGenerating?: boolean;
  className?: string;
  downloadFileName?: string;
  onAddToNotes?: (text: string) => void;
  onQuizSubmission?: (signal: QuizSubmissionSignal) => void;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean);
}

function formatDateLabel(value?: string) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function normalizeAnswer(value: string) {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function extractQuizQuestions(payload: ArtifactPayload): QuizQuestion[] {
  const record = asRecord(payload);
  const rawQuestions = Array.isArray(record?.questions)
    ? record?.questions
    : Array.isArray(payload)
      ? payload
      : [];

  return rawQuestions
    .map((item, index) => {
      const question = asRecord(item);
      if (!question) return null;
      return {
        questionId: asString(question.question_id) || `question-${index + 1}`,
        question: asString(question.question) || asString(question.text) || `Question ${index + 1}`,
        questionType: asString(question.question_type) || 'multiple_choice',
        options: asStringArray(question.options),
        correctAnswer: asString(question.correct_answer) || asString(question.answer) || '',
        explanation: asString(question.explanation) || '',
        concept: asString(question.concept) || '',
        difficulty: asString(question.difficulty) || 'medium',
      };
    })
    .filter((item): item is QuizQuestion => Boolean(item));
}

function extractFlashcards(payload: ArtifactPayload): FlashcardItem[] {
  const record = asRecord(payload);
  const rawCards = Array.isArray(record?.cards)
    ? record?.cards
    : Array.isArray(record?.flashcards)
      ? record?.flashcards
      : Array.isArray(payload)
        ? payload
        : [];

  return rawCards
    .map((item) => {
      const card = asRecord(item);
      if (!card) return null;
      const front = asString(card.front) || asString(card.question);
      const back = asString(card.back) || asString(card.answer);
      if (!front || !back) return null;
      return {
        front,
        back,
        concept: asString(card.concept) || '',
        difficulty: asString(card.difficulty) || 'medium',
        studyHint: asString(card.study_hint) || '',
      };
    })
    .filter((item): item is FlashcardItem => Boolean(item));
}

function extractRevisionDays(payload: ArtifactPayload): RevisionDay[] {
  const record = asRecord(payload);
  const rawDays = Array.isArray(record?.days)
    ? record?.days
    : Array.isArray(record?.steps)
      ? record?.steps
      : Array.isArray(record?.items)
        ? record?.items
        : Array.isArray(record?.plan)
          ? record?.plan
          : Array.isArray(record?.schedule)
            ? record?.schedule
            : Array.isArray(payload)
              ? payload
              : [];

  return rawDays
    .map((item, index) => {
      const day = asRecord(item);
      if (!day) return null;
      return {
        dayLabel: asString(day.day_label) || asString(day.title) || asString(day.topic) || `Day ${index + 1}`,
        scheduledFor: asString(day.scheduled_for) || '',
        focusConcepts: asStringArray(day.focus_concepts),
        activities: asStringArray(day.activities),
        rationale: asString(day.rationale) || asString(day.description) || asString(day.concept) || '',
      };
    })
    .filter((item): item is RevisionDay => Boolean(item));
}

function downloadPayload(payload: ArtifactPayload, fileName: string) {
  const blob = new Blob([JSON.stringify(payload ?? {}, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ArtifactModal({
  open,
  onClose,
  children,
  title,
  type,
  createdAt,
  onDownload,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  title: string;
  type: string;
  createdAt?: string;
  onDownload?: () => void;
}) {
  const Icon = ARTIFACT_TYPE_ICON[type] || FileJson;
  const colorClass = ARTIFACT_TYPE_COLOR[type] || 'text-muted-foreground bg-muted border-border';

  useEffect(() => {
    if (!open) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 border-b border-border/40 px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-3">
            <Icon className={cn('h-4 w-4 shrink-0', colorClass.split(' ')[0])} />
            <h2 className="truncate text-base font-semibold text-foreground">{title}</h2>
            <span className="text-xs text-muted-foreground shrink-0">{type.replace(/_/g, ' ')}</span>
            {createdAt ? <span className="text-xs text-muted-foreground/60 shrink-0">{formatDateLabel(createdAt)}</span> : null}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {onDownload ? (
              <button
                type="button"
                onClick={onDownload}
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                title="Download JSON"
              >
                <Download className="h-4 w-4" />
              </button>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-5">{children}</div>
      </div>
    </div>
  );
}

function NotesArtifactBody({ payload }: { payload: ArtifactPayload }) {
  const record = asRecord(payload);
  const sections = Array.isArray(record?.sections) ? record.sections.map(asRecord).filter(Boolean) as Record<string, unknown>[] : [];
  const nextActions = asStringArray(record?.next_actions);
  const coverageConcepts = asStringArray(record?.coverage_concepts);
  const summary = asString(record?.summary) || asString(record?.content) || asString(record?.text);

  return (
    <div className="space-y-5">
      {summary ? (
        <div className="text-sm text-foreground leading-relaxed">
          <RichTutorContent content={summary} />
        </div>
      ) : null}

      {sections.length > 0 ? (
        <div className="space-y-5">
          {sections.map((section, index) => {
            const bullets = asStringArray(section.bullets);
            const heading = asString(section.heading) || `Section ${index + 1}`;
            const takeaway = asString(section.key_takeaway);
            const concepts = asStringArray(section.concepts);

            return (
              <div key={`${heading}-${index}`}>
                <h3 className="text-sm font-semibold text-foreground mb-2">{heading}</h3>

                {bullets.length > 0 ? (
                  <ul className="space-y-1.5 ml-0.5">
                    {bullets.map((bullet) => (
                      <li key={bullet} className="flex gap-2.5">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-gold/70" />
                        <div className="min-w-0 flex-1 text-sm text-foreground/90">
                          <RichTutorContent content={bullet} />
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}

                {takeaway ? (
                  <p className="mt-2.5 text-sm text-foreground/80 border-l-2 border-gold/30 pl-3 italic">{takeaway}</p>
                ) : null}

                {concepts.length > 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">Concepts: {concepts.join(', ')}</p>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {nextActions.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-1.5">Next actions</p>
          <ul className="space-y-1">
            {nextActions.map((action) => (
              <li key={action} className="flex gap-2.5 text-sm text-foreground/90">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-gold/70" />
                <span>{action}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {coverageConcepts.length > 0 ? (
        <p className="text-xs text-muted-foreground">Coverage: {coverageConcepts.join(', ')}</p>
      ) : null}
    </div>
  );
}

function FlashcardsArtifactBody({
  payload,
  currentIndex,
  flipped,
  onPrevious,
  onNext,
  onFlip,
  onReset,
}: {
  payload: ArtifactPayload;
  currentIndex: number;
  flipped: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onFlip: () => void;
  onReset: () => void;
}) {
  const cards = extractFlashcards(payload);
  const currentCard = cards[currentIndex];

  if (!currentCard) {
    return <ArtifactFallbackBody payload={payload} />;
  }

  return (
    <div className="space-y-4">
      {/* Navigation bar */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button type="button" onClick={onPrevious} disabled={currentIndex === 0}
            className="rounded-lg border border-border p-1.5 text-foreground transition-colors hover:bg-muted/60 disabled:opacity-30">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-muted-foreground tabular-nums">{currentIndex + 1} / {cards.length}</span>
          <button type="button" onClick={onNext} disabled={currentIndex >= cards.length - 1}
            className="rounded-lg border border-border p-1.5 text-foreground transition-colors hover:bg-muted/60 disabled:opacity-30">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          {currentCard.concept ? <span className="text-xs text-muted-foreground">{currentCard.concept}</span> : null}
          <button type="button" onClick={onReset}
            className="rounded-lg border border-border p-1.5 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground" title="Restart deck">
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Prompt */}
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1.5">Prompt</p>
        <div className="text-sm text-foreground leading-relaxed">
          <RichTutorContent content={currentCard.front} />
        </div>
      </div>

      {/* Answer */}
      <div className={cn('rounded-xl border px-4 py-3 transition-all', flipped ? 'border-gold/25 bg-gold/[0.04]' : 'border-border bg-muted/30')}>
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-xs font-medium text-muted-foreground">Answer</p>
          <button type="button" onClick={onFlip}
            className="inline-flex items-center gap-1.5 text-xs text-gold hover:text-gold/80 transition-colors">
            {flipped ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
            {flipped ? 'Hide' : 'Reveal'}
          </button>
        </div>
        {flipped ? (
          <div className="text-sm text-foreground leading-relaxed">
            <RichTutorContent content={currentCard.back} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground/60 italic">Click reveal to see the answer</p>
        )}
      </div>

      {currentCard.studyHint ? (
        <p className="text-xs text-muted-foreground border-l-2 border-gold/30 pl-3">{currentCard.studyHint}</p>
      ) : null}
    </div>
  );
}

function QuizArtifactBody({
  payload,
  currentIndex,
  answers,
  onCurrentIndexChange,
  onAnswerChange,
  onSubmit,
  onToggleExplanation,
  onReset,
}: {
  payload: ArtifactPayload;
  currentIndex: number;
  answers: Record<number, QuizAnswerState>;
  onCurrentIndexChange: (index: number) => void;
  onAnswerChange: (index: number, answer: string) => void;
  onSubmit: (index: number) => void;
  onToggleExplanation: (index: number) => void;
  onReset: () => void;
}) {
  const record = asRecord(payload);
  const questions = extractQuizQuestions(payload);
  const currentQuestion = questions[currentIndex];
  const currentState = answers[currentIndex] || { answer: '', submitted: false, showExplanation: false };
  const answeredCount = Object.values(answers).filter((entry) => entry.submitted).length;
  const correctCount = questions.reduce((count, question, index) => {
    const response = answers[index];
    if (!response?.submitted) return count;
    return normalizeAnswer(response.answer) === normalizeAnswer(question.correctAnswer) ? count + 1 : count;
  }, 0);

  if (!currentQuestion) {
    return <ArtifactFallbackBody payload={payload} />;
  }

  const isCorrect = currentState.submitted
    ? normalizeAnswer(currentState.answer) === normalizeAnswer(currentQuestion.correctAnswer)
    : false;
  const canSubmit = Boolean(currentState.answer.trim()) && !currentState.submitted;
  const hasOptions = currentQuestion.options.length > 0;
  const followUp = asString(record?.recommended_follow_up);

  return (
    <div className="space-y-4">
      {/* Score + nav bar */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-sm">
          <span className="text-gold font-medium tabular-nums">{correctCount}/{questions.length} correct</span>
          <span className="text-muted-foreground tabular-nums">{answeredCount} answered</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button type="button" onClick={() => onCurrentIndexChange(Math.max(0, currentIndex - 1))} disabled={currentIndex === 0}
            className="rounded-lg border border-border p-1.5 text-foreground transition-colors hover:bg-muted/60 disabled:opacity-30">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-muted-foreground tabular-nums min-w-[3rem] text-center">{currentIndex + 1} / {questions.length}</span>
          <button type="button" onClick={() => onCurrentIndexChange(Math.min(questions.length - 1, currentIndex + 1))} disabled={currentIndex >= questions.length - 1}
            className="rounded-lg border border-border p-1.5 text-foreground transition-colors hover:bg-muted/60 disabled:opacity-30">
            <ChevronRight className="h-4 w-4" />
          </button>
          <button type="button" onClick={onReset}
            className="rounded-lg border border-border p-1.5 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground ml-1" title="Reset quiz">
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Question dots */}
      <div className="flex flex-wrap gap-1.5">
        {questions.map((question, index) => {
          const response = answers[index];
          const answered = Boolean(response?.submitted);
          const correct = answered && normalizeAnswer(response?.answer || '') === normalizeAnswer(question.correctAnswer);
          return (
            <button key={question.questionId} type="button" onClick={() => onCurrentIndexChange(index)}
              className={cn(
                'flex h-7 w-7 items-center justify-center rounded-md text-[10px] font-semibold transition-colors',
                index === currentIndex ? 'bg-gold/15 text-gold ring-1 ring-gold/40'
                  : correct ? 'bg-emerald-500/10 text-emerald-500'
                  : answered ? 'bg-red-500/10 text-red-500'
                  : 'bg-muted/40 text-muted-foreground hover:bg-muted/70',
              )}>
              {index + 1}
            </button>
          );
        })}
      </div>

      {/* Question */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-medium text-muted-foreground">Q{currentIndex + 1}</span>
          {currentQuestion.concept ? <span className="text-xs text-muted-foreground/70">{currentQuestion.concept}</span> : null}
        </div>
        <div className="text-sm text-foreground leading-relaxed">
          <RichTutorContent content={currentQuestion.question} />
        </div>
      </div>

      {/* Options / Answer input */}
      <div className="space-y-2">
        {hasOptions ? (
          currentQuestion.options.map((option, optionIndex) => {
            const isSelected = currentState.answer === option;
            const isCorrectOption = currentState.submitted && normalizeAnswer(option) === normalizeAnswer(currentQuestion.correctAnswer);
            const isWrongSelection = currentState.submitted && isSelected && !isCorrect;
            return (
              <button key={`${option}-${optionIndex}`} type="button"
                onClick={() => !currentState.submitted && onAnswerChange(currentIndex, option)}
                disabled={currentState.submitted}
                className={cn(
                  'flex w-full items-start gap-3 rounded-xl border px-3.5 py-2.5 text-left transition-colors',
                  !currentState.submitted && isSelected ? 'border-gold/40 bg-gold/[0.06]'
                    : !currentState.submitted ? 'border-border hover:border-gold/20'
                    : isCorrectOption ? 'border-emerald-500/30 bg-emerald-500/[0.06]'
                    : isWrongSelection ? 'border-red-500/30 bg-red-500/[0.06]'
                    : 'border-border/40 text-muted-foreground',
                )}>
                <span className={cn(
                  'flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] font-semibold mt-0.5',
                  !currentState.submitted && isSelected ? 'bg-gold/20 text-gold'
                    : isCorrectOption ? 'bg-emerald-500/20 text-emerald-500'
                    : isWrongSelection ? 'bg-red-500/20 text-red-500'
                    : 'bg-muted/60 text-muted-foreground',
                )}>
                  {String.fromCharCode(65 + optionIndex)}
                </span>
                <span className="min-w-0 flex-1 text-sm">{option}</span>
                {isCorrectOption ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" /> : null}
              </button>
            );
          })
        ) : (
          <textarea
            value={currentState.answer}
            onChange={(event) => !currentState.submitted && onAnswerChange(currentIndex, event.target.value)}
            disabled={currentState.submitted}
            placeholder="Type your answer..."
            className="min-h-[100px] w-full resize-none rounded-xl border border-border bg-card/60 px-3.5 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/50 focus:border-gold/30 disabled:opacity-70"
          />
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {currentState.submitted && currentQuestion.explanation ? (
            <button type="button" onClick={() => onToggleExplanation(currentIndex)}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
              <HelpCircle className="h-3.5 w-3.5" />
              {currentState.showExplanation ? 'Hide explanation' : 'Explain'}
            </button>
          ) : null}
        </div>
        <button type="button" onClick={() => onSubmit(currentIndex)} disabled={!canSubmit}
          className="inline-flex items-center gap-1.5 rounded-lg bg-gold px-3.5 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-gold/90 disabled:opacity-40">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Check
        </button>
      </div>

      {/* Feedback */}
      {currentState.submitted ? (
        <div className={cn(
          'rounded-xl border px-3.5 py-2.5 text-sm',
          isCorrect ? 'border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-600 dark:text-emerald-400' : 'border-red-500/20 bg-red-500/[0.06] text-red-600 dark:text-red-400',
        )}>
          <p className="font-medium">{isCorrect ? 'Correct!' : 'Not quite.'}</p>
          {!isCorrect && currentQuestion.correctAnswer ? (
            <p className="mt-0.5">Answer: <span className="font-semibold">{currentQuestion.correctAnswer}</span></p>
          ) : null}
        </div>
      ) : null}

      {currentState.submitted && currentState.showExplanation && currentQuestion.explanation ? (
        <div className="text-sm text-foreground/80 border-l-2 border-gold/30 pl-3">
          <RichTutorContent content={currentQuestion.explanation} />
        </div>
      ) : null}

      {followUp ? (
        <p className="text-xs text-muted-foreground border-l-2 border-border pl-3">
          <span className="font-medium">Follow-up:</span> {followUp}
        </p>
      ) : null}
    </div>
  );
}

function RevisionPlanArtifactBody({ payload }: { payload: ArtifactPayload }) {
  const record = asRecord(payload);
  const days = extractRevisionDays(payload);
  const summary = asString(record?.summary);
  const horizonDays = typeof record?.horizon_days === 'number' ? record.horizon_days : null;

  if (days.length === 0 && !summary) {
    return <ArtifactFallbackBody payload={payload} />;
  }

  return (
    <div className="space-y-5">
      {(horizonDays || days.length > 0) ? (
        <p className="text-xs text-muted-foreground">
          {horizonDays ? `${horizonDays}-day horizon` : ''}{horizonDays && days.length > 0 ? ' · ' : ''}{days.length > 0 ? `${days.length} planned sessions` : ''}
        </p>
      ) : null}

      {summary ? (
        <div className="text-sm text-foreground leading-relaxed">
          <RichTutorContent content={summary} />
        </div>
      ) : null}

      <div className="space-y-4">
        {days.map((day, index) => (
          <div key={`${day.dayLabel}-${index}`} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-xs font-semibold text-gold bg-gold/10 mt-0.5">
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">{day.dayLabel}</h3>
                {day.scheduledFor ? <span className="text-xs text-muted-foreground">{formatDateLabel(day.scheduledFor)}</span> : null}
              </div>
              {day.rationale ? <div className="mt-1 text-sm text-foreground/80"><RichTutorContent content={day.rationale} /></div> : null}
              {day.activities.length > 0 ? (
                <ul className="mt-2 space-y-1">
                  {day.activities.map((activity) => (
                    <li key={activity} className="flex gap-2.5 text-sm text-foreground/90">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-gold/70" />
                      <span>{activity}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {day.focusConcepts.length > 0 ? (
                <p className="mt-1.5 text-xs text-muted-foreground">Focus: {day.focusConcepts.join(', ')}</p>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function GenericArtifactBody({ payload }: { payload: ArtifactPayload }) {
  const record = asRecord(payload);
  const content = asString(record?.content) || asString(record?.summary) || asString(record?.text);
  const primitiveEntries = Object.entries(record || {}).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value));

  return (
    <div className="space-y-4">
      {content ? (
        <div className="text-sm text-foreground leading-relaxed">
          <RichTutorContent content={content} />
        </div>
      ) : null}
      {primitiveEntries.length > 0 ? (
        <div className="space-y-2">
          {primitiveEntries.map(([key, value]) => (
            <div key={key}>
              <span className="text-xs font-medium text-muted-foreground">{key.replace(/_/g, ' ')}: </span>
              <span className="text-sm text-foreground">{String(value)}</span>
            </div>
          ))}
        </div>
      ) : null}
      {!content ? <ArtifactFallbackBody payload={payload} /> : null}
    </div>
  );
}

function ArtifactFallbackBody({ payload }: { payload: ArtifactPayload }) {
  return (
    <div className="rounded-3xl border border-border bg-background/70 p-5">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        <FileJson className="h-4 w-4" />
        Raw artifact payload
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-foreground/80">
        {JSON.stringify(payload ?? {}, null, 2)}
      </pre>
    </div>
  );
}

export function ArtifactViewerCard({
  artifactKey,
  type,
  title,
  payload,
  subtitle,
  createdAt,
  isGenerating = false,
  className,
  downloadFileName,
  onAddToNotes,
  onQuizSubmission,
}: ArtifactViewerCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentFlashcardIndex, setCurrentFlashcardIndex] = useState(0);
  const [flashcardFlipped, setFlashcardFlipped] = useState(false);
  const [currentQuizIndex, setCurrentQuizIndex] = useState(0);
  const [quizAnswers, setQuizAnswers] = useState<Record<number, QuizAnswerState>>({});

  const flashcards = useMemo(() => extractFlashcards(payload), [payload]);
  const quizQuestions = useMemo(() => extractQuizQuestions(payload), [payload]);
  const quizStats = useMemo(() => {
    const answered = Object.values(quizAnswers).filter((entry) => entry.submitted).length;
    const correct = quizQuestions.reduce((count, question, index) => {
      const response = quizAnswers[index];
      if (!response?.submitted) return count;
      return normalizeAnswer(response.answer) === normalizeAnswer(question.correctAnswer) ? count + 1 : count;
    }, 0);
    return { answered, correct, total: quizQuestions.length };
  }, [quizAnswers, quizQuestions]);
  useEffect(() => {
    setCurrentFlashcardIndex(0);
    setFlashcardFlipped(false);
    setCurrentQuizIndex(0);
    setQuizAnswers({});
  }, [payload, type]);

  const Icon = ARTIFACT_TYPE_ICON[type] || FileJson;
  const colorClass = ARTIFACT_TYPE_COLOR[type] || 'text-muted-foreground bg-muted border-border';
  const canOpen = Boolean(payload) && !isGenerating;
  const resolvedDownloadFileName = downloadFileName || `${type}-${title.toLowerCase().replace(/\s+/g, '-')}.json`;
  const resolvedArtifactKey = artifactKey || resolvedDownloadFileName;
  const openLabel = type === 'quiz' ? (quizStats.answered > 0 ? 'Continue quiz' : 'Start quiz') : type === 'flashcards' ? 'Study deck' : 'Open artifact';
  const modalBody = (
    <>
      {type === 'notes' ? (
        <NotesArtifactBody payload={payload} />
      ) : type === 'flashcards' ? (
        <FlashcardsArtifactBody
          payload={payload}
          currentIndex={currentFlashcardIndex}
          flipped={flashcardFlipped}
          onPrevious={() => {
            setCurrentFlashcardIndex((index) => Math.max(0, index - 1));
            setFlashcardFlipped(false);
          }}
          onNext={() => {
            setCurrentFlashcardIndex((index) => Math.min(flashcards.length - 1, index + 1));
            setFlashcardFlipped(false);
          }}
          onFlip={() => setFlashcardFlipped((value) => !value)}
          onReset={() => {
            setCurrentFlashcardIndex(0);
            setFlashcardFlipped(false);
          }}
        />
      ) : type === 'quiz' ? (
        <QuizArtifactBody
          payload={payload}
          currentIndex={currentQuizIndex}
          answers={quizAnswers}
          onCurrentIndexChange={setCurrentQuizIndex}
          onAnswerChange={(index, answer) => {
            setQuizAnswers((current) => ({
              ...current,
              [index]: {
                answer,
                submitted: current[index]?.submitted ?? false,
                showExplanation: current[index]?.showExplanation ?? false,
              },
            }));
          }}
          onSubmit={(index) => {
            const question = quizQuestions[index];
            const submittedAnswer = quizAnswers[index]?.answer || '';
            const wasCorrect = question
              ? normalizeAnswer(submittedAnswer) === normalizeAnswer(question.correctAnswer)
              : false;

            setQuizAnswers((current) => ({
              ...current,
              [index]: {
                answer: current[index]?.answer || '',
                submitted: true,
                showExplanation: current[index]?.showExplanation ?? false,
              },
            }));

            if (question && onQuizSubmission) {
              onQuizSubmission({
                artifactKey: resolvedArtifactKey,
                artifactTitle: title,
                questionId: question.questionId,
                question: question.question,
                concept: question.concept,
                userAnswer: submittedAnswer,
                correctAnswer: question.correctAnswer,
                explanation: question.explanation,
                wasCorrect,
              });
            }
          }}
          onToggleExplanation={(index) => {
            setQuizAnswers((current) => ({
              ...current,
              [index]: {
                answer: current[index]?.answer || '',
                submitted: current[index]?.submitted ?? false,
                showExplanation: !(current[index]?.showExplanation ?? false),
              },
            }));
          }}
          onReset={() => {
            setCurrentQuizIndex(0);
            setQuizAnswers({});
          }}
        />
      ) : type === 'revision_plan' ? (
        <RevisionPlanArtifactBody payload={payload} />
      ) : type === 'concept_card' ? (
        <GenericArtifactBody payload={payload} />
      ) : (
        <GenericArtifactBody payload={payload} />
      )}
    </>
  );

  return (
    <>
      <div className={cn('rounded-xl border border-border bg-card/95 px-3 py-2.5 transition-colors hover:border-gold/20', className)}>
        <div className="flex items-center gap-2.5">
          <Icon className={cn('h-4 w-4 shrink-0', colorClass.split(' ')[0])} />
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold text-foreground">{title}</h3>
            {subtitle ? <p className="text-[11px] text-muted-foreground truncate">{subtitle}</p> : null}
          </div>
          {isGenerating ? <Sparkles className="h-3.5 w-3.5 text-gold animate-pulse shrink-0" /> : null}
          <button
            type="button"
            onClick={() => canOpen && setIsOpen(true)}
            disabled={!canOpen}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gold/20 bg-gold/10 px-2.5 py-1 text-[11px] font-medium text-gold transition-colors hover:bg-gold/15 disabled:cursor-not-allowed disabled:opacity-40 shrink-0"
          >
            {isGenerating ? 'Generating…' : openLabel}
          </button>
        </div>
      </div>

      <ArtifactModal
        open={isOpen}
        onClose={() => setIsOpen(false)}
        title={title}
        type={type}
        createdAt={createdAt}
        onDownload={payload ? () => downloadPayload(payload, resolvedDownloadFileName) : undefined}
      >
        {onAddToNotes ? (
          <SelectableCapture onCapture={onAddToNotes}>{modalBody}</SelectableCapture>
        ) : modalBody}
      </ArtifactModal>
    </>
  );
}
