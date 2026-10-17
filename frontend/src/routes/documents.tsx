import { useMemo, useRef, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import {
  AlertCircle, ArrowRight, CheckCircle2, Clock3, Download, FileCode2, FileImage,
  FileText, FolderOpen, Loader2, RefreshCw, Search, Sparkles, Upload, XCircle,
} from "lucide-react";
import { Card } from "@/components/brd/Panels";
import { useApp } from "@/context/AppContext";
import type { SourceDocument } from "@/types";

export const Route = createFileRoute("/documents")({
  head: () => ({
    meta: [
      { title: "Documents — BRD Agent" },
      { name: "description", content: "Grounding source files and generated Business Requirements Documents." },
    ],
  }),
  component: Page,
});

const ACCEPTED = ".pdf,.docx,.txt,.png,.jpg,.jpeg,.webp";

function formatBytes(bytes?: number | null) {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (["ready", "parsed", "completed", "processed"].includes(value)) {
    return { icon: CheckCircle2, className: "border-success/20 bg-success/10 text-success" };
  }
  if (["failed", "error"].includes(value)) {
    return { icon: XCircle, className: "border-destructive/20 bg-destructive/10 text-destructive" };
  }
  return { icon: Clock3, className: "border-warning/20 bg-warning/10 text-warning" };
}

function documentIcon(document: SourceDocument) {
  if (["png", "jpg", "jpeg", "webp", "image"].includes(document.file_type.toLowerCase())) {
    return FileImage;
  }
  if (document.file_type.toLowerCase() === "txt") return FileCode2;
  return FileText;
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

function Workflow({ activeProject, sources, requirements, questions, brdVersion }: ReturnType<typeof useApp>) {
  const stages = [
    { label: "Source documents", done: sources.length > 0, icon: FolderOpen },
    { label: "AI analysis", done: requirements.length > 0, icon: Sparkles },
    { label: "Clarification review", done: requirements.length > 0 && questions.length === 0, icon: CheckCircle2 },
    { label: "BRD generation", done: Boolean(brdVersion), icon: FileText },
  ];

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex min-w-[620px] items-center justify-between gap-2">
        {stages.map((stage, index) => {
          const Icon = stage.icon;
          return (
            <div key={stage.label} className="flex min-w-0 flex-1 items-center gap-2">
              <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border ${
                stage.done ? "border-primary/30 bg-primary/10 text-primary" : "border-border bg-muted/50 text-muted-foreground"
              }`}>
                <Icon className="h-4 w-4" />
              </div>
              <span className={`truncate text-[11px] font-medium ${stage.done ? "text-foreground" : "text-muted-foreground"}`}>
                {stage.label}
              </span>
              {index < stages.length - 1 && <span className="mx-1 h-px flex-1 bg-border" />}
            </div>
          );
        })}
      </div>
      {!activeProject && <span className="sr-only">Select a project to view workflow progress.</span>}
    </div>
  );
}

function SourceWorkspace() {
  const {
    activeProject, sources, uploadSource, isProjectLoading, refreshActiveProject,
  } = useApp();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const statuses = useMemo(() => Array.from(new Set(sources.map((source) => source.status))), [sources]);
  const filteredSources = useMemo(() => sources.filter((source) => {
    const matchesQuery = source.filename.toLowerCase().includes(query.toLowerCase().trim());
    const matchesStatus = status === "all" || source.status === status;
    return matchesQuery && matchesStatus;
  }), [query, sources, status]);

  const handleUpload = async (file?: File) => {
    if (!file || !activeProject) return;
    setUploadError(null);
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("Files must be 10 MB or smaller.");
      return;
    }
    const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
    if (!ACCEPTED.split(",").includes(extension)) {
      setUploadError("Supported formats: PDF, DOCX, TXT, PNG, JPG, and WEBP.");
      return;
    }
    setUploading(true);
    try {
      await uploadSource(file);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold text-foreground">Source Documents</h2>
          <p className="mt-1 text-[11.5px] text-muted-foreground">Upload the documents that ground your requirements in real evidence.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refreshActiveProject()}
            disabled={isProjectLoading}
            aria-label="Refresh source documents"
            className="rounded-md border border-border p-2 text-muted-foreground hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isProjectLoading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => inputRef.current?.click()}
            disabled={!activeProject || uploading}
            className="flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-[12px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            {uploading ? "Uploading..." : "Upload Documents"}
          </button>
          <input ref={inputRef} type="file" accept={ACCEPTED} className="hidden" onChange={(event) => handleUpload(event.target.files?.[0])} />
        </div>
      </div>

      {uploadError && (
        <div className="mt-4 flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-[11.5px] text-destructive" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{uploadError}</span>
          <button onClick={() => setUploadError(null)} aria-label="Dismiss upload error"><XCircle className="h-4 w-4" /></button>
        </div>
      )}

      {sources.length > 0 && (
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <label className="relative flex-1">
            <span className="sr-only">Search source documents</span>
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by filename..." className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-[12px] outline-none focus:ring-2 focus:ring-primary/20" />
          </label>
          <label>
            <span className="sr-only">Filter by processing status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="w-full rounded-md border border-border bg-background px-3 py-2 text-[12px] outline-none focus:ring-2 focus:ring-primary/20 sm:w-auto">
              <option value="all">All statuses</option>
              {statuses.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          {(query || status !== "all") && (
            <button onClick={() => { setQuery(""); setStatus("all"); }} className="rounded-md border border-border px-3 py-2 text-[12px] text-muted-foreground hover:bg-muted">Clear filters</button>
          )}
        </div>
      )}

      <div className="mt-5">
        {isProjectLoading ? (
          <div className="flex min-h-[180px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/20 text-[12px] text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin text-primary" /> Loading documents...</div>
        ) : sources.length === 0 ? (
          <div className="flex min-h-[190px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 p-6 text-center">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-primary/10 text-primary"><Upload className="h-5 w-5" /></div>
            <h3 className="mt-3 text-[13px] font-semibold text-foreground">Add your first source documents</h3>
            <p className="mt-1 max-w-md text-[11.5px] text-muted-foreground">Ground your BRD with customer briefs, PRDs, meeting notes, architecture documents, or supported whiteboard images.</p>
            <p className="mt-3 text-[10.5px] text-muted-foreground">PDF, DOCX, TXT, PNG, JPG, WEBP · Maximum 10 MB</p>
          </div>
        ) : filteredSources.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-8 text-center text-[12px] text-muted-foreground">No documents match the current filters.</div>
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {filteredSources.map((source) => {
              const Icon = documentIcon(source);
              const tone = statusTone(source.status);
              const StatusIcon = tone.icon;
              return (
                <div key={source.id} className="flex min-w-0 items-start gap-3 rounded-lg border border-border bg-background p-3 transition-colors hover:border-primary/30">
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-primary/10 text-primary"><Icon className="h-4 w-4" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12.5px] font-semibold text-foreground" title={source.filename}>{source.filename}</p>
                    <p className="mt-1 text-[10.5px] text-muted-foreground">{source.file_type.toUpperCase()} {formatBytes(source.file_size_bytes) ? `· ${formatBytes(source.file_size_bytes)}` : ""} {formatDate(source.created_at) ? `· ${formatDate(source.created_at)}` : ""}</p>
                    <p className="mt-1 text-[10.5px] text-muted-foreground">{source.chunk_count} grounded chunks</p>
                  </div>
                  <span className={`inline-flex shrink-0 items-center gap-1 rounded border px-2 py-1 text-[9.5px] font-semibold uppercase ${tone.className}`}><StatusIcon className="h-3 w-3" />{source.status}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
}

function Deliverables() {
  const { activeProject, brdVersion, downloadDocx, isGeneratingBRD } = useApp();
  const navigate = useNavigate();
  return (
    <Card className="p-5">
      <div>
        <h2 className="text-[15px] font-semibold text-foreground">Generated BRD Deliverables</h2>
        <p className="mt-1 text-[11.5px] text-muted-foreground">Access business requirements documents generated from your project materials.</p>
      </div>
      <div className="mt-5">
        {brdVersion ? (
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
            <div className="flex items-start gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary/15 text-primary"><FileText className="h-5 w-5" /></div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-semibold text-foreground">{brdVersion.title}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">Version {brdVersion.version_number} · {brdVersion.status}{formatDate(brdVersion.created_at) ? ` · ${formatDate(brdVersion.created_at)}` : ""}</p>
              </div>
              <span className="inline-flex items-center gap-1 rounded border border-success/20 bg-success/10 px-2 py-1 text-[9.5px] font-semibold uppercase text-success"><CheckCircle2 className="h-3 w-3" />Available</span>
            </div>
            <button onClick={downloadDocx} disabled={isGeneratingBRD} className="mt-4 flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-[12px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {isGeneratingBRD ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              {isGeneratingBRD ? "Preparing download..." : "Download Word (.docx)"}
            </button>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-border bg-muted/20 p-6 text-center">
            <div className="mx-auto grid h-10 w-10 place-items-center rounded-lg bg-muted text-muted-foreground"><FileText className="h-5 w-5" /></div>
            <h3 className="mt-3 text-[13px] font-semibold text-foreground">No BRD generated yet</h3>
            <p className="mx-auto mt-1 max-w-sm text-[11.5px] text-muted-foreground">Upload source documents, run analysis, resolve clarification gaps, and generate your first BRD.</p>
            {activeProject && <button onClick={() => navigate({ to: "/analysis" })} className="mt-4 inline-flex items-center gap-1.5 text-[11.5px] font-semibold text-primary hover:underline">Open analysis workspace <ArrowRight className="h-3.5 w-3.5" /></button>}
          </div>
        )}
      </div>
    </Card>
  );
}

function Page() {
  const app = useApp();
  const { activeProject, sources, requirements, questions, assumptions, brdVersion, isProjectLoading } = app;
  const processed = sources.filter((source) => ["ready", "parsed", "completed", "processed"].includes(source.status.toLowerCase())).length;
  const processing = sources.filter((source) => !["ready", "parsed", "completed", "processed", "failed", "error"].includes(source.status.toLowerCase())).length;
  const failed = sources.filter((source) => ["failed", "error"].includes(source.status.toLowerCase())).length;

  if (!activeProject && !isProjectLoading) {
    return <Card className="mx-auto mt-8 max-w-xl p-10 text-center"><FolderOpen className="mx-auto h-8 w-8 text-primary" /><h1 className="mt-3 text-lg font-semibold text-foreground">Select a project to manage documents</h1><p className="mt-2 text-[12px] text-muted-foreground">Choose a project from the header or create one before uploading source materials.</p><Link to="/projects" className="mt-5 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-[12px] font-semibold text-primary-foreground">Open projects <ArrowRight className="h-3.5 w-3.5" /></Link></Card>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 text-[11px] text-muted-foreground">Projects <span className="mx-1">/</span> {activeProject?.title || "Project"} <span className="mx-1">/</span> Documents</div>
          <h1 className="text-[22px] font-bold tracking-tight text-foreground">Document Workspace</h1>
          <p className="mt-1 text-[12.5px] text-muted-foreground">Manage source materials, track processing, and access generated business requirements documents.</p>
          {activeProject && <p className="mt-2 text-[12px] font-medium text-primary">{activeProject.title}</p>}
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-[11px] text-muted-foreground"><Sparkles className="h-3.5 w-3.5 text-primary" /> Evidence-led document intelligence</div>
      </div>

      {activeProject && <Workflow {...app} />}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {([
          ["Source documents", sources.length, FolderOpen],
          ["Processed", processed, CheckCircle2],
          ["Processing", processing, Clock3],
          ["Issues", failed, AlertCircle],
        ] as const).map(([label, value, Icon]) => (
          <Card key={String(label)} className="flex items-center gap-3 p-3"><Icon className="h-4 w-4 shrink-0 text-primary" /><div><p className="text-[18px] font-bold text-foreground">{isProjectLoading ? "—" : value}</p><p className="text-[10.5px] text-muted-foreground">{label}</p></div></Card>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,.65fr)]">
        <SourceWorkspace />
        <Deliverables />
      </div>
      {activeProject && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 text-[11.5px] text-muted-foreground">
          <span>{requirements.length} requirements · {questions.length} clarification gaps · {assumptions.length} assumptions</span>
          <Link to="/analysis" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">Continue in analysis <ArrowRight className="h-3.5 w-3.5" /></Link>
        </div>
      )}
    </div>
  );
}
