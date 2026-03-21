import {
  FlashcardsIcon,
  NotesIcon,
  QuizIcon,
  RevisionPlanIcon,
  SummaryIcon,
} from './ArtifactIcons';

export const ARTIFACT_TYPE_ICON: Record<string, typeof QuizIcon> = {
  quiz: QuizIcon,
  flashcards: FlashcardsIcon,
  notes: NotesIcon,
  summary: SummaryIcon,
  revision_plan: RevisionPlanIcon,
};

export const ARTIFACT_TYPE_COLOR: Record<string, string> = {
  quiz: 'text-amber-600 bg-amber-50 border-amber-200',
  flashcards: 'text-teal-700 bg-teal-50 border-teal-200',
  notes: 'text-gold bg-gold/[0.06] border-gold/20',
  summary: 'text-blue-600 bg-blue-50 border-blue-200',
  revision_plan: 'text-purple-600 bg-purple-50 border-purple-200',
};

export const ARTIFACT_TYPE_BADGE: Record<string, string> = {
  quiz: 'bg-amber-100 text-amber-700 border-amber-200',
  flashcards: 'bg-teal-100 text-teal-700 border-teal-200',
  notes: 'bg-gold/10 text-gold border-gold/20',
  summary: 'bg-blue-100 text-blue-700 border-blue-200',
  revision_plan: 'bg-purple-100 text-purple-700 border-purple-200',
};
