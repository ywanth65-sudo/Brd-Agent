import { useState, type ReactNode } from "react";
import {
  FileText, Database, ListChecks, BadgeCheck, Download, Upload, ZoomIn, ZoomOut, ChevronLeft, ChevronRight,
  Maximize, CheckCircle2, Loader2, Play, ShieldCheck, Scale, Gauge, AlertCircle, Plus, FileSpreadsheet,
  HelpCircle, Sparkles, ClipboardList
} from "lucide-react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { useApp } from "@/context/AppContext";
import type { Requirement, RequirementPriority, RequirementType } from "@/types";

export const Card = ({ children, className = "" }: { children: ReactNode; className?: string }) => (
  <div className={`rounded-lg border border-border bg-card shadow-[0_1px_2px_0_rgb(0_0_0/0.04)] ${className}`}>{children}</div>
);

export function ValidationBadge({ priority, type }: { priority?: RequirementPriority | string; type?: string }) {
  const p = priority || "SHOULD";
  let c = "bg-primary/10 text-primary border-primary/20";
  if (p === "MUST") c = "bg-destructive/10 text-destructive border-destructive/20";
  else if (p === "SHOULD") c = "bg-warning/10 text-warning border-warning/20";
  else if (p === "COULD") c = "bg-success/10 text-success border-success/20";
  else if (p === "WONT") c = "bg-muted text-muted-foreground border-border";

  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[10.5px] font-semibold tracking-wide uppercase ${c}`}>
      {p}
    </span>
  );
}

function DocThumb({ small, count = 0 }: { small?: boolean; count?: number }) {
  return (
    <div className={`flex h-full w-full flex-col justify-between bg-card ${small ? "p-1.5" : "p-3"}`}>
      <div className="flex flex-col gap-1">
        <div className="h-1.5 w-2/3 rounded-sm bg-primary/70" />
        <div className="h-1 w-1/2 rounded-sm bg-foreground/30" />
        {Array.from({ length: small ? 4 : 8 }).map((_, i) => (
          <div key={i} className="h-1 rounded-sm bg-muted-foreground/20" style={{ width: `${60 + ((i * 19) % 38)}%` }} />
        ))}
      </div>
      <div className="text-[9.5px] font-mono text-muted-foreground/70">
        {count > 0 ? `${count} files` : "No docs"}
      </div>
    </div>
  );
}

export function ProjectHeader() {
  const { activeProject, activeProjectDetail, requirements, questions, assumptions, sources } = useApp();

  if (!activeProject) {
    return (
      <Card className="flex flex-col items-center justify-center p-8 text-center">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary mb-3">
          <Sparkles className="h-6 w-6" />
        </div>
        <h2 className="text-[16px] font-semibold text-foreground">No Active Project Selected</h2>
        <p className="text-[12.5px] text-muted-foreground mt-1 max-w-sm">
          Select a project from the top bar or create a new project to start analyzing requirements.
        </p>
      </Card>
    );
  }

  const createdDate = activeProject.created_at
    ? new Date(activeProject.created_at).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Recently";

  return (
    <Card className="flex flex-col gap-4 p-4 sm:flex-row">
      <div className="h-[150px] w-full shrink-0 overflow-hidden rounded border border-border bg-muted p-2 sm:w-[112px]">
        <DocThumb count={sources.length} />
      </div>
      <div className="min-w-0 flex-1 py-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[16px] font-semibold text-foreground truncate">{activeProject.title}</h1>
          <span className="rounded bg-primary/10 border border-primary/20 px-2 py-0.5 text-[10.5px] font-semibold text-primary uppercase">
            {activeProject.status}
          </span>
        </div>
        <p className="text-[12px] text-muted-foreground mt-1 line-clamp-2">
          {activeProject.idea}
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-4">
          <div>
            <dt className="text-[10.5px] text-muted-foreground">Project ID</dt>
            <dd className="text-[12px] font-mono font-medium text-foreground">{activeProject.id.slice(0, 8)}...</dd>
          </div>
          <div>
            <dt className="text-[10.5px] text-muted-foreground">Created</dt>
            <dd className="text-[12px] font-medium text-foreground">{createdDate}</dd>
          </div>
          <div>
            <dt className="text-[10.5px] text-muted-foreground">Requirements</dt>
            <dd className="text-[12px] font-medium text-foreground">{activeProjectDetail?.requirement_count ?? requirements.length}</dd>
          </div>
          <div>
            <dt className="text-[10.5px] text-muted-foreground">Open Gaps</dt>
            <dd className="text-[12px] font-medium text-foreground">{activeProjectDetail?.open_question_count ?? questions.length}</dd>
          </div>
        </dl>
      </div>
    </Card>
  );
}

export function KPIs() {
  const { activeProjectDetail, requirements, questions, assumptions, sources } = useApp();

  const reqCount = activeProjectDetail?.requirement_count ?? requirements.length;
  const questionCount = activeProjectDetail?.open_question_count ?? questions.length;
  const assumptionCount = activeProjectDetail?.assumption_count ?? assumptions.length;
  const sourceCount = sources.length;

  const proposedAssumptions = assumptions.filter((a) => a.status === "PROPOSED").length;
  const readySources = sources.filter((s) => ["ready", "parsed", "completed"].includes(s.status.toLowerCase())).length;
  const kpis = [
    [FileText, "text-primary", String(reqCount), "Requirements", reqCount ? `${requirements.filter((r) => r.type === "functional").length} functional` : "Awaiting analysis"],
    [Database, "text-success", String(sourceCount), "Grounding Sources", sourceCount ? `${readySources} processed` : "No documents uploaded"],
    [ListChecks, "text-warning", String(questionCount), "Clarification Gaps", questionCount ? "Stakeholder input needed" : "No open gaps"],
    [BadgeCheck, "text-violet", String(assumptionCount), "Explicit Assumptions", assumptionCount ? `${proposedAssumptions} proposed` : "None identified"],
  ] as const;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {kpis.map(([I, c, n, l, s]) => (
        <Card key={l} className="p-4">
          <I className={`h-6 w-6 ${c}`} />
          <div className="mt-3 text-[22px] font-bold leading-none text-foreground">{n}</div>
          <div className="mt-1.5 text-[12.5px] font-medium text-foreground">{l}</div>
          <div className="mt-2 text-[10.5px] text-muted-foreground">{s}</div>
        </Card>
      ))}
    </div>
  );
}

export function exportCsv(requirements?: Requirement[], projectTitle?: string) {
  if (!requirements || requirements.length === 0) {
    toast.error("No requirements available to export");
    return;
  }
  const head = "ID,Type,Title,Priority,Confidence,Statement,Acceptance Criteria";
  const rows = requirements.map((r) => [
    r.id,
    r.type,
    `"${(r.title || '').replace(/"/g, '""')}"`,
    r.priority,
    r.confidence,
    `"${(r.statement || '').replace(/"/g, '""')}"`,
    `"${(r.acceptance_criteria || []).join('; ').replace(/"/g, '""')}"`,
  ].join(","));

  const content = [head, ...rows].join("\n");
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${projectTitle ? projectTitle.replace(/\s+/g, '_') : 'project'}_requirements.csv`;
  a.click();
  URL.revokeObjectURL(url);
  toast.success("Requirements exported to CSV");
}

export function Actions() {
  const { activeProject, brdVersion, downloadDocx, triggerAnalyze, isAnalyzing, requirements, isGeneratingBRD } = useApp();
  const canAnalyze = Boolean(activeProject && ["DRAFT", "ANALYZING", "AWAITING_CLARIFICATION", "GENERATED"].includes(activeProject.status));

  const handleExportCsv = () => {
    exportCsv(requirements, activeProject?.title);
  };

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <button
        onClick={() => {
          if (canAnalyze) void triggerAnalyze();
        }}
        disabled={isAnalyzing || !canAnalyze}
        title={activeProject && !canAnalyze
          ? `Analysis is not available while this project is ${activeProject.status.replaceAll("_", " ")}.`
          : "Run AI analysis"}
        className="flex items-center gap-2 rounded-md bg-primary px-3.5 py-2 text-[12.5px] font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        {isAnalyzing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
        {isAnalyzing ? "Analyzing..." : "Run AI Analysis"}
      </button>
      {activeProject && !canAnalyze && (
        <span className="text-[10.5px] text-muted-foreground">
          Analysis unavailable for {activeProject.status.replaceAll("_", " ")} projects
        </span>
      )}

      <button
        onClick={handleExportCsv}
        disabled={!activeProject || requirements.length === 0}
        className="flex items-center gap-2 rounded-md border border-border bg-card px-3.5 py-2 text-[12.5px] font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
      >
        <FileSpreadsheet className="h-3.5 w-3.5 text-muted-foreground" />
        Export CSV
      </button>

      <button
        onClick={downloadDocx}
        disabled={!activeProject || !brdVersion || isGeneratingBRD}
        title={!brdVersion ? "Generate the BRD before downloading a Word document" : "Download the generated BRD"}
        className="flex items-center gap-2 rounded-md border border-border bg-card px-3.5 py-2 text-[12.5px] font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
      >
        {isGeneratingBRD ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5 text-muted-foreground" />}
        {isGeneratingBRD ? "Preparing..." : "Download Word"}
      </button>
    </div>
  );
}

export function DocumentViewer() {
  const { sources, uploadSource, activeProject, isProjectLoading } = useApp();
  const [uploading, setUploading] = useState(false);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadSource(file);
    } catch {
      // toast handled in context
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  return (
    <Card className="flex flex-col p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-[13.5px] font-semibold text-foreground">Grounding Source Documents</h2>
          <p className="text-[11.5px] text-muted-foreground">Upload PDFs, Word docs, notes, or whiteboard photos</p>
        </div>
        <label className={`flex items-center gap-1.5 rounded-md bg-primary/10 border border-primary/30 px-3 py-1.5 text-[11.5px] font-medium text-primary hover:bg-primary/20 transition-colors cursor-pointer ${uploading || !activeProject ? 'opacity-50 pointer-events-none' : ''}`}>
          {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
          <span>Upload File</span>
          <input
            type="file"
            accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.webp"
            className="hidden"
            onChange={handleFileUpload}
            disabled={uploading || !activeProject}
          />
        </label>
      </div>

      <div className="flex-1 overflow-y-auto min-h-[220px] max-h-[300px]">
        {isProjectLoading ? (
          <div className="flex h-full min-h-[180px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/20 text-[12px] text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            Loading source documents...
          </div>
        ) : sources.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center p-8 text-center border-2 border-dashed border-border rounded-lg">
            <FileText className="h-8 w-8 text-muted-foreground/50 mb-2" />
            <div className="text-[13px] font-medium text-foreground">No source documents uploaded yet</div>
            <div className="text-[11.5px] text-muted-foreground mt-1 max-w-xs">
              Upload customer briefs, PRDs, or architecture notes to ground requirement synthesis.
            </div>
          </div>
        ) : (
          <div className="divide-y divide-border/60">
            {sources.map((s) => (
              <div key={s.id} className="flex items-center justify-between py-2.5 px-2 hover:bg-muted/50 rounded transition-colors">
                <div className="flex items-center gap-2.5 min-w-0">
                  <FileText className="h-4 w-4 text-primary shrink-0" />
                  <div className="truncate">
                    <div className="text-[12.5px] font-medium text-foreground truncate">{s.filename}</div>
                    <div className="text-[10.5px] text-muted-foreground">
                      {s.file_type.toUpperCase()} • {s.chunk_count} grounded chunks • {s.status}
                      {s.created_at ? ` • ${new Date(s.created_at).toLocaleDateString()}` : ""}
                    </div>
                  </div>
                </div>
                <span className={`shrink-0 text-[10px] rounded px-2 py-0.5 font-semibold uppercase ${
                  ["ready", "parsed", "completed"].includes(s.status.toLowerCase())
                    ? "bg-success/10 text-success border border-success/20"
                    : ["failed", "error"].includes(s.status.toLowerCase())
                    ? "bg-destructive/10 text-destructive border border-destructive/20"
                    : "bg-warning/10 text-warning border border-warning/20"
                }`}>
                  {s.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

const typeIcon = (t: string) => {
  const m: Record<string, [any, string]> = {
    functional: [FileText, "text-primary"],
    nonfunctional: [Gauge, "text-violet"],
    business: [Scale, "text-warning"],
    constraint: [ShieldCheck, "text-destructive"],
  };
  return m[t] ?? [FileText, "text-primary"];
};

export function RequirementsTable({ full = false }: { full?: boolean }) {
  const { requirements, isProjectLoading } = useApp();
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState<string>("All");
  const [selectedReq, setSelectedReq] = useState<any>(null);

  const per = full ? 12 : 6;
  const list = typeFilter === "All" ? requirements : requirements.filter((r) => r.type.toLowerCase() === typeFilter.toLowerCase());
  const pages = Math.max(1, Math.ceil(list.length / per));
  const rows = list.slice((page - 1) * per, page * per);

  return (
    <Card className="flex flex-col p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-[13.5px] font-semibold text-foreground">Extracted Requirements ({requirements.length})</h2>
          <p className="text-[11.5px] text-muted-foreground">Synthesized and prioritized via MoSCoW methodology</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={typeFilter}
            onChange={(e) => {
              setTypeFilter(e.target.value);
              setPage(1);
            }}
            className="rounded border border-border bg-card px-2 py-1 text-[11.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="All">All Types</option>
            <option value="functional">Functional</option>
            <option value="nonfunctional">Non-Functional</option>
            <option value="business">Business Rule</option>
            <option value="constraint">Constraint</option>
          </select>
          {!full && (
            <Link to="/requirements" className="text-[11.5px] font-medium text-primary hover:underline">
              View All
            </Link>
          )}
        </div>
      </div>

      <div className="mt-3 flex-1 overflow-x-auto min-h-[220px]">
        <table className="w-full min-w-[620px] text-left text-[11.5px]">
          <thead className="text-[10.5px] text-muted-foreground border-b border-border">
            <tr>
              <th className="pb-2 font-semibold">ID</th>
              <th className="w-[30%] pb-2 font-semibold">Title</th>
              <th className="pb-2 font-semibold">Type</th>
              <th className="pb-2 font-semibold">Priority</th>
              <th className="pb-2 font-semibold">Confidence</th>
              <th className="pb-2 font-semibold">Traceability</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {isProjectLoading ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-muted-foreground">
                  <span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin text-primary" /> Loading requirements...</span>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-muted-foreground">
                  No requirements extracted yet. Click "Run AI Analysis" or upload documents.
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const [IconComponent, colorClass] = typeIcon(r.type);
                const isSelected = selectedReq?.id === r.id;
                return (
                  <tr
                    key={r.id}
                    onClick={() => {
                      setSelectedReq(r);
                      toast(`${r.id}: ${r.title || r.statement}`, {
                        description: `Actor: ${r.actor || 'N/A'} • Outcome: ${r.outcome || 'N/A'}`,
                      });
                    }}
                    className={`cursor-pointer transition-colors hover:bg-muted/60 ${isSelected ? 'bg-accent/40' : ''}`}
                  >
                    <td className="py-2.5">
                      <span className="flex items-center gap-1.5 font-mono font-medium text-foreground">
                        <IconComponent className={`h-3.5 w-3.5 ${colorClass}`} />
                        {r.id}
                      </span>
                    </td>
                    <td className="max-w-[240px]">
                      <div className="truncate font-medium text-foreground" title={r.title || r.statement}>
                        {r.title || r.statement}
                      </div>
                    </td>
                    <td className="capitalize text-muted-foreground">{r.type}</td>
                    <td>
                      <ValidationBadge priority={r.priority} />
                    </td>
                    <td>
                      <span className="font-mono text-muted-foreground">
                        {Math.round((r.confidence ?? 1) * 100)}%
                      </span>
                    </td>
                    <td className="text-muted-foreground text-[10.5px]">
                      {r.trace_refs && r.trace_refs.length > 0 ? r.trace_refs.join(', ') : 'Grounded'}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground pt-2 border-t border-border">
        <span>
          Showing {list.length ? (page - 1) * per + 1 : 0} to {Math.min(page * per, list.length)} of {list.length} requirements
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="grid h-7 w-7 place-items-center rounded border border-border hover:bg-muted disabled:opacity-40"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          {Array.from({ length: Math.min(5, pages) }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              onClick={() => setPage(p)}
              className={`h-7 w-7 rounded text-[11px] font-medium transition-colors ${
                p === page ? "bg-primary text-primary-foreground" : "border border-border hover:bg-muted"
              }`}
            >
              {p}
            </button>
          ))}
          <button
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page >= pages}
            className="grid h-7 w-7 place-items-center rounded border border-border hover:bg-muted disabled:opacity-40"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </Card>
  );
}

export function ValidationSummary() {
  const { requirements, questions, assumptions, triggerAnalyze, isAnalyzing } = useApp();

  const total = requirements.length;
  const highConfidence = requirements.filter((r) => (r.confidence ?? 0) >= 0.8).length;
  const medConfidence = requirements.filter((r) => (r.confidence ?? 0) >= 0.5 && (r.confidence ?? 0) < 0.8).length;
  const lowConfidence = requirements.filter((r) => (r.confidence ?? 0) < 0.5).length;

  const highPct = total > 0 ? Math.round((highConfidence / total) * 100) : 0;
  const mediumPct = total > 0 ? Math.round((medConfidence / total) * 100) : 0;
  const lowPct = total > 0 ? Math.max(0, 100 - highPct - mediumPct) : 0;
  const mediumEnd = highPct + mediumPct;

  return (
    <Card className="flex flex-col p-4">
      <h2 className="text-[13.5px] font-semibold text-foreground">AI Validation &amp; Quality Audit</h2>
      <div className="mt-3 flex flex-1 items-center gap-6">
        <div
          className="relative grid h-28 w-28 place-items-center rounded-full bg-muted/30"
          style={{
            background: total
              ? `conic-gradient(var(--success) 0 ${highPct}%, var(--warning) ${highPct}% ${mediumEnd}%, var(--destructive) ${mediumEnd}% 100%)`
              : "var(--border)",
          }}
          aria-label={total
            ? `Confidence distribution: ${highPct}% high, ${mediumPct}% medium, ${lowPct}% low`
            : "Confidence distribution unavailable until requirements are analyzed"}
        >
          <div className="grid h-20 w-20 place-items-center rounded-full bg-card">
          <div className="text-center">
            <div className="text-[22px] font-bold text-foreground leading-none">{total ? `${highPct}%` : "—"}</div>
            <div className="mt-1 text-[10.5px] text-muted-foreground">High Conf.</div>
          </div>
          </div>
        </div>
        <ul className="flex-1 space-y-2 text-[11.5px]">
          <li className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-success" />High Confidence
            </span>
            <span className="font-semibold text-foreground">{highConfidence} <span className="font-normal text-muted-foreground">({highPct}%)</span></span>
          </li>
          <li className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-warning" />Medium Review
            </span>
            <span className="font-semibold text-foreground">{medConfidence} <span className="font-normal text-muted-foreground">({mediumPct}%)</span></span>
          </li>
          <li className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-destructive" />Low / Ambiguous
            </span>
            <span className="font-semibold text-foreground">{lowConfidence} <span className="font-normal text-muted-foreground">({lowPct}%)</span></span>
          </li>
          <li className="flex items-center justify-between pt-1 border-t border-border">
            <span className="text-muted-foreground">Clarification Gaps</span>
            <span className="font-semibold text-primary">{questions.length}</span>
          </li>
        </ul>
      </div>

      <div className="mt-4 flex items-center justify-between pt-2 border-t border-border">
        <span className="text-[10.5px] text-muted-foreground">
          {total > 0 ? `${total} verified requirements` : 'Awaiting analysis'}
        </span>
        <button
          onClick={triggerAnalyze}
          disabled={isAnalyzing}
          className="flex items-center gap-1.5 rounded-md border border-primary/40 px-3 py-1.5 text-[11.5px] font-medium text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
        >
          {isAnalyzing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          {isAnalyzing ? "Validating..." : "Run AI Validation"}
        </button>
      </div>
    </Card>
  );
}

export function KeyFindings() {
  const { requirements, sources, questions, assumptions, activeProject } = useApp();

  const findings = [
    `${requirements.length} requirements extracted and verified`,
    `${sources.length} grounding source files indexed`,
    `${questions.length} clarification gaps identified for stakeholder review`,
    `${assumptions.length} explicit assumptions mapped`,
    activeProject?.status === 'READY_TO_GENERATE' || activeProject?.status === 'COMPLETED'
      ? "Deterministic validation gates satisfied"
      : "Pending stakeholder input or document ingestion",
  ];

  return (
    <Card className="flex flex-col p-4">
      <h2 className="text-[13.5px] font-semibold text-foreground">Project Summary</h2>
      <ul className="mt-3 flex-1 space-y-2.5 text-[11.5px]">
        {findings.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-foreground">
            <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
            <span>{f}</span>
          </li>
        ))}
      </ul>
      <Link to="/reports" className="mt-3 flex items-center gap-1 self-end text-[11.5px] font-medium text-primary hover:underline">
        View Full Report
        <ChevronRight className="h-3.5 w-3.5" />
      </Link>
    </Card>
  );
}

export function Activity() {
  const { activeProject } = useApp();
  return (
    <Card className="flex flex-col p-4">
      <h2 className="text-[13.5px] font-semibold text-foreground">Project Activity Log</h2>
      <div className="mt-3 flex flex-1 flex-col justify-center rounded-md border border-dashed border-border bg-muted/20 p-5 text-center">
        <ClipboardList className="mx-auto h-6 w-6 text-muted-foreground/60" />
        <p className="mt-2 text-[12px] font-medium text-foreground">Activity details unavailable here</p>
        <p className="mt-1 text-[10.5px] text-muted-foreground">
          {activeProject ? "Open the audit log to view persisted project events." : "Select a project to view its activity."}
        </p>
      </div>
      <Link to="/audit-log" className="mt-3 flex items-center gap-1 self-end text-[11.5px] font-medium text-primary hover:underline">
        View All Activity
        <ChevronRight className="h-3.5 w-3.5" />
      </Link>
    </Card>
  );
}
