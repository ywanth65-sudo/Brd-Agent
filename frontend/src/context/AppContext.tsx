import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import type { User, Session } from '@supabase/supabase-js';
import { supabase } from '@/api/supabase';
import * as api from '@/api/projects';
import type {
  Project,
  ProjectDetailResponse,
  Requirement,
  Question,
  Assumption,
  SourceDocument,
  BRDVersion,
} from '@/types';
import { toast } from 'sonner';

interface AppContextType {
  // Auth
  user: User | null;
  session: Session | null;
  isAuthenticated: boolean;
  isAuthLoading: boolean;
  showAuthModal: boolean;
  setShowAuthModal: (open: boolean) => void;
  signOut: () => Promise<void>;

  // Projects
  projects: Project[];
  activeProjectId: string | null;
  activeProject: Project | null;
  activeProjectDetail: ProjectDetailResponse | null;
  requirements: Requirement[];
  questions: Question[];
  assumptions: Assumption[];
  sources: SourceDocument[];
  brdVersion: BRDVersion | null;
  isProjectLoading: boolean;
  isAnalyzing: boolean;
  isGeneratingBRD: boolean;

  // Actions
  setActiveProjectId: (id: string) => void;
  refreshProjects: () => Promise<void>;
  refreshActiveProject: () => Promise<void>;
  createProject: (title: string | undefined, idea: string) => Promise<Project>;
  uploadSource: (file: File) => Promise<SourceDocument>;
  triggerAnalyze: () => Promise<void>;
  submitQuestionAnswers: (answers: { question_id: string; value: string }[]) => Promise<void>;
  decideAssumption: (assumptionId: string, decision: 'accepted' | 'rejected') => Promise<void>;
  generateBRD: () => Promise<void>;
  downloadDocx: () => Promise<void>;
}

const AppContext = createContext<AppContextType | null>(null);

