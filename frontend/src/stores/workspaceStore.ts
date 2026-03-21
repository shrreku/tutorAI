/**
 * Workspace session store (PROD-012 / PROD-009).
 *
 * Manages live study workspace state: objectives, mastery, artifacts,
 * checkpoints, and warnings during an active session.
 */

import { useSyncExternalStore } from 'react';
import type {
  ObjectiveSnapshot,
  ArtifactEventPayload,
  CheckpointRequestedPayload,
  SourceCitationPayload,
  SessionBriefPayload,
} from '../types/session-events';

export interface WorkspaceState {
  // Session context
  sessionId: string | null;
  notebookId: string | null;
  mode: string | null;
  sessionBrief: SessionBriefPayload | null;

  // Live objectives
  objectives: ObjectiveSnapshot[];

  // Live mastery
  mastery: Record<string, number>;
  weakConcepts: string[];

  // Artifacts generated during session
  liveArtifacts: ArtifactEventPayload[];

  // Active checkpoint
  activeCheckpoint: CheckpointRequestedPayload | null;

  // Citations
  citations: SourceCitationPayload[];

  // Warnings
  warnings: Array<{ type: string; message: string; dismissed: boolean }>;

  // Panel visibility
  leftPanelOpen: boolean;
  rightPanelOpen: boolean;

  // Actions
  initSession: (brief: SessionBriefPayload) => void;
  clearSession: () => void;
  updateObjective: (obj: ObjectiveSnapshot) => void;
  updateMastery: (conceptId: string, newScore: number) => void;
  addArtifact: (artifact: ArtifactEventPayload) => void;
  updateArtifact: (artifactId: string, updates: Partial<ArtifactEventPayload>) => void;
  setCheckpoint: (checkpoint: CheckpointRequestedPayload | null) => void;
  addCitation: (citation: SourceCitationPayload) => void;
  addWarning: (type: string, message: string) => void;
  dismissWarning: (index: number) => void;
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;
  setLeftPanelOpen: (open: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
}

type WorkspaceListener = () => void;

const listeners = new Set<WorkspaceListener>();

function emitChange() {
  listeners.forEach((listener) => listener());
}

function updateWorkspaceState(
  updater: Partial<WorkspaceState> | ((state: WorkspaceState) => Partial<WorkspaceState>),
) {
  const nextPartial = typeof updater === 'function' ? updater(workspaceState) : updater;
  workspaceState = { ...workspaceState, ...nextPartial };
  emitChange();
}

function subscribe(listener: WorkspaceListener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

let workspaceState: WorkspaceState = {
  sessionId: null,
  notebookId: null,
  mode: null,
  sessionBrief: null,
  objectives: [],
  mastery: {},
  weakConcepts: [],
  liveArtifacts: [],
  activeCheckpoint: null,
  citations: [],
  warnings: [],
  leftPanelOpen: true,
  rightPanelOpen: true,

  initSession: (brief) =>
    updateWorkspaceState({
      sessionId: brief.session_id,
      notebookId: brief.notebook_id,
      mode: brief.mode,
      sessionBrief: brief,
      objectives: brief.objectives,
      mastery: brief.mastery_snapshot,
      weakConcepts: brief.weak_concepts,
      liveArtifacts: [],
      activeCheckpoint: null,
      citations: [],
      warnings: [],
    }),

  clearSession: () =>
    updateWorkspaceState({
      sessionId: null,
      notebookId: null,
      mode: null,
      sessionBrief: null,
      objectives: [],
      mastery: {},
      weakConcepts: [],
      liveArtifacts: [],
      activeCheckpoint: null,
      citations: [],
      warnings: [],
    }),

  updateObjective: (obj) =>
    updateWorkspaceState((state) => {
      const idx = state.objectives.findIndex((o) => o.objective_id === obj.objective_id);
      if (idx === -1) return { objectives: [...state.objectives, obj] };
      const next = [...state.objectives];
      next[idx] = obj;
      return { objectives: next };
    }),

  updateMastery: (conceptId, newScore) =>
    updateWorkspaceState((state) => ({
      mastery: { ...state.mastery, [conceptId]: newScore },
      weakConcepts: newScore < 0.4
        ? [...new Set([...state.weakConcepts, conceptId])]
        : state.weakConcepts.filter((c) => c !== conceptId),
    })),

  addArtifact: (artifact) =>
    updateWorkspaceState((state) => ({ liveArtifacts: [...state.liveArtifacts, artifact] })),

  updateArtifact: (artifactId, updates) =>
    updateWorkspaceState((state) => ({
      liveArtifacts: state.liveArtifacts.map((a) =>
        a.artifact_id === artifactId ? { ...a, ...updates } : a,
      ),
    })),

  setCheckpoint: (checkpoint) => updateWorkspaceState({ activeCheckpoint: checkpoint }),

  addCitation: (citation) =>
    updateWorkspaceState((state) => ({ citations: [...state.citations, citation] })),

  addWarning: (type, message) =>
    updateWorkspaceState((state) => ({
      warnings: [...state.warnings, { type, message, dismissed: false }],
    })),

  dismissWarning: (index) =>
    updateWorkspaceState((state) => ({
      warnings: state.warnings.map((w, i) => (i === index ? { ...w, dismissed: true } : w)),
    })),

  toggleLeftPanel: () => updateWorkspaceState((state) => ({ leftPanelOpen: !state.leftPanelOpen })),
  toggleRightPanel: () => updateWorkspaceState((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
  setLeftPanelOpen: (open) => updateWorkspaceState({ leftPanelOpen: open }),
  setRightPanelOpen: (open) => updateWorkspaceState({ rightPanelOpen: open }),
};

export function useWorkspaceStore(): WorkspaceState;
export function useWorkspaceStore<T>(selector: (state: WorkspaceState) => T): T;
export function useWorkspaceStore<T>(selector?: (state: WorkspaceState) => T) {
  const snapshot = useSyncExternalStore(subscribe, () => workspaceState, () => workspaceState);
  return selector ? selector(snapshot) : snapshot;
}
