import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen, Sparkles, ArrowLeft, ArrowRight, CheckCircle, FileText, Loader2,
  Layers, GraduationCap, Lightbulb,
} from 'lucide-react';
import { useResources, useResourceTopics, useCreateSession } from '../api/hooks';
import type { TopicInfo } from '../types/api';

export default function NewSessionPage() {
  const navigate = useNavigate();
  const { data: resourcesData, isLoading } = useResources();
  const createSession = useCreateSession();
  const [selectedResourceId, setSelectedResourceId] = useState<string | null>(null);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [step, setStep] = useState<'select' | 'topics' | 'confirm'>('select');

  const { data: topicsData, isLoading: topicsLoading } = useResourceTopics(selectedResourceId || '');

  const resources = resourcesData?.items?.filter(r => r.status === 'ready' || r.status === 'completed') ?? [];
  const selectedResource = resources.find(r => r.id === selectedResourceId);

  const toggleTopic = (topicId: string) => {
    setSelectedTopics(prev =>
      prev.includes(topicId) ? prev.filter(t => t !== topicId) : [...prev, topicId]
    );
  };

  const selectAllTopics = () => {
    if (!topicsData?.topics) return;
    if (selectedTopics.length === topicsData.topics.length) {
      setSelectedTopics([]);
    } else {
      setSelectedTopics(topicsData.topics.map(t => t.topic_id));
    }
  };

  const handleStartSession = async () => {
    if (!selectedResourceId) return;
    try {
      const session = await createSession.mutateAsync({
        resource_id: selectedResourceId,
        selected_topics: selectedTopics.length > 0 ? selectedTopics : undefined,
      });
      navigate(`/sessions/${session.id}`);
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const stepTitles = {
    select: <>Choose a <span className="italic text-gold">resource</span></>,
    topics: <>Select <span className="italic text-gold">topics</span> to study</>,
    confirm: <>Ready to <span className="italic text-gold">begin?</span></>,
  };

  const stepDescriptions = {
    select: 'Select a processed resource to start your tutoring session.',
    topics: 'Choose which topics to focus on, or study all of them.',
    confirm: 'The AI tutor will create a learning plan based on your selections.',
  };

  const steps = [
    { key: 'select', label: 'Resource' },
    { key: 'topics', label: 'Topics' },
    { key: 'confirm', label: 'Start' },
  ] as const;

  const currentStepIdx = steps.findIndex(s => s.key === step);

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      {/* Header */}
      <div className="mb-8 animate-fade-up">
        <button
          onClick={() => {
            if (step === 'topics') setStep('select');
            else if (step === 'confirm') setStep('topics');
            else navigate(-1);
          }}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        <div className="flex items-center gap-2 mb-3">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
            New Session
          </span>
        </div>

        <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight text-foreground leading-tight mb-2">
          {stepTitles[step]}
        </h1>
        <p className="text-muted-foreground max-w-lg">
          {stepDescriptions[step]}
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-3 mb-8 animate-fade-up" style={{ animationDelay: '0.05s' }}>
        {steps.map((s, i) => (
          <div key={s.key} className="flex items-center gap-2">
            {i > 0 && <div className="w-6 h-px bg-border" />}
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium border transition-colors ${
              i < currentStepIdx
                ? 'bg-gold/10 border-gold/20 text-gold'
                : i === currentStepIdx
                  ? 'bg-gold/15 border-gold/30 text-gold'
                  : 'bg-secondary border-border text-muted-foreground'
            }`}>
              {i < currentStepIdx ? <CheckCircle className="w-3.5 h-3.5" /> : i + 1}
            </div>
            <span className={`text-sm font-medium ${
              i === currentStepIdx ? 'text-foreground' : 'text-muted-foreground'
            }`}>
              {s.label}
            </span>
          </div>
        ))}
      </div>

      {/* Step 1: Select Resource */}
      {step === 'select' && (
        <div className="flex-1">
          {isLoading ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="w-6 h-6 text-gold animate-spin" />
            </div>
          ) : resources.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-center animate-fade-up">
              <div className="w-14 h-14 rounded-xl bg-card border border-border flex items-center justify-center mb-4">
                <BookOpen className="w-6 h-6 text-muted-foreground" />
              </div>
              <h3 className="font-display text-lg font-semibold text-foreground mb-1">No resources available</h3>
              <p className="text-sm text-muted-foreground mb-4">Upload and process a PDF first</p>
              <button
                onClick={() => navigate('/resources')}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors"
              >
                Go to Resources <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <div className="grid gap-3 max-w-2xl">
              {resources.map((resource, i) => (
                <button
                  key={resource.id}
                  onClick={() => setSelectedResourceId(resource.id)}
                  className={`group flex items-center gap-4 p-4 rounded-xl border text-left transition-all duration-200 animate-fade-up ${
                    selectedResourceId === resource.id
                      ? 'border-gold/40 bg-gold/[0.06] shadow-md shadow-gold/5'
                      : 'border-border bg-card hover:border-gold/20 hover:bg-card/80'
                  }`}
                  style={{ animationDelay: `${0.1 + i * 0.05}s` }}
                >
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
                    selectedResourceId === resource.id
                      ? 'bg-gold/15 border border-gold/25'
                      : 'bg-secondary border border-border'
                  }`}>
                    <FileText className={`w-5 h-5 ${
                      selectedResourceId === resource.id ? 'text-gold' : 'text-muted-foreground'
                    }`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-card-foreground truncate">
                      {resource.filename}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {resource.topic || 'No topic'} &middot; {new Date(resource.uploaded_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                    selectedResourceId === resource.id
                      ? 'border-gold bg-gold'
                      : 'border-muted-foreground/30'
                  }`}>
                    {selectedResourceId === resource.id && (
                      <CheckCircle className="w-3 h-3 text-primary-foreground" />
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}

          {selectedResourceId && (
            <div className="mt-8 animate-fade-up">
              <button
                onClick={() => { setStep('topics'); setSelectedTopics([]); }}
                className="flex items-center gap-2 px-6 py-3 rounded-lg bg-gold text-primary-foreground font-medium text-sm hover:bg-gold/90 transition-colors shadow-lg shadow-gold/20"
              >
                Continue <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Step 2: Select Topics */}
      {step === 'topics' && selectedResource && (
        <div className="flex-1 animate-fade-up">
          {topicsLoading ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="w-6 h-6 text-gold animate-spin" />
            </div>
          ) : !topicsData?.topics || topicsData.topics.length === 0 ? (
            <div className="max-w-lg">
              <div className="rounded-xl border border-gold/15 bg-gold/[0.04] p-4 mb-6">
                <div className="flex gap-3">
                  <Lightbulb className="w-4 h-4 text-gold mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-card-foreground mb-1">No specific topics found</p>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      The AI tutor will cover all concepts from this resource. You can proceed directly.
                    </p>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setStep('confirm')}
                className="flex items-center gap-2 px-6 py-3 rounded-lg bg-gold text-primary-foreground font-medium text-sm hover:bg-gold/90 transition-colors shadow-lg shadow-gold/20"
              >
                Continue <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <>
              {/* Resource info + select all */}
              <div className="flex items-center justify-between mb-5 max-w-3xl">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center">
                    <FileText className="w-4 h-4 text-gold" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-card-foreground">{selectedResource.filename}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {topicsData.total_concepts} concepts across {topicsData.topics.length} topics
                    </p>
                  </div>
                </div>
                <button
                  onClick={selectAllTopics}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:border-gold/20 transition-colors"
                >
                  {selectedTopics.length === topicsData.topics.length ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              {/* Topic cards grid */}
              <div className="grid gap-3 md:grid-cols-2 max-w-3xl">
                {topicsData.topics.map((topic: TopicInfo, i: number) => {
                  const isSelected = selectedTopics.includes(topic.topic_id);
                  const primaryCount = topic.primary_concepts.length;

                  return (
                    <button
                      key={topic.topic_id}
                      onClick={() => toggleTopic(topic.topic_id)}
                      className={`group relative text-left p-5 rounded-xl border transition-all duration-200 animate-fade-up ${
                        isSelected
                          ? 'border-gold/40 bg-gold/[0.06] shadow-md shadow-gold/5'
                          : 'border-border bg-card hover:border-gold/20 hover:bg-card/80'
                      }`}
                      style={{ animationDelay: `${0.05 + i * 0.04}s` }}
                    >
                      {/* Selection indicator */}
                      <div className={`absolute top-4 right-4 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                        isSelected ? 'border-gold bg-gold' : 'border-muted-foreground/30'
                      }`}>
                        {isSelected && <CheckCircle className="w-3 h-3 text-primary-foreground" />}
                      </div>

                      {/* Topic icon */}
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center mb-3 transition-colors ${
                        isSelected
                          ? 'bg-gold/15 border border-gold/25'
                          : 'bg-secondary border border-border'
                      }`}>
                        <Layers className={`w-4 h-4 ${isSelected ? 'text-gold' : 'text-muted-foreground'}`} />
                      </div>

                      {/* Topic name */}
                      <h3 className="font-display text-sm font-semibold text-card-foreground mb-1.5 pr-6 leading-snug">
                        {topic.topic_name}
                      </h3>

                      {/* Stats */}
                      <div className="flex items-center gap-3 text-[11px] text-muted-foreground mb-3">
                        <span className="flex items-center gap-1">
                          <GraduationCap className="w-3 h-3" />
                          {primaryCount} key concept{primaryCount !== 1 ? 's' : ''}
                        </span>
                        {topic.support_concepts.length > 0 && (
                          <span>+{topic.support_concepts.length} supporting</span>
                        )}
                      </div>

                      {/* Concept chips */}
                      <div className="flex flex-wrap gap-1.5">
                        {topic.primary_concepts.slice(0, 4).map(c => (
                          <span
                            key={c}
                            className={`px-2 py-0.5 rounded-md text-[10px] font-medium border transition-colors ${
                              isSelected
                                ? 'bg-gold/10 border-gold/20 text-gold'
                                : 'bg-secondary border-border text-muted-foreground'
                            }`}
                          >
                            {c.replace(/_/g, ' ')}
                          </span>
                        ))}
                        {topic.primary_concepts.length > 4 && (
                          <span className="px-2 py-0.5 rounded-md text-[10px] text-muted-foreground">
                            +{topic.primary_concepts.length - 4} more
                          </span>
                        )}
                      </div>

                      {/* Prereq indicator */}
                      {topic.prereq_topic_ids.length > 0 && (
                        <div className="mt-3 pt-2.5 border-t border-border/50">
                          <span className="text-[10px] text-muted-foreground/70">
                            Builds on {topic.prereq_topic_ids.length} other topic{topic.prereq_topic_ids.length !== 1 ? 's' : ''}
                          </span>
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Continue button */}
              <div className="mt-8 flex items-center gap-3 animate-fade-up" style={{ animationDelay: '0.3s' }}>
                <button
                  onClick={() => setStep('confirm')}
                  className="flex items-center gap-2 px-6 py-3 rounded-lg bg-gold text-primary-foreground font-medium text-sm hover:bg-gold/90 transition-colors shadow-lg shadow-gold/20"
                >
                  {selectedTopics.length === 0 ? 'Study All Topics' : `Study ${selectedTopics.length} Topic${selectedTopics.length !== 1 ? 's' : ''}`}
                  <ArrowRight className="w-4 h-4" />
                </button>
                {selectedTopics.length > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {selectedTopics.length} of {topicsData.topics.length} selected
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Step 3: Confirm & Start */}
      {step === 'confirm' && selectedResource && (
        <div className="flex-1 max-w-lg animate-fade-up">
          {/* Selected resource preview */}
          <div className="rounded-xl border border-border bg-card p-6 mb-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center">
                <FileText className="w-5 h-5 text-gold" />
              </div>
              <div>
                <p className="text-sm font-medium text-card-foreground">{selectedResource.filename}</p>
                <p className="text-xs text-muted-foreground">{selectedResource.topic || 'No topic'}</p>
              </div>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between py-2 border-t border-border/50">
                <span className="text-muted-foreground">Status</span>
                <span className="text-card-foreground font-medium capitalize">{selectedResource.status}</span>
              </div>
              <div className="flex justify-between py-2 border-t border-border/50">
                <span className="text-muted-foreground">Topics</span>
                <span className="text-card-foreground font-medium">
                  {selectedTopics.length > 0
                    ? `${selectedTopics.length} selected`
                    : 'All topics'}
                </span>
              </div>
              {selectedTopics.length > 0 && topicsData?.topics && (
                <div className="pt-2 border-t border-border/50">
                  <div className="flex flex-wrap gap-1.5">
                    {topicsData.topics
                      .filter(t => selectedTopics.includes(t.topic_id))
                      .map(t => (
                        <span key={t.topic_id} className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-gold/10 border border-gold/20 text-gold">
                          {t.topic_name}
                        </span>
                      ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Info box */}
          <div className="rounded-xl border border-gold/15 bg-gold/[0.04] p-4 mb-8">
            <div className="flex gap-3">
              <Sparkles className="w-4 h-4 text-gold mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-card-foreground mb-1">How it works</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Your AI tutor will create a personalized learning plan for the selected topics
                  and guide you through the material with questions, explanations, and feedback.
                </p>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setStep('topics')}
              className="px-4 py-2.5 rounded-lg border border-border text-sm font-medium text-muted-foreground hover:text-foreground hover:border-gold/20 transition-colors"
            >
              Back
            </button>
            <button
              onClick={handleStartSession}
              disabled={createSession.isPending}
              className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-gold text-primary-foreground font-medium text-sm hover:bg-gold/90 transition-colors shadow-lg shadow-gold/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {createSession.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Start Session
                </>
              )}
            </button>
          </div>

          {createSession.isError && (
            <div className="mt-4 p-3 rounded-lg border border-destructive/30 bg-destructive/10 text-sm text-destructive">
              Failed to create session. Please try again.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
