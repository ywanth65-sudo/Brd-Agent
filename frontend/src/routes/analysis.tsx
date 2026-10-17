import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  AlertCircle, ArrowRight, Check, CheckCircle2, CircleHelp, Clock3, FileCheck2,
  FileText, Loader2, Play, Send, ShieldAlert, Sparkles, X, XCircle,
} from "lucide-react";
import { Card } from "@/components/brd/Panels";
import { useApp } from "@/context/AppContext";
import type { AnswerFormat } from "@/types";
import { toast } from "sonner";

export const Route = createFileRoute("/analysis")({
  head: () => ({
    meta: [
      { title: "Requirements Intelligence — BRD Agent" },
      { name: "description", content: "Review requirement quality, resolve ambiguities, and validate assumptions." },
    ],
  }),
  component: Page,
});

const confidenceBand = (confidence: number) => confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";
const canAnalyzeStatus = ["DRAFT", "ANALYZING", "AWAITING_CLARIFICATION", "GENERATED"];

function Workflow({ status, sourceCount, requirementCount, questionCount, ready }: {
  status?: string; sourceCount: number; requirementCount: number; questionCount: number; ready: boolean;
}) {
  const sourceDone = sourceCount > 0;
  const analysisDone = requirementCount > 0;
  const clarificationDone = analysisDone && questionCount === 0;
  const stages = [
    ["Source documents", sourceDone, FileText, "/documents"],
    ["AI analysis", analysisDone, Sparkles, "/analysis"],
    ["Clarification review", clarificationDone, CircleHelp, "/analysis"],
    ["BRD generation", ready, FileCheck2, "/reports"],
  ] as const;
  return <div className="overflow-x-auto rounded-xl border border-border bg-card px-4 py-3">
    <div className="flex min-w-[620px] items-center justify-between gap-2">
      {stages.map(([label, done, Icon, href], index) => <div key={label} className="flex min-w-0 flex-1 items-center gap-2">
        <Link to={href} className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border transition-colors ${done ? "border-primary/30 bg-primary/10 text-primary" : "border-border bg-muted/50 text-muted-foreground"}`} aria-label={`Open ${label}`}>
          <Icon className="h-4 w-4" />
        </Link>
        <span className={`truncate text-[11px] font-medium ${done ? "text-foreground" : "text-muted-foreground"}`}>{label}</span>
        {index < stages.length - 1 && <span className="mx-1 h-px flex-1 bg-border" />}
      </div>)}
    </div>
    <p className="mt-2 text-[10px] text-muted-foreground">Current project status: <span className="font-semibold text-foreground">{status || "Unavailable"}</span></p>
  </div>;
}

function QualityOverview() {
  const { requirements, questions, triggerAnalyze, isAnalyzing, activeProject } = useApp();
  const total = requirements.length;
  const high = requirements.filter((r) => (r.confidence ?? 0) >= 0.8).length;
  const medium = requirements.filter((r) => (r.confidence ?? 0) >= 0.5 && (r.confidence ?? 0) < 0.8).length;
  const low = Math.max(0, total - high - medium);
  const highPct = total ? Math.round(high / total * 100) : 0;
  const mediumPct = total ? Math.round(medium / total * 100) : 0;
  const lowPct = total ? Math.max(0, 100 - highPct - mediumPct) : 0;
  const end = highPct + mediumPct;
  const canAnalyze = Boolean(activeProject && canAnalyzeStatus.includes(activeProject.status));
  return <Card className="p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-[10px] font-bold tracking-[.16em] text-primary">QUALITY OVERVIEW</p><h2 className="mt-2 text-[16px] font-semibold">AI Validation &amp; Quality Audit</h2><p className="mt-1 text-[11.5px] text-muted-foreground">Confidence bands are calculated from the returned requirement records.</p></div>
      <button onClick={() => canAnalyze && void triggerAnalyze()} disabled={!canAnalyze || isAnalyzing} title={!canAnalyze ? "Analysis is not available for this project status" : "Run AI analysis"} className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-[11.5px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50">{isAnalyzing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}{isAnalyzing ? "Analyzing..." : "Run AI Analysis"}</button>
    </div>
    {total === 0 ? <div className="mt-5 rounded-lg border border-dashed border-border bg-muted/20 p-8 text-center"><ShieldAlert className="mx-auto h-7 w-7 text-muted-foreground" /><h3 className="mt-2 text-[13px] font-semibold">Your requirements quality report starts here</h3><p className="mx-auto mt-1 max-w-md text-[11.5px] text-muted-foreground">Run AI analysis to evaluate extracted requirements, inspect available evidence, and identify areas needing clarification.</p></div> :
      <div className="mt-6 grid gap-6 md:grid-cols-[150px_1fr] md:items-center">
        <div className="relative mx-auto grid h-32 w-32 place-items-center rounded-full" style={{ background: `conic-gradient(var(--success) 0 ${highPct}%, var(--warning) ${highPct}% ${end}%, var(--destructive) ${end}% 100%)` }} aria-label={`Confidence distribution: ${highPct}% high, ${mediumPct}% medium, ${lowPct}% low`}><div className="grid h-24 w-24 place-items-center rounded-full bg-card text-center"><strong className="text-[24px]">{highPct}%</strong><span className="text-[10px] text-muted-foreground">high confidence</span></div></div>
        <div className="grid grid-cols-3 gap-2">{[["High confidence", high, highPct, "bg-success"], ["Needs review", medium, mediumPct, "bg-warning"], ["Low / ambiguous", low, lowPct, "bg-destructive"]].map(([label, count, pct, color]) => <div key={String(label)} className="rounded-lg border border-border p-3"><div className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground"><span className={`h-2 w-2 rounded-full ${color}`} />{label}</div><p className="mt-2 text-[18px] font-bold">{count}</p><p className="text-[10px] text-muted-foreground">{pct}% of requirements</p></div>)}</div>
      </div>}
    <div className="mt-5 flex items-center gap-2 border-t border-border pt-3 text-[11px] text-muted-foreground"><CircleHelp className="h-3.5 w-3.5 text-warning" />{questions.length} outstanding clarification gap{questions.length === 1 ? "" : "s"}</div>
  </Card>;
}

function Assumptions() {
  const { assumptions, decideAssumption } = useApp();
  const [saving, setSaving] = useState<string | null>(null);
  const decide = async (id: string, decision: "accepted" | "rejected") => { setSaving(id); try { await decideAssumption(id, decision); } finally { setSaving(null); } };
  return <Card className="p-5">
    <div><p className="text-[10px] font-bold tracking-[.16em] text-primary">DECISION REGISTER</p><h2 className="mt-2 text-[16px] font-semibold">Explicit Assumptions <span className="text-muted-foreground">({assumptions.length})</span></h2><p className="mt-1 text-[11.5px] text-muted-foreground">Review AI-synthesized defaults requiring stakeholder sign-off.</p></div>
    <div className="mt-5 space-y-2.5">{assumptions.length === 0 ? <div className="rounded-lg border border-dashed border-border bg-muted/20 p-8 text-center"><CheckCircle2 className="mx-auto h-7 w-7 text-muted-foreground" /><h3 className="mt-2 text-[13px] font-semibold">No assumptions to review yet</h3><p className="mt-1 text-[11.5px] text-muted-foreground">AI-generated assumptions appear here when project information requires an explicit decision.</p></div> : assumptions.map((a) => { const accepted = a.status === "ACCEPTED"; const rejected = a.status === "REJECTED"; return <div key={a.id} className="rounded-lg border border-border p-3.5 transition-colors hover:border-primary/30"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-[12.5px] font-semibold">{a.statement}</p><p className="mt-1 text-[11px] leading-5 text-muted-foreground">{a.rationale}</p><div className="mt-2 flex flex-wrap gap-1.5"><span className="rounded border border-border bg-muted px-2 py-0.5 text-[9.5px] font-semibold uppercase">Impact: {a.impact}</span><span className={`rounded border px-2 py-0.5 text-[9.5px] font-semibold uppercase ${accepted ? "border-success/20 bg-success/10 text-success" : rejected ? "border-destructive/20 bg-destructive/10 text-destructive" : "border-warning/20 bg-warning/10 text-warning"}`}>{a.status}</span></div></div><div className="flex shrink-0 gap-1.5"><button onClick={() => void decide(a.id, "accepted")} disabled={saving === a.id || accepted} aria-label="Accept assumption" className="rounded border border-success/30 p-1.5 text-success hover:bg-success/10 disabled:opacity-50"><Check className="h-4 w-4" /></button><button onClick={() => void decide(a.id, "rejected")} disabled={saving === a.id || rejected} aria-label="Reject assumption" className="rounded border border-destructive/30 p-1.5 text-destructive hover:bg-destructive/10 disabled:opacity-50"><X className="h-4 w-4" /></button></div></div></div>; })}</div>
  </Card>;
}

function AnswerControl({ format, value, options, onChange }: { format: AnswerFormat; value: string; options?: string[] | null; onChange: (value: string) => void }) {
  if (format === "CHOICE" && options?.length) return <select value={value} onChange={(e) => onChange(e.target.value)} className="min-w-0 flex-1 rounded-md border border-input bg-background px-3 py-2 text-[12px] focus:outline-none focus:ring-2 focus:ring-primary/20"><option value="">Select an answer...</option>{options.map((option) => <option key={option} value={option}>{option}</option>)}</select>;
  if (format === "YES_NO") return <select value={value} onChange={(e) => onChange(e.target.value)} className="min-w-0 flex-1 rounded-md border border-input bg-background px-3 py-2 text-[12px] focus:outline-none focus:ring-2 focus:ring-primary/20"><option value="">Select an answer...</option><option value="yes">Yes</option><option value="no">No</option></select>;
  return <input type={format === "DATE" ? "date" : format === "NUMBER" ? "number" : "text"} value={value} onChange={(e) => onChange(e.target.value)} placeholder={`Enter ${format.toLowerCase()} answer...`} className="min-w-0 flex-1 rounded-md border border-input bg-background px-3 py-2 text-[12px] focus:outline-none focus:ring-2 focus:ring-primary/20" />;
}

function Questions() {
  const { questions, submitQuestionAnswers, activeProject } = useApp();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState<string | null>(null);
  const submit = async (id: string) => { const value = answers[id]?.trim(); if (!value) { toast.error("Please provide an answer first."); return; } setSubmitting(id); try { await submitQuestionAnswers([{ question_id: id, value }]); setAnswers((current) => ({ ...current, [id]: "" })); } finally { setSubmitting(null); } };
  return <Card className="p-5"><div><p className="text-[10px] font-bold tracking-[.16em] text-primary">STAKEHOLDER REVIEW</p><h2 className="mt-2 text-[16px] font-semibold">Clarification Questions <span className="text-muted-foreground">({questions.length})</span></h2><p className="mt-1 text-[11.5px] text-muted-foreground">Resolve incomplete or ambiguous requirements before generating the BRD.</p></div>{questions.length === 0 ? <div className="mt-5 rounded-lg border border-dashed border-border bg-muted/20 p-8 text-center"><CheckCircle2 className="mx-auto h-7 w-7 text-success" /><h3 className="mt-2 text-[13px] font-semibold">{activeProject?.status === "READY_TO_GENERATE" ? "No open clarification gaps" : "No questions generated yet"}</h3><p className="mt-1 text-[11.5px] text-muted-foreground">{activeProject?.status === "READY_TO_GENERATE" ? "All currently identified gaps are resolved. The project can move to BRD generation." : "Run AI analysis to identify decisions that need stakeholder input."}</p></div> : <div className="mt-5 grid gap-3 md:grid-cols-2">{questions.map((q) => <div key={q.id} className="rounded-lg border border-border p-4"><div className="flex items-start justify-between gap-2"><div><span className="font-mono text-[10px] text-primary">{q.id}</span><p className="mt-1 text-[12.5px] font-semibold">{q.question_text}</p></div><span className="shrink-0 rounded border border-warning/20 bg-warning/10 px-2 py-0.5 text-[9.5px] font-semibold text-warning">Priority {q.priority}</span></div><p className="mt-2 text-[11px] italic leading-5 text-muted-foreground">{q.why_it_matters}</p><div className="mt-4 flex gap-2"><AnswerControl format={q.answer_format} value={answers[q.id] || ""} options={q.options} onChange={(value) => setAnswers((current) => ({ ...current, [q.id]: value }))} /><button onClick={() => void submit(q.id)} disabled={submitting === q.id || !answers[q.id]?.trim()} className="flex items-center gap-1 rounded-md bg-primary px-3 py-2 text-[11px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50">{submitting === q.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}<span className="sr-only">Submit answer</span></button></div></div>)}</div>}</Card>;
}

function Page() {
  const { activeProject, sources, requirements, questions, assumptions, generateBRD, isGeneratingBRD } = useApp();
  const canGenerate = activeProject?.status === "READY_TO_GENERATE";
  return <div className="space-y-4">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><div className="mb-2 text-[11px] text-muted-foreground">Projects <span className="mx-1">/</span> {activeProject?.title || "Project"} <span className="mx-1">/</span> BRD Analysis</div><p className="text-[10px] font-bold tracking-[.16em] text-primary">REQUIREMENTS INTELLIGENCE</p><h1 className="mt-2 text-[22px] font-bold tracking-tight">Requirements Intelligence</h1><p className="mt-1 max-w-2xl text-[12.5px] text-muted-foreground">Review requirement quality, resolve ambiguities, and validate assumptions before generating your Business Requirements Document.</p>{activeProject && <p className="mt-2 text-[12px] font-medium text-primary">{activeProject.title} <span className="ml-2 rounded border border-border bg-muted px-2 py-0.5 text-[9.5px] uppercase text-muted-foreground">{activeProject.status}</span></p>}</div><div className="flex items-center gap-2"><button onClick={() => canGenerate && void generateBRD()} disabled={!canGenerate || isGeneratingBRD} title={!canGenerate ? "Generation is available only when the project is READY_TO_GENERATE" : "Generate formal BRD"} className="flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-[12px] font-semibold text-white hover:bg-emerald-500 disabled:opacity-50">{isGeneratingBRD ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}{isGeneratingBRD ? "Generating..." : "Generate Formal BRD"}</button></div></div>
    <Workflow status={activeProject?.status} sourceCount={sources.length} requirementCount={requirements.length} questionCount={questions.length} ready={canGenerate} />
    <QualityOverview />
    <div className="grid gap-4 xl:grid-cols-[1.15fr_.85fr]"><Questions /><Assumptions /></div>
    {activeProject && !canGenerate && activeProject.status !== "READY_TO_GENERATE" && <div className="flex items-center gap-2 rounded-lg border border-warning/20 bg-warning/5 px-4 py-3 text-[11px] text-warning"><AlertCircle className="h-4 w-4 shrink-0" />BRD generation becomes available when the backend marks this project READY_TO_GENERATE.</div>}
  </div>;
}
