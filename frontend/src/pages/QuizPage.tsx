import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  XCircle,
  Loader2,
  Target,
  Sparkles,
  BarChart3,
  RotateCcw,
  BookOpen,
  Trophy,
  Zap,
  Clock,
} from 'lucide-react';
import { useGenerateQuiz, useSubmitQuizAnswer, useQuizResults } from '../api/hooks';
import type {
  QuizGenerateResponse,
  QuizAnswerResponse,
} from '../types/api';

type QuizPhase = 'generating' | 'active' | 'reviewing' | 'results';

interface AnswerState {
  selected: string | null;
  submitted: boolean;
  grade: QuizAnswerResponse | null;
}

export default function QuizPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<QuizPhase>('generating');
  const [quiz, setQuiz] = useState<QuizGenerateResponse | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const [showResults, setShowResults] = useState(false);
  const questionRef = useRef<HTMLDivElement>(null);

  const generateQuiz = useGenerateQuiz();
  const submitAnswer = useSubmitQuizAnswer();
  const quizResults = useQuizResults(showResults && quiz ? quiz.quiz_id : '');

  const numQuestions = parseInt(searchParams.get('n') || '5', 10);

  // Generate quiz on mount
  useEffect(() => {
    if (!sessionId) return;
    generateQuiz.mutate(
      { session_id: sessionId, num_questions: numQuestions },
      {
        onSuccess: (data) => {
          setQuiz(data);
          setPhase('active');
          // Initialize answer states
          const initial: Record<string, AnswerState> = {};
          data.questions.forEach((q) => {
            initial[q.question_id] = { selected: null, submitted: false, grade: null };
          });
          setAnswers(initial);
        },
        onError: () => {
          // Stay on generating with error state
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Scroll to question on change
  useEffect(() => {
    questionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [currentIndex]);

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground text-sm">No session specified.</p>
      </div>
    );
  }

  // ── Generating state ─────────────────────────────────────────────
  if (phase === 'generating') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center space-y-4 animate-fade-up">
          {generateQuiz.isError ? (
            <>
              <div className="w-14 h-14 mx-auto rounded-xl bg-destructive/10 border border-destructive/20 flex items-center justify-center">
                <XCircle className="w-6 h-6 text-destructive" />
              </div>
              <h3 className="font-display text-lg font-semibold text-foreground">
                Failed to generate quiz
              </h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                {(generateQuiz.error as Error)?.message || 'Something went wrong.'}
              </p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={() => {
                    generateQuiz.mutate({ session_id: sessionId, num_questions: numQuestions });
                  }}
                  className="px-4 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5 inline mr-1.5" />
                  Retry
                </button>
                <button
                  onClick={() => navigate(`/sessions/${sessionId}`)}
                  className="px-4 py-2 rounded-lg border border-border text-muted-foreground text-sm hover:text-foreground transition-colors"
                >
                  Back to Session
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="w-14 h-14 mx-auto rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-gold animate-pulse-gold" />
              </div>
              <h3 className="font-display text-lg font-semibold text-foreground">
                Generating your quiz...
              </h3>
              <p className="text-sm text-muted-foreground">
                Creating questions based on your session
              </p>
              <Loader2 className="w-5 h-5 text-gold animate-spin mx-auto" />
            </>
          )}
        </div>
      </div>
    );
  }

  if (!quiz || quiz.questions.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center space-y-4 animate-fade-up">
          <div className="w-14 h-14 mx-auto rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center">
            <Target className="w-6 h-6 text-gold" />
          </div>
          <h3 className="font-display text-lg font-semibold text-foreground">
            No questions generated
          </h3>
          <p className="text-sm text-muted-foreground">
            Try starting a new quiz.
          </p>
          <button
            onClick={() => navigate(`/sessions/${sessionId}`)}
            className="px-4 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors"
          >
            Back to Session
          </button>
        </div>
      </div>
    );
  }

  // ── Results state ────────────────────────────────────────────────
  if (phase === 'results' || showResults) {
    const results = quizResults.data;
    const totalAnswered = Object.values(answers).filter((a) => a.submitted).length;
    const totalCorrect = Object.values(answers).filter(
      (a) => a.grade?.is_correct,
    ).length;
    const scorePercent =
      results?.score_percent ??
      (totalAnswered > 0 ? (totalCorrect / quiz.questions.length) * 100 : 0);

    return (
      <div className="flex h-full">
        <div className="flex-1 overflow-auto">
          <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3 mb-2">
              <button
                onClick={() => navigate(`/sessions/${sessionId}`)}
                className="w-8 h-8 rounded-lg border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-gold/20 transition-all"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
              <h2 className="font-display text-lg font-semibold text-foreground">
                Quiz Results
              </h2>
            </div>

            {/* Score Card */}
            <div className="rounded-xl border border-border bg-card p-6 text-center animate-fade-up">
              <div className="w-20 h-20 mx-auto rounded-full border-4 flex items-center justify-center mb-4"
                style={{
                  borderColor: scorePercent >= 80 ? 'hsl(142 71% 45%)' : scorePercent >= 50 ? 'hsl(var(--gold))' : 'hsl(var(--muted-foreground))',
                }}
              >
                <span className="font-display text-2xl font-bold text-foreground">
                  {Math.round(scorePercent)}%
                </span>
              </div>
              <div className="flex items-center justify-center gap-2 mb-2">
                {scorePercent >= 80 ? (
                  <Trophy className="w-5 h-5 text-emerald-400" />
                ) : scorePercent >= 50 ? (
                  <Zap className="w-5 h-5 text-gold" />
                ) : (
                  <BookOpen className="w-5 h-5 text-muted-foreground" />
                )}
                <h3 className="font-display text-base font-semibold text-foreground">
                  {scorePercent >= 80
                    ? 'Excellent!'
                    : scorePercent >= 50
                      ? 'Good Effort!'
                      : 'Keep Practicing!'}
                </h3>
              </div>
              <p className="text-sm text-muted-foreground">
                {totalCorrect} of {quiz.questions.length} correct
              </p>
              {results?.summary && (
                <p className="text-sm text-card-foreground/80 mt-3 leading-relaxed">
                  {results.summary}
                </p>
              )}
            </div>

            {/* Concept Scores */}
            {results?.concept_scores && Object.keys(results.concept_scores).length > 0 && (
              <div className="rounded-xl border border-border bg-card p-5 animate-fade-up" style={{ animationDelay: '0.05s' }}>
                <div className="flex items-center gap-2 mb-4">
                  <BarChart3 className="w-3.5 h-3.5 text-gold" />
                  <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                    Concept Scores
                  </span>
                </div>
                <div className="space-y-3">
                  {Object.entries(results.concept_scores)
                    .sort(([, a], [, b]) => b - a)
                    .map(([concept, score]) => (
                      <div key={concept} className="space-y-1.5">
                        <div className="flex justify-between items-center">
                          <span className="text-xs text-card-foreground capitalize truncate max-w-[200px]">
                            {concept.replace(/_/g, ' ')}
                          </span>
                          <span className="text-[11px] font-mono text-muted-foreground">
                            {Math.round(score * 100)}%
                          </span>
                        </div>
                        <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{
                              width: `${score * 100}%`,
                              backgroundColor:
                                score >= 0.8
                                  ? 'hsl(142 71% 45%)'
                                  : score >= 0.5
                                    ? 'hsl(var(--gold))'
                                    : 'hsl(var(--muted-foreground))',
                            }}
                          />
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Per-question review */}
            <div className="space-y-3 animate-fade-up" style={{ animationDelay: '0.1s' }}>
              <div className="flex items-center gap-2 mb-1">
                <Target className="w-3.5 h-3.5 text-gold" />
                <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                  Question Review
                </span>
              </div>
              {quiz.questions.map((q, i) => {
                const ans = answers[q.question_id];
                const isCorrect = ans?.grade?.is_correct;
                return (
                  <div
                    key={q.question_id}
                    className={`rounded-xl border p-4 transition-all ${
                      isCorrect
                        ? 'border-emerald-400/20 bg-emerald-400/5'
                        : ans?.submitted
                          ? 'border-destructive/20 bg-destructive/5'
                          : 'border-border bg-card'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5 ${
                          isCorrect
                            ? 'bg-emerald-400/10 border border-emerald-400/20'
                            : ans?.submitted
                              ? 'bg-destructive/10 border border-destructive/20'
                              : 'bg-secondary border border-border'
                        }`}
                      >
                        {isCorrect ? (
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        ) : ans?.submitted ? (
                          <XCircle className="w-3.5 h-3.5 text-destructive" />
                        ) : (
                          <span className="text-[10px] font-mono text-muted-foreground">{i + 1}</span>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-card-foreground mb-1">
                          {q.question_text}
                        </p>
                        {ans?.submitted && ans.grade && (
                          <div className="mt-2 text-xs space-y-1">
                            <p className="text-muted-foreground">
                              <span className="font-medium">Your answer:</span> {ans.selected}
                            </p>
                            {!isCorrect && (
                              <p className="text-emerald-400/80">
                                <span className="font-medium">Correct:</span> {ans.grade.correct_answer}
                              </p>
                            )}
                            {ans.grade.explanation && (
                              <p className="text-muted-foreground/80 italic">
                                {ans.grade.explanation}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Actions */}
            <div className="flex flex-col gap-2.5 pt-2 pb-8 animate-fade-up" style={{ animationDelay: '0.15s' }}>
              <button
                onClick={() => {
                  // Reset and regenerate
                  setPhase('generating');
                  setQuiz(null);
                  setAnswers({});
                  setCurrentIndex(0);
                  setShowResults(false);
                  generateQuiz.mutate(
                    { session_id: sessionId, num_questions: numQuestions },
                    {
                      onSuccess: (data) => {
                        setQuiz(data);
                        setPhase('active');
                        const initial: Record<string, AnswerState> = {};
                        data.questions.forEach((q) => {
                          initial[q.question_id] = { selected: null, submitted: false, grade: null };
                        });
                        setAnswers(initial);
                      },
                    },
                  );
                }}
                className="flex items-center justify-center gap-2 w-full px-4 py-3 rounded-xl bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-all"
              >
                <RotateCcw className="w-4 h-4" />
                Take Another Quiz
              </button>
              <button
                onClick={() => navigate(`/sessions/${sessionId}`)}
                className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl border border-border text-card-foreground text-sm font-medium hover:bg-card hover:border-gold/20 transition-all"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to Session
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Active quiz state ────────────────────────────────────────────
  const currentQuestion = quiz.questions[currentIndex];
  const currentAnswer = answers[currentQuestion.question_id] || {
    selected: null,
    submitted: false,
    grade: null,
  };
  const allAnswered = Object.values(answers).every((a) => a.submitted);
  const answeredCount = Object.values(answers).filter((a) => a.submitted).length;
  const correctCount = Object.values(answers).filter(
    (a) => a.grade?.is_correct,
  ).length;
  const progressPercent = (answeredCount / quiz.questions.length) * 100;

  const handleSelectOption = (option: string) => {
    if (currentAnswer.submitted) return;
    setAnswers((prev) => ({
      ...prev,
      [currentQuestion.question_id]: {
        ...prev[currentQuestion.question_id],
        selected: option,
      },
    }));
  };

  const handleSubmitAnswer = () => {
    if (!currentAnswer.selected || currentAnswer.submitted) return;

    submitAnswer.mutate(
      {
        quiz_id: quiz.quiz_id,
        question_id: currentQuestion.question_id,
        answer: currentAnswer.selected,
      },
      {
        onSuccess: (grade) => {
          setAnswers((prev) => ({
            ...prev,
            [currentQuestion.question_id]: {
              ...prev[currentQuestion.question_id],
              submitted: true,
              grade,
            },
          }));
        },
      },
    );
  };

  const handleNext = () => {
    if (currentIndex < quiz.questions.length - 1) {
      setCurrentIndex(currentIndex + 1);
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  const handleFinish = () => {
    setShowResults(true);
    setPhase('results');
  };

  // Extract option letter
  const getOptionLetter = (option: string): string => {
    const match = option.match(/^([A-D])[.)]/);
    return match ? match[1] : option.charAt(0).toUpperCase();
  };

  return (
    <div className="flex h-full">
      {/* Main quiz area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(`/sessions/${sessionId}`)}
              className="w-8 h-8 rounded-lg border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-gold/20 transition-all"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-semibold text-foreground">
                  Quiz
                </h2>
                <div className="px-2 py-0.5 rounded-md border border-gold/20 bg-gold/10 text-[10px] font-medium text-gold uppercase tracking-wider">
                  {quiz.topic || 'Assessment'}
                </div>
              </div>
              {quiz.quiz_focus && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {quiz.quiz_focus}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-xs text-muted-foreground font-mono">
              {answeredCount}/{quiz.questions.length}
            </div>
            {allAnswered && (
              <button
                onClick={handleFinish}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-400/10 border border-emerald-400/20 text-xs font-medium text-emerald-400 hover:bg-emerald-400/20 transition-all"
              >
                <Trophy className="w-3 h-3" />
                See Results
              </button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-1 w-full bg-secondary">
          <div
            className="h-full bg-gold rounded-r-full transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {/* Question area */}
        <div className="flex-1 overflow-auto px-6 py-8">
          <div className="max-w-2xl mx-auto" ref={questionRef}>
            {/* Question number pills */}
            <div className="flex flex-wrap gap-1.5 mb-6">
              {quiz.questions.map((q, i) => {
                const ans = answers[q.question_id];
                const isCurrent = i === currentIndex;
                return (
                  <button
                    key={q.question_id}
                    onClick={() => setCurrentIndex(i)}
                    className={`w-8 h-8 rounded-lg text-xs font-medium transition-all flex items-center justify-center ${
                      isCurrent
                        ? 'bg-gold/20 border border-gold/30 text-gold'
                        : ans?.grade?.is_correct
                          ? 'bg-emerald-400/10 border border-emerald-400/20 text-emerald-400'
                          : ans?.submitted
                            ? 'bg-destructive/10 border border-destructive/20 text-destructive'
                            : 'bg-card border border-border text-muted-foreground hover:border-gold/20'
                    }`}
                  >
                    {ans?.grade?.is_correct ? (
                      <CheckCircle className="w-3 h-3" />
                    ) : ans?.submitted ? (
                      <XCircle className="w-3 h-3" />
                    ) : (
                      i + 1
                    )}
                  </button>
                );
              })}
            </div>

            {/* Question card */}
            <div className="rounded-xl border border-border bg-card p-6 mb-6 animate-fade-up">
              <div className="flex items-start gap-3 mb-5">
                <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center flex-shrink-0">
                  <span className="text-sm font-display font-bold text-gold">
                    {currentIndex + 1}
                  </span>
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium px-1.5 py-0.5 rounded border border-border bg-secondary/50">
                      {currentQuestion.concept.replace(/_/g, ' ')}
                    </span>
                    <span
                      className={`text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded border ${
                        currentQuestion.difficulty === 'hard'
                          ? 'border-destructive/20 text-destructive bg-destructive/5'
                          : currentQuestion.difficulty === 'easy'
                            ? 'border-emerald-400/20 text-emerald-400 bg-emerald-400/5'
                            : 'border-gold/20 text-gold bg-gold/5'
                      }`}
                    >
                      {currentQuestion.difficulty}
                    </span>
                  </div>
                  <p className="text-base text-foreground leading-relaxed mt-2">
                    {currentQuestion.question_text}
                  </p>
                </div>
              </div>

              {/* Options */}
              <div className="space-y-2.5 pl-11">
                {currentQuestion.options.map((option) => {
                  const letter = getOptionLetter(option);
                  const isSelected = currentAnswer.selected === letter;
                  const isSubmitted = currentAnswer.submitted;
                  const isCorrectOption =
                    isSubmitted &&
                    currentAnswer.grade &&
                    letter === currentAnswer.grade.correct_answer.charAt(0).toUpperCase();
                  const isWrongSelected = isSubmitted && isSelected && !currentAnswer.grade?.is_correct;

                  return (
                    <button
                      key={option}
                      onClick={() => handleSelectOption(letter)}
                      disabled={isSubmitted}
                      className={`w-full text-left rounded-xl border px-4 py-3.5 transition-all flex items-center gap-3 group ${
                        isCorrectOption
                          ? 'border-emerald-400/30 bg-emerald-400/10'
                          : isWrongSelected
                            ? 'border-destructive/30 bg-destructive/10'
                            : isSelected
                              ? 'border-gold/30 bg-gold/10'
                              : 'border-border bg-background hover:border-gold/20 hover:bg-gold/5'
                      } ${isSubmitted ? 'cursor-default' : 'cursor-pointer'}`}
                    >
                      <div
                        className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold transition-all ${
                          isCorrectOption
                            ? 'bg-emerald-400/20 border border-emerald-400/30 text-emerald-400'
                            : isWrongSelected
                              ? 'bg-destructive/20 border border-destructive/30 text-destructive'
                              : isSelected
                                ? 'bg-gold/20 border border-gold/30 text-gold'
                                : 'bg-secondary border border-border text-muted-foreground group-hover:border-gold/20 group-hover:text-gold'
                        }`}
                      >
                        {isCorrectOption ? (
                          <CheckCircle className="w-3.5 h-3.5" />
                        ) : isWrongSelected ? (
                          <XCircle className="w-3.5 h-3.5" />
                        ) : (
                          letter
                        )}
                      </div>
                      <span
                        className={`text-sm leading-relaxed ${
                          isCorrectOption
                            ? 'text-emerald-400'
                            : isWrongSelected
                              ? 'text-destructive/80'
                              : isSelected
                                ? 'text-foreground'
                                : 'text-card-foreground'
                        }`}
                      >
                        {option.replace(/^[A-D][.)]\s*/, '')}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Feedback after submit */}
              {currentAnswer.submitted && currentAnswer.grade && (
                <div
                  className={`mt-4 ml-11 rounded-xl border px-4 py-3 animate-fade-up ${
                    currentAnswer.grade.is_correct
                      ? 'border-emerald-400/20 bg-emerald-400/5'
                      : 'border-destructive/20 bg-destructive/5'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    {currentAnswer.grade.is_correct ? (
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5 text-destructive" />
                    )}
                    <span
                      className={`text-xs font-medium ${
                        currentAnswer.grade.is_correct
                          ? 'text-emerald-400'
                          : 'text-destructive'
                      }`}
                    >
                      {currentAnswer.grade.is_correct ? 'Correct!' : 'Incorrect'}
                    </span>
                  </div>
                  {currentAnswer.grade.feedback && (
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {currentAnswer.grade.feedback}
                    </p>
                  )}
                  {currentAnswer.grade.explanation && !currentAnswer.grade.is_correct && (
                    <p className="text-xs text-muted-foreground/70 mt-1 italic leading-relaxed">
                      {currentAnswer.grade.explanation}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-between">
              <button
                onClick={handlePrev}
                disabled={currentIndex === 0}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:border-gold/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                Previous
              </button>

              <div className="flex gap-2">
                {!currentAnswer.submitted && (
                  <button
                    onClick={handleSubmitAnswer}
                    disabled={!currentAnswer.selected || submitAnswer.isPending}
                    className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm shadow-gold/20"
                  >
                    {submitAnswer.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <CheckCircle className="w-3.5 h-3.5" />
                    )}
                    Submit Answer
                  </button>
                )}
                {currentAnswer.submitted && currentIndex < quiz.questions.length - 1 && (
                  <button
                    onClick={handleNext}
                    className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-all shadow-sm shadow-gold/20"
                  >
                    Next
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
                {currentAnswer.submitted && currentIndex === quiz.questions.length - 1 && allAnswered && (
                  <button
                    onClick={handleFinish}
                    className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-emerald-400 text-primary-foreground text-sm font-medium hover:bg-emerald-400/90 transition-all shadow-sm shadow-emerald-400/20"
                  >
                    <Trophy className="w-3.5 h-3.5" />
                    See Results
                  </button>
                )}
              </div>

              <button
                onClick={handleNext}
                disabled={currentIndex === quiz.questions.length - 1}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:border-gold/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Next
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Right sidebar — quiz status */}
      <div className="w-64 border-l border-border bg-card/30 overflow-auto flex flex-col">
        <div className="p-5 space-y-5 flex-1">
          {/* Quiz Info */}
          <div className="animate-fade-up">
            <div className="flex items-center gap-2 mb-3">
              <Target className="w-3.5 h-3.5 text-gold" />
              <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                Quiz Progress
              </span>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-xs text-muted-foreground">Answered</span>
                <span className="text-xs text-card-foreground font-mono">
                  {answeredCount}/{quiz.questions.length}
                </span>
              </div>
              <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-gold rounded-full transition-all duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              {answeredCount > 0 && (
                <div className="flex justify-between items-center">
                  <span className="text-xs text-muted-foreground">Correct</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-emerald-400 font-mono">{correctCount}</span>
                    <span className="text-[10px] text-muted-foreground/60">/</span>
                    <span className="text-xs text-muted-foreground font-mono">{answeredCount}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Quick nav */}
          <div className="animate-fade-up" style={{ animationDelay: '0.05s' }}>
            <div className="flex items-center gap-2 mb-3">
              <Clock className="w-3.5 h-3.5 text-gold" />
              <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                Questions
              </span>
            </div>
            <div className="grid grid-cols-5 gap-1.5">
              {quiz.questions.map((q, i) => {
                const ans = answers[q.question_id];
                const isCurrent = i === currentIndex;
                return (
                  <button
                    key={q.question_id}
                    onClick={() => setCurrentIndex(i)}
                    className={`w-full aspect-square rounded-lg text-[10px] font-medium transition-all flex items-center justify-center ${
                      isCurrent
                        ? 'bg-gold/20 border border-gold/30 text-gold ring-1 ring-gold/20'
                        : ans?.grade?.is_correct
                          ? 'bg-emerald-400/10 border border-emerald-400/20 text-emerald-400'
                          : ans?.submitted
                            ? 'bg-destructive/10 border border-destructive/20 text-destructive'
                            : 'bg-card border border-border text-muted-foreground hover:border-gold/20'
                    }`}
                  >
                    {i + 1}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Finish button in sidebar */}
          {allAnswered && (
            <div className="animate-fade-up" style={{ animationDelay: '0.1s' }}>
              <button
                onClick={handleFinish}
                className="flex items-center justify-center gap-2 w-full px-4 py-3 rounded-xl bg-emerald-400/10 border border-emerald-400/20 text-emerald-400 text-sm font-medium hover:bg-emerald-400/20 transition-all"
              >
                <Trophy className="w-4 h-4" />
                See Results
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
