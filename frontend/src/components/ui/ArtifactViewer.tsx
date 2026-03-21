import { type ReactNode, useEffect, useMemo, useState } from 'react';
import {
  Brain,
  CheckCircle2,
  ChevronDown,
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
  ARTIFACT_TYPE_BADGE,
  ARTIFACT_TYPE_COLOR,
  ARTIFACT_TYPE_ICON,
} from '../icons/ArtifactIcons';
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
  badge?: string;
  isGenerating?: boolean;
  className?: string;
  downloadFileName?: string;
  onAddToNotes?: (text: string) => void;
  onQuizSubmission?: (signal: QuizSubmissionSignal) => void;
};

type PreviewInfo = {
  description: string | null;
  chips: string[];
};

type ArtifactDetailRow = {
  label: string;
  value: string;
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

function truncateText(value: string | null, limit = 132) {
  if (!value) return null;
  return value.length > limit ? `${value.slice(0, limit - 1).trimEnd()}…` : value;
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

function getPreviewInfo(
  type: string,
  payload: ArtifactPayload,
  quizStats?: { answered: number; correct: number; total: number },
): PreviewInfo {
  const record = asRecord(payload);
  const notesSections = Array.isArray(record?.sections) ? record.sections.length : 0;
  const notesNextActions = asStringArray(record?.next_actions);
  const flashcards = extractFlashcards(payload);
  const quizQuestions = extractQuizQuestions(payload);
  const revisionDays = extractRevisionDays(payload);

  if (type === 'notes') {
    return {
      description: asString(record?.summary) || asString(record?.content) || asString(record?.text),
      chips: [
        notesSections > 0 ? `${notesSections} sections` : null,
        notesNextActions.length > 0 ? `${notesNextActions.length} next actions` : null,
      ].filter((item): item is string => Boolean(item)),
    };
  }

  if (type === 'flashcards') {
    return {
      description: asString(record?.deck_strategy) || 'Practice key concepts as a guided flashcard deck.',
      chips: [`${flashcards.length} cards`],
    };
  }

  if (type === 'quiz') {
    return {
      description: asString(record?.quiz_focus) || 'Check your understanding with a guided quiz.',
      chips: [
        quizStats && quizStats.answered > 0 ? `${quizStats.correct}/${quizStats.total} correct` : null,
        quizStats && quizStats.answered > 0 ? `${quizStats.answered}/${quizStats.total} answered` : null,
        quizQuestions.length > 0 ? `${quizQuestions.length} questions` : null,
      ].filter((item): item is string => Boolean(item)),
    };
  }

  if (type === 'revision_plan') {
    return {
      description: asString(record?.summary) || 'Review plan generated from your notebook sessions.',
      chips: [
        revisionDays.length > 0 ? `${revisionDays.length} days` : null,
        typeof record?.horizon_days === 'number' ? `${record.horizon_days} day horizon` : null,
      ].filter((item): item is string => Boolean(item)),
    };
  }

  if (type === 'concept_card') {
    return {
      description: asString(record?.summary) || asString(record?.content) || 'Concept artifact',
      chips: [asString(record?.concept)].filter((item): item is string => Boolean(item)),
    };
  }

  return {
    description: asString(record?.summary) || asString(record?.content) || 'Structured artifact',
    chips: [],
  };
}

function getArtifactDetailRows(
  type: string,
  payload: ArtifactPayload,
  quizStats: { answered: number; correct: number; total: number },
): ArtifactDetailRow[] {
  const record = asRecord(payload);
  if (!record) return [];

  if (type === 'notes') {
    const summary = truncateText(asString(record.summary), 160);
    const coverage = asStringArray(record.coverage_concepts).slice(0, 4).join(', ');
    return [
      summary ? { label: 'Summary', value: summary } : null,
      coverage ? { label: 'Coverage', value: coverage } : null,
    ].filter((item): item is ArtifactDetailRow => Boolean(item));
  }

  if (type === 'flashcards') {
    const strategy = truncateText(asString(record.deck_strategy), 140);
    const focus = extractFlashcards(payload)
      .map((card) => card.concept)
      .filter(Boolean)
      .slice(0, 4)
      .join(', ');
    return [
      strategy ? { label: 'Deck strategy', value: strategy } : null,
      focus ? { label: 'Focus concepts', value: focus } : null,
    ].filter((item): item is ArtifactDetailRow => Boolean(item));
  }

  if (type === 'quiz') {
    const focus = truncateText(asString(record.quiz_focus), 160);
    const followUp = truncateText(asString(record.recommended_follow_up), 160);
    return [
      focus ? { label: 'Quiz focus', value: focus } : null,
      quizStats.answered > 0 ? { label: 'Current result', value: `${quizStats.correct}/${quizStats.total} correct, ${quizStats.answered}/${quizStats.total} answered` } : null,
      followUp ? { label: 'Follow-up', value: followUp } : null,
    ].filter((item): item is ArtifactDetailRow => Boolean(item));
  }

  if (type === 'revision_plan') {
    const summary = truncateText(asString(record.summary), 160);
    const firstFocus = extractRevisionDays(payload)
      .flatMap((day) => day.focusConcepts)
      .slice(0, 4)
      .join(', ');
    return [
      summary ? { label: 'Plan summary', value: summary } : null,
      firstFocus ? { label: 'Focus concepts', value: firstFocus } : null,
    ].filter((item): item is ArtifactDetailRow => Boolean(item));
  }

  const fallbackSummary = truncateText(asString(record.summary) || asString(record.content), 160);
  return fallbackSummary ? [{ label: 'Details', value: fallbackSummary }] : [];
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
  badge,
  createdAt,
  onDownload,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  title: string;
  type: string;
  badge?: string;
  createdAt?: string;
  onDownload?: () => void;
}) {
  const Icon = ARTIFACT_TYPE_ICON[type] || FileJson;
  const colorClass = ARTIFACT_TYPE_COLOR[type] || 'text-muted-foreground bg-muted border-border';
  const badgeClass = ARTIFACT_TYPE_BADGE[type] || 'bg-muted text-muted-foreground border-border';

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
        className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-border bg-card shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border/50 px-6 py-5">
          <div className="flex min-w-0 items-start gap-4">
            <div className={cn('rounded-2xl border p-3', colorClass)}>
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-xl font-semibold text-foreground">{title}</h2>
                {badge ? (
                  <span className={cn('rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.14em]', badgeClass)}>
                    {badge}
                  </span>
                ) : null}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <span>{type.replace(/_/g, ' ')}</span>
                {createdAt ? <span>{formatDateLabel(createdAt)}</span> : null}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {onDownload ? (
              <button
                type="button"
                onClick={onDownload}
                className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-gold/30 hover:bg-gold/5"
              >
                <Download className="h-4 w-4" />
                Download
              </button>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-6">{children}</div>
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
    <div className="space-y-6">
      {summary ? (
        <div className="rounded-3xl border border-gold/15 bg-gold/[0.05] px-5 py-4">
          <RichTutorContent content={summary} />
        </div>
      ) : null}

      {sections.length > 0 ? (
        <div className="space-y-4">
          {sections.map((section, index) => {
            const bullets = asStringArray(section.bullets);
            const heading = asString(section.heading) || `Section ${index + 1}`;
            const takeaway = asString(section.key_takeaway);
            const sessionIds = asStringArray(section.source_session_ids);
            const concepts = asStringArray(section.concepts);

            return (
              <div key={`${heading}-${index}`} className="rounded-3xl border border-border/60 bg-background/60 p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-semibold text-foreground">{heading}</h3>
                  {sessionIds.length > 0 ? (
                    <span className="rounded-full border border-border px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                      {sessionIds.length} session sources
                    </span>
                  ) : null}
                </div>

                {bullets.length > 0 ? (
                  <div className="mt-4 space-y-3">
                    {bullets.map((bullet) => (
                      <div key={bullet} className="flex gap-3">
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gold" />
                        <div className="min-w-0 flex-1 text-sm text-foreground">
                          <RichTutorContent content={bullet} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}

                {takeaway ? (
                  <div className="mt-4 rounded-2xl border border-gold/15 bg-gold/10 px-4 py-3 text-sm text-foreground">
                    <span className="font-semibold">Key takeaway:</span> {takeaway}
                  </div>
                ) : null}

                {concepts.length > 0 ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {concepts.map((concept) => (
                      <span key={concept} className="rounded-full border border-border px-3 py-1 text-xs text-foreground">
                        {concept}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {nextActions.length > 0 ? (
        <div>
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Next actions</p>
          <div className="flex flex-wrap gap-2">
            {nextActions.map((action) => (
              <span key={action} className="rounded-full border border-border px-3 py-1.5 text-sm text-foreground">
                {action}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {coverageConcepts.length > 0 ? (
        <div>
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Coverage concepts</p>
          <div className="flex flex-wrap gap-2">
            {coverageConcepts.map((concept) => (
              <span key={concept} className="rounded-full border border-border bg-background/70 px-3 py-1.5 text-sm text-foreground">
                {concept}
              </span>
            ))}
          </div>
        </div>
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
  const record = asRecord(payload);
  const cards = extractFlashcards(payload);
  const currentCard = cards[currentIndex];
  const title = asString(record?.title);
  const deckStrategy = asString(record?.deck_strategy);

  if (!currentCard) {
    return <ArtifactFallbackBody payload={payload} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {title ? <span className="rounded-full border border-border px-3 py-1 text-xs text-foreground">{title}</span> : null}
        {deckStrategy ? <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">{deckStrategy}</span> : null}
        <span className="rounded-full border border-border px-3 py-1 text-xs text-foreground">Card {currentIndex + 1} of {cards.length}</span>
      </div>

      <div className="rounded-[28px] border border-border bg-background/60 p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {currentCard.concept ? <span className="rounded-full border border-border px-3 py-1 text-xs text-foreground">{currentCard.concept}</span> : null}
            {currentCard.difficulty ? <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">{currentCard.difficulty}</span> : null}
          </div>
          <button
            type="button"
            onClick={onFlip}
            className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-gold/30 hover:bg-gold/5"
          >
            {flipped ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            {flipped ? 'Hide answer' : 'Reveal answer'}
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-3xl border border-border bg-card/70 p-5">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Prompt</p>
            <div className="text-base text-foreground">
              <RichTutorContent content={currentCard.front} />
            </div>
          </div>
          <div className={cn(
            'rounded-3xl border p-5 transition-all',
            flipped ? 'border-gold/25 bg-gold/[0.05]' : 'border-border bg-card/40',
          )}>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Answer</p>
            {flipped ? (
              <div className="text-base text-foreground">
                <RichTutorContent content={currentCard.back} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Reveal the back of the card when you want to check yourself.</p>
            )}
          </div>
        </div>

        {currentCard.studyHint ? (
          <div className="mt-4 rounded-2xl border border-border bg-card/60 px-4 py-3">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Study hint</p>
            <p className="text-sm text-foreground">{currentCard.studyHint}</p>
          </div>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onPrevious}
            disabled={currentIndex === 0}
            className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" />
            Previous
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={currentIndex >= cards.length - 1}
            className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 disabled:opacity-40"
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 hover:text-foreground"
        >
          <RotateCcw className="h-4 w-4" />
          Restart deck
        </button>
      </div>
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
  const quizFocus = asString(record?.quiz_focus);
  const followUp = asString(record?.recommended_follow_up);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-gold/20 bg-gold/10 px-3 py-1 text-xs text-gold">{correctCount}/{questions.length} correct</span>
          <span className="rounded-full border border-border px-3 py-1 text-xs text-foreground">{answeredCount}/{questions.length} answered</span>
          {quizFocus ? <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">{quizFocus}</span> : null}
        </div>
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 hover:text-foreground"
        >
          <RotateCcw className="h-4 w-4" />
          Reset quiz
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {questions.map((question, index) => {
          const response = answers[index];
          const answered = Boolean(response?.submitted);
          const correct = answered && normalizeAnswer(response?.answer || '') === normalizeAnswer(question.correctAnswer);
          return (
            <button
              key={question.questionId}
              type="button"
              onClick={() => onCurrentIndexChange(index)}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-full border text-xs font-semibold transition-colors',
                index === currentIndex
                  ? 'border-gold bg-gold/10 text-gold'
                  : correct
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500'
                    : answered
                      ? 'border-red-500/30 bg-red-500/10 text-red-500'
                      : 'border-border text-muted-foreground hover:border-gold/20 hover:text-foreground',
              )}
            >
              {index + 1}
            </button>
          );
        })}
      </div>

      <div className="rounded-[28px] border border-border bg-background/60 p-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-border px-3 py-1 text-xs text-foreground">Question {currentIndex + 1}</span>
          {currentQuestion.concept ? <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">{currentQuestion.concept}</span> : null}
          {currentQuestion.difficulty ? <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">{currentQuestion.difficulty}</span> : null}
        </div>

        <div className="rounded-3xl border border-border bg-card/70 p-5">
          <RichTutorContent content={currentQuestion.question} />
        </div>

        <div className="mt-4 space-y-3">
          {hasOptions ? (
            currentQuestion.options.map((option, optionIndex) => {
              const isSelected = currentState.answer === option;
              const isCorrectOption = currentState.submitted && normalizeAnswer(option) === normalizeAnswer(currentQuestion.correctAnswer);
              const isWrongSelection = currentState.submitted && isSelected && !isCorrect;
              return (
                <button
                  key={`${option}-${optionIndex}`}
                  type="button"
                  onClick={() => !currentState.submitted && onAnswerChange(currentIndex, option)}
                  disabled={currentState.submitted}
                  className={cn(
                    'flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition-colors',
                    !currentState.submitted && isSelected
                      ? 'border-gold/30 bg-gold/10 text-foreground'
                      : !currentState.submitted
                        ? 'border-border bg-card/50 text-foreground hover:border-gold/20'
                        : isCorrectOption
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-foreground'
                          : isWrongSelection
                            ? 'border-red-500/30 bg-red-500/10 text-foreground'
                            : 'border-border/60 bg-card/30 text-muted-foreground',
                  )}
                >
                  <span className={cn(
                    'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold',
                    !currentState.submitted && isSelected
                      ? 'border-gold bg-gold/20 text-gold'
                      : isCorrectOption
                        ? 'border-emerald-500 bg-emerald-500/20 text-emerald-500'
                        : isWrongSelection
                          ? 'border-red-500 bg-red-500/20 text-red-500'
                          : 'border-border text-muted-foreground',
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
              className="min-h-[120px] w-full resize-none rounded-2xl border border-border bg-card/60 px-4 py-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/50 focus:border-gold/30 disabled:opacity-70"
            />
          )}
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onCurrentIndexChange(Math.max(0, currentIndex - 1))}
              disabled={currentIndex === 0}
              className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </button>
            <button
              type="button"
              onClick={() => onCurrentIndexChange(Math.min(questions.length - 1, currentIndex + 1))}
              disabled={currentIndex >= questions.length - 1}
              className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 disabled:opacity-40"
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="flex items-center gap-2">
            {currentState.submitted && currentQuestion.explanation ? (
              <button
                type="button"
                onClick={() => onToggleExplanation(currentIndex)}
                className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-gold/30 hover:bg-gold/5"
              >
                <HelpCircle className="h-4 w-4" />
                {currentState.showExplanation ? 'Hide explanation' : 'Show explanation'}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => onSubmit(currentIndex)}
              disabled={!canSubmit}
              className="inline-flex items-center gap-2 rounded-xl bg-gold px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-gold/90 disabled:opacity-40"
            >
              <CheckCircle2 className="h-4 w-4" />
              Check answer
            </button>
          </div>
        </div>

        {currentState.submitted ? (
          <div className={cn(
            'mt-4 rounded-2xl border px-4 py-3 text-sm',
            isCorrect ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400',
          )}>
            <p className="font-medium">{isCorrect ? 'Correct answer.' : 'Not quite.'}</p>
            {!isCorrect && currentQuestion.correctAnswer ? (
              <p className="mt-1">Correct answer: <span className="font-semibold">{currentQuestion.correctAnswer}</span></p>
            ) : null}
          </div>
        ) : null}

        {currentState.submitted && currentState.showExplanation && currentQuestion.explanation ? (
          <div className="mt-4 rounded-2xl border border-border bg-card/60 px-4 py-4">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              <Sparkles className="h-4 w-4" />
              Explanation
            </div>
            <RichTutorContent content={currentQuestion.explanation} />
          </div>
        ) : null}
      </div>

      {followUp ? (
        <div className="rounded-2xl border border-border bg-card/50 px-4 py-3">
          <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            <Brain className="h-4 w-4" />
            Recommended follow-up
          </div>
          <RichTutorContent content={followUp} />
        </div>
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
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {horizonDays ? <span className="rounded-full border border-border px-3 py-1 text-xs text-foreground">{horizonDays} day horizon</span> : null}
        {days.length > 0 ? <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">{days.length} planned sessions</span> : null}
      </div>

      {summary ? (
        <div className="rounded-3xl border border-gold/15 bg-gold/[0.05] px-5 py-4">
          <RichTutorContent content={summary} />
        </div>
      ) : null}

      <div className="space-y-4">
        {days.map((day, index) => (
          <div key={`${day.dayLabel}-${index}`} className="flex gap-4 rounded-3xl border border-border bg-background/60 p-5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-gold/20 bg-gold/10 text-sm font-semibold text-gold">
              {index + 1}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-foreground">{day.dayLabel}</h3>
                {day.scheduledFor ? <span className="rounded-full border border-border px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{formatDateLabel(day.scheduledFor)}</span> : null}
              </div>
              {day.rationale ? <div className="mt-2 text-sm text-foreground"><RichTutorContent content={day.rationale} /></div> : null}
              {day.activities.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {day.activities.map((activity) => (
                    <div key={activity} className="flex gap-3 text-sm text-foreground">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gold" />
                      <span>{activity}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {day.focusConcepts.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {day.focusConcepts.map((concept) => (
                    <span key={concept} className="rounded-full border border-border px-3 py-1 text-xs text-foreground">
                      {concept}
                    </span>
                  ))}
                </div>
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
    <div className="space-y-5">
      {content ? (
        <div className="rounded-3xl border border-border bg-background/60 p-5">
          <RichTutorContent content={content} />
        </div>
      ) : null}
      {primitiveEntries.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {primitiveEntries.map(([key, value]) => (
            <div key={key} className="rounded-2xl border border-border bg-card/60 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{key.replace(/_/g, ' ')}</p>
              <p className="mt-2 text-sm text-foreground">{String(value)}</p>
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
  badge,
  isGenerating = false,
  className,
  downloadFileName,
  onAddToNotes,
  onQuizSubmission,
}: ArtifactViewerCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [currentFlashcardIndex, setCurrentFlashcardIndex] = useState(0);
  const [flashcardFlipped, setFlashcardFlipped] = useState(false);
  const [currentQuizIndex, setCurrentQuizIndex] = useState(0);
  const [quizAnswers, setQuizAnswers] = useState<Record<number, QuizAnswerState>>({});

  const record = asRecord(payload);
  const generation = asRecord(record?.generation);
  const sourceCounts = asRecord(record?.source_counts);
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
  const previewInfo = useMemo(() => getPreviewInfo(type, payload, quizStats), [payload, quizStats, type]);
  const detailRows = useMemo(() => getArtifactDetailRows(type, payload, quizStats), [payload, quizStats, type]);

  useEffect(() => {
    setDetailsOpen(false);
    setCurrentFlashcardIndex(0);
    setFlashcardFlipped(false);
    setCurrentQuizIndex(0);
    setQuizAnswers({});
  }, [payload, type]);

  const Icon = ARTIFACT_TYPE_ICON[type] || FileJson;
  const colorClass = ARTIFACT_TYPE_COLOR[type] || 'text-muted-foreground bg-muted border-border';
  const badgeClass = ARTIFACT_TYPE_BADGE[type] || 'bg-muted text-muted-foreground border-border';
  const metadata = [
    formatDateLabel(createdAt),
    asString(generation?.strategy),
    sourceCounts?.sessions != null ? `${String(sourceCounts.sessions)} sessions` : null,
  ].filter((item): item is string => Boolean(item));
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
      <div className={cn('rounded-xl border border-border bg-card/95 px-3 py-3 transition-colors hover:border-gold/20', className)}>
        <div className="flex items-start gap-3">
          <div className={cn('rounded-xl border p-2.5 shrink-0', colorClass)}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-sm font-semibold text-foreground">{title}</h3>
              {badge ? (
                <span className={cn('rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.14em]', badgeClass)}>
                  {badge}
                </span>
              ) : null}
              {isGenerating ? <Sparkles className="h-3.5 w-3.5 text-gold animate-pulse" /> : null}
              <button
                type="button"
                onClick={() => setDetailsOpen((value) => !value)}
                className="ml-auto inline-flex items-center gap-1 rounded-full border border-border px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:border-gold/20 hover:text-foreground"
              >
                Details
                <ChevronDown className={cn('h-3 w-3 transition-transform', detailsOpen && 'rotate-180')} />
              </button>
            </div>
            {subtitle ? <p className="mt-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{subtitle}</p> : null}
            {metadata.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                {metadata.map((item) => (
                  <span key={item} className="rounded-full border border-border px-2 py-0.5">{item}</span>
                ))}
              </div>
            ) : null}
            {previewInfo.chips.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {previewInfo.chips.slice(0, 4).map((chip) => (
                  <span key={chip} className="rounded-full border border-border bg-background/60 px-2 py-0.5 text-[10px] text-foreground">
                    {chip}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {detailsOpen && detailRows.length > 0 ? (
          <div className="mt-3 space-y-2 border-t border-border/60 pt-3">
            {detailRows.map((row) => (
              <div key={row.label} className="grid gap-1 sm:grid-cols-[88px_minmax(0,1fr)]">
                <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{row.label}</span>
                <p className="text-sm leading-relaxed text-foreground/90">{row.value}</p>
              </div>
            ))}
          </div>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-3">
          <button
            type="button"
            onClick={() => canOpen && setIsOpen(true)}
            disabled={!canOpen}
            className="inline-flex items-center gap-2 rounded-lg border border-gold/20 bg-gold/10 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gold transition-colors hover:bg-gold/15 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {type === 'quiz' ? <Brain className="h-3.5 w-3.5" /> : type === 'flashcards' ? <Eye className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
            {isGenerating ? 'Generating…' : openLabel}
          </button>

          {payload ? (
            <button
              type="button"
              onClick={() => downloadPayload(payload, resolvedDownloadFileName)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:border-gold/30 hover:bg-gold/5 hover:text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              Download JSON
            </button>
          ) : null}
        </div>
      </div>

      <ArtifactModal
        open={isOpen}
        onClose={() => setIsOpen(false)}
        title={title}
        type={type}
        badge={badge}
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