const STORAGE_ACTIVE_PROJECT_KEY = 'brd_agent_active_project_id';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // ─── Auth State ───────────────────────────────────────────────────────────
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [showAuthModal, setShowAuthModal] = useState(false);

  // ─── Project State ────────────────────────────────────────────────────────
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectIdState] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_ACTIVE_PROJECT_KEY) || null;
  });
  const [activeProjectDetail, setActiveProjectDetail] = useState<ProjectDetailResponse | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [assumptions, setAssumptions] = useState<Assumption[]>([]);
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [brdVersion, setBrdVersion] = useState<BRDVersion | null>(null);
  const [isProjectLoading, setIsProjectLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isGeneratingBRD, setIsGeneratingBRD] = useState(false);

  const isAuthenticated = DEMO_MODE || !!user;

  // Active project entity lookup
  const activeProject = useMemo(() => {
    if (!activeProjectId) return null;
    return projects.find((p) => p.id === activeProjectId) || activeProjectDetail?.project || null;
  }, [activeProjectId, projects, activeProjectDetail]);

  const setActiveProjectId = useCallback((id: string) => {
    setActiveProjectIdState(id);
    localStorage.setItem(STORAGE_ACTIVE_PROJECT_KEY, id);
  }, []);

  // ─── Supabase Auth Listener ───────────────────────────────────────────────
  useEffect(() => {
    if (DEMO_MODE) {
      setIsAuthLoading(false);
      setShowAuthModal(false);
      return;
    }

    let mounted = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      setUser(data.session?.user ?? null);
      setIsAuthLoading(false);
      if (!data.session?.user) {
        setShowAuthModal(true);
      }
    });

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
      setUser(newSession?.user ?? null);
      setIsAuthLoading(false);
      if (newSession?.user) {
        setShowAuthModal(false);
      } else {
        setShowAuthModal(true);
      }
    });

    return () => {
      mounted = false;
      authListener.subscription.unsubscribe();
    };
  }, []);

  const signOut = useCallback(async () => {
    if (DEMO_MODE) {
      toast.info('Authentication is disabled in demo mode');
      return;
    }

    try {
      await supabase.auth.signOut();
      setUser(null);
      setSession(null);
      setShowAuthModal(true);
      toast.success('Signed out successfully');
    } catch (err: any) {
      toast.error(err.message || 'Error signing out');
    }
  }, []);

  // ─── Load Project Collection ──────────────────────────────────────────────
  const refreshProjects = useCallback(async () => {
    try {
      const list = await api.getProjects(50);
      setProjects(list);
      // Auto-select first project if none selected or current invalid
      if (list.length > 0) {
        const stored = localStorage.getItem(STORAGE_ACTIVE_PROJECT_KEY);
        const exists = list.some((p) => p.id === stored);
        if (exists && stored) {
          setActiveProjectIdState(stored);
        } else {
          setActiveProjectId(list[0].id);
        }
      } else {
        setActiveProjectIdState(null);
        localStorage.removeItem(STORAGE_ACTIVE_PROJECT_KEY);
      }
    } catch (err: any) {
      console.warn('Failed to load project list:', err.message);
    }
  }, [setActiveProjectId]);

  // Load project list once auth is established
  useEffect(() => {
    if (!isAuthLoading) {
      refreshProjects();
    }
  }, [isAuthLoading, refreshProjects]);

  // ─── Load Single Active Project Data ──────────────────────────────────────
  const refreshActiveProject = useCallback(async () => {
    if (!activeProjectId) {
      setActiveProjectDetail(null);
      setRequirements([]);
      setQuestions([]);
      setAssumptions([]);
      setSources([]);
      setBrdVersion(null);
      return;
    }

    setIsProjectLoading(true);
    try {
      const [detail, reqs, qs, asms, srcs] = await Promise.all([
        api.getProjectDetail(activeProjectId).catch(() => null),
        api.getRequirements(activeProjectId).catch(() => []),
        api.getQuestions(activeProjectId).catch(() => []),
        api.getAssumptions(activeProjectId).catch(() => []),
        api.getSourceFiles(activeProjectId).catch(() => []),
      ]);

      if (detail) setActiveProjectDetail(detail);
      setRequirements(reqs);
      setQuestions(qs);
      setAssumptions(asms);
      setSources(srcs);

      // Check if BRD is generated
      if (detail?.project.status === 'GENERATED' || detail?.project.status === 'COMPLETED') {
        api.getBRD(activeProjectId)
          .then((brd) => setBrdVersion(brd))
          .catch(() => setBrdVersion(null));
      } else {
        setBrdVersion(null);
      }
    } catch (err: any) {
      console.warn('Error fetching active project:', err);
    } finally {
      setIsProjectLoading(false);
    }
  }, [activeProjectId]);

  useEffect(() => {
    refreshActiveProject();
  }, [refreshActiveProject]);

  // ─── Project Mutations ────────────────────────────────────────────────────
  const createProject = useCallback(
    async (title: string | undefined, idea: string): Promise<Project> => {
      const res = await api.createProject(title, idea);
      toast.success(`Project "${res.project.title}" created!`);
      await refreshProjects();
      setActiveProjectId(res.project.id);
      return res.project;
    },
    [refreshProjects, setActiveProjectId]
  );

  const uploadSource = useCallback(
    async (file: File): Promise<SourceDocument> => {
      if (!activeProjectId) throw new Error('No active project selected');
      toast.info(`Uploading ${file.name}...`);
      const doc = await api.uploadSourceFile(activeProjectId, file);
      toast.success(`${file.name} uploaded and parsed!`);
      setSources((prev) => [doc, ...prev]);
      await refreshActiveProject();
      return doc;
    },
    [activeProjectId, refreshActiveProject]
  );

  const triggerAnalyze = useCallback(async () => {
    if (!activeProjectId) return;
    if (activeProject && !['DRAFT', 'ANALYZING', 'AWAITING_CLARIFICATION', 'GENERATED'].includes(activeProject.status)) {
      toast.info(`Analysis is unavailable while this project is ${activeProject.status.replaceAll('_', ' ')}.`);
      return;
    }
    setIsAnalyzing(true);
    toast.info('Running AI analysis & verification loop...');
    try {
      const res = await api.analyzeProject(activeProjectId);
      setRequirements(res.requirements);
      setQuestions(res.open_questions);
      setAssumptions(res.assumptions);
      toast.success('AI Analysis completed successfully!');
      await refreshActiveProject();
      await refreshProjects();
    } catch (err: any) {
      toast.error(err.message || 'Analysis failed');
    } finally {
      setIsAnalyzing(false);
    }
  }, [activeProject, activeProjectId, refreshActiveProject, refreshProjects]);

  const submitQuestionAnswers = useCallback(
    async (answers: { question_id: string; value: string }[]) => {
      if (!activeProjectId) return;
      toast.info('Submitting clarification answers...');
      try {
        const res = await api.submitAnswers(activeProjectId, answers);
        setRequirements(res.requirements);
        setQuestions(res.open_questions);
        setAssumptions(res.assumptions);
        toast.success('Answers processed and requirements updated!');
        await refreshActiveProject();
      } catch (err: any) {
        toast.error(err.message || 'Failed to submit answers');
      }
    },
    [activeProjectId, refreshActiveProject]
  );

  const decideAssumption = useCallback(
    async (assumptionId: string, decision: 'accepted' | 'rejected') => {
      if (!activeProjectId) return;
      try {
        await api.decideAssumption(activeProjectId, assumptionId, decision);
        toast.success(`Assumption marked as ${decision}`);
        setAssumptions((prev) =>
          prev.map((a) => (a.id === assumptionId ? { ...a, status: decision.toUpperCase() as any } : a))
        );
      } catch (err: any) {
        toast.error(err.message || 'Failed to update assumption');
      }
    },
    [activeProjectId]
  );

  const generateBRD = useCallback(async () => {
    if (!activeProjectId) return;
    setIsGeneratingBRD(true);
    toast.info('Generating formal BRD document...');
    try {
      const res = await api.generateBRD(activeProjectId);
      setBrdVersion(res.brd_version);
      toast.success('BRD generated successfully! Ready for export.');
      await refreshActiveProject();
    } catch (err: any) {
      toast.error(err.message || 'BRD generation failed');
    } finally {
      setIsGeneratingBRD(false);
    }
  }, [activeProjectId, refreshActiveProject]);

  const downloadDocx = useCallback(async () => {
    if (!activeProjectId) return;
    if (!brdVersion) {
      toast.info('Generate the BRD before downloading a Word document.');
      return;
    }
    toast.info('Preparing BRD document download...');
    try {
      const filename = activeProject
        ? `BRD_${activeProject.title.replace(/\s+/g, '_')}_v1.docx`
        : `BRD_${activeProjectId}.docx`;
      await api.downloadBRDDocx(activeProjectId, filename);
      toast.success('Download started!');
    } catch (err: any) {
      toast.error(err.message || 'Failed to download document');
    }
  }, [activeProjectId, activeProject, brdVersion]);

  return (
    <AppContext.Provider
      value={{
        user,
        session,
        isAuthenticated,
        isAuthLoading,
        showAuthModal,
        setShowAuthModal,
        signOut,
        projects,
        activeProjectId,
        activeProject,
        activeProjectDetail,
        requirements,
        questions,
        assumptions,
        sources,
        brdVersion,
        isProjectLoading,
        isAnalyzing,
        isGeneratingBRD,
        setActiveProjectId,
        refreshProjects,
        refreshActiveProject,
        createProject,
        uploadSource,
        triggerAnalyze,
        submitQuestionAnswers,
        decideAssumption,
        generateBRD,
        downloadDocx,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
