import { useState } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import {
  ArrowRight, Check, ChevronRight, FileCheck2, FileText, GitBranch, Menu, ShieldCheck,
  Sparkles, Upload, Users, X,
} from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "BRD Agent — Requirements you can trust" },
      { name: "description", content: "Turn scattered project information into traceable business requirements and structured BRDs." },
    ],
  }),
  component: Landing,
});

type DemoTab = "sources" | "requirements" | "gaps" | "brd";

const demoTabs: { id: DemoTab; label: string }[] = [
  { id: "sources", label: "Source documents" },
  { id: "requirements", label: "Requirements" },
  { id: "gaps", label: "Conflicts & gaps" },
  { id: "brd", label: "BRD preview" },
];

function DemoPanel({ tab }: { tab: DemoTab }) {
  const content: Record<DemoTab, import("react").ReactNode> = {
    sources: <div className="space-y-2">{["customer-brief.pdf", "checkout-notes.docx", "architecture.txt"].map((file, index) => <div key={file} className="flex items-center gap-3 rounded-lg border border-border bg-background p-3"><FileText className={`h-4 w-4 ${index === 1 ? "text-primary" : "text-muted-foreground"}`} /><div className="min-w-0 flex-1"><p className="truncate text-[12px] font-semibold">{file}</p><p className="text-[10px] text-muted-foreground">{index === 2 ? "Ready to analyze" : "Processed source"}</p></div><span className="rounded-full bg-success/10 px-2 py-1 text-[9px] font-semibold text-success">{index === 2 ? "READY" : "PARSED"}</span></div>)}</div>,
    requirements: <div className="space-y-2">{[["REQ-014", "Customers can save a preferred payment method", "MUST"], ["REQ-021", "Checkout confirms the final amount before payment", "SHOULD"], ["REQ-033", "Payment failures are logged for support review", "MUST"]].map(([id, text, priority]) => <div key={id} className="rounded-lg border border-border bg-background p-3"><div className="flex items-center justify-between gap-3"><span className="font-mono text-[10px] text-primary">{id}</span><span className="rounded border border-warning/20 bg-warning/10 px-2 py-0.5 text-[9px] font-semibold text-warning">{priority}</span></div><p className="mt-2 text-[11.5px] font-medium">{text}</p><p className="mt-1 text-[10px] text-muted-foreground">Evidence: customer-brief.pdf · 86% illustrative confidence</p></div>)}</div>,
    gaps: <div className="space-y-3"><div className="rounded-lg border border-warning/20 bg-warning/5 p-4"><div className="flex items-center gap-2 text-warning"><GitBranch className="h-4 w-4" /><span className="text-[11px] font-semibold">Clarification needed</span></div><p className="mt-2 text-[12px] font-medium">Should saved payment methods be available across all customer accounts?</p><p className="mt-2 text-[10.5px] text-muted-foreground">Review the decision before generating the final BRD.</p></div><div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4"><p className="text-[11px] font-semibold text-destructive">Potential conflict</p><p className="mt-1 text-[11px] text-muted-foreground">Two source notes describe different payment retry windows.</p></div></div>,
    brd: <div className="rounded-lg border border-border bg-background p-5"><div className="flex items-center gap-3 border-b border-border pb-4"><FileCheck2 className="h-6 w-6 text-primary" /><div><p className="text-[13px] font-bold">Payment Platform BRD</p><p className="text-[10px] text-muted-foreground">Demonstration preview · structured for review</p></div></div><div className="mt-5 space-y-3">{["Executive summary", "Functional requirements", "Assumptions & dependencies", "Traceability matrix"].map((section, index) => <div key={section} className="flex items-center gap-2 text-[11px]"><span className="grid h-5 w-5 place-items-center rounded bg-primary/10 text-[9px] text-primary">{index + 1}</span>{section}<ChevronRight className="ml-auto h-3 w-3 text-muted-foreground" /></div>)}</div></div>,
  };
  return <div className="min-h-[255px] transition-opacity duration-200">{content[tab]}</div>;
}

function Landing() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [tab, setTab] = useState<DemoTab>("requirements");

  const closeMobile = () => setMobileOpen(false);
  return (
    <main className="min-h-screen overflow-hidden bg-background text-foreground">
      <nav className="sticky top-0 z-30 border-b border-border/80 bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 lg:px-8">
          <Link to="/" className="flex items-center gap-2 font-bold tracking-tight"><span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-foreground"><FileText className="h-4 w-4" /></span>BRD Agent</Link>
          <div className="hidden items-center gap-7 text-[12px] font-medium text-muted-foreground md:flex"><a href="#product" className="hover:text-foreground">Product</a><a href="#workflow" className="hover:text-foreground">How it works</a><a href="#features" className="hover:text-foreground">Features</a><a href="#trust" className="hover:text-foreground">Why BRD Agent</a></div>
          <div className="hidden items-center gap-2 md:flex"><Link to="/login" className="rounded-md px-3 py-2 text-[12px] font-semibold text-muted-foreground hover:text-foreground">Sign in</Link><Link to="/projects" className="rounded-md bg-primary px-3.5 py-2 text-[12px] font-semibold text-primary-foreground hover:bg-primary/90">Open workspace</Link></div>
          <button className="md:hidden" aria-label={mobileOpen ? "Close menu" : "Open menu"} onClick={() => setMobileOpen(!mobileOpen)}>{mobileOpen ? <X /> : <Menu />}</button>
        </div>
        {mobileOpen && <div className="border-t border-border bg-card p-4 md:hidden"><div className="flex flex-col gap-3 text-sm"><a href="#product" onClick={closeMobile}>Product</a><a href="#workflow" onClick={closeMobile}>How it works</a><a href="#features" onClick={closeMobile}>Features</a><Link to="/projects" onClick={closeMobile} className="font-semibold text-primary">Open workspace</Link></div></div>}
      </nav>

      <section id="product" className="mx-auto grid max-w-7xl gap-12 px-5 pb-20 pt-16 lg:grid-cols-[.9fr_1.1fr] lg:items-center lg:px-8 lg:pt-24">
        <div><p className="mb-5 flex items-center gap-2 text-[10px] font-bold tracking-[.18em] text-primary"><span className="h-1.5 w-1.5 rounded-full bg-primary" />AI-POWERED REQUIREMENTS ENGINEERING</p><h1 className="max-w-xl text-4xl font-bold tracking-[-.04em] text-foreground sm:text-6xl">Turn scattered documents into <span className="text-primary">requirements you can trust.</span></h1><p className="mt-6 max-w-lg text-base leading-7 text-muted-foreground">BRD Agent transforms project documents into structured business requirements, helping teams uncover gaps, review assumptions, trace evidence, and create clearer Business Requirements Documents.</p><div className="mt-8 flex flex-wrap gap-3"><Link to="/projects" className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground shadow-sm hover:bg-primary/90">Start a project <ArrowRight className="h-4 w-4" /></Link><a href="#workflow" className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-5 py-3 text-sm font-semibold hover:bg-muted">Explore the workflow</a></div><p className="mt-5 text-[11px] text-muted-foreground">From source documents to a structured BRD.</p></div>
        <div className="rounded-2xl border border-border bg-card p-3 shadow-[0_18px_60px_-30px_rgba(30,64,175,.35)]"><div className="rounded-xl border border-border bg-muted/30 p-3"><div className="flex items-center justify-between border-b border-border pb-3"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-destructive/60" /><span className="h-2 w-2 rounded-full bg-warning/70" /><span className="h-2 w-2 rounded-full bg-success/70" /><span className="ml-2 text-[10px] font-medium text-muted-foreground">Demonstration workspace</span></div><span className="text-[10px] text-muted-foreground">Sample project</span></div><div className="flex gap-1 overflow-x-auto border-b border-border py-3">{demoTabs.map((item) => <button key={item.id} onClick={() => setTab(item.id)} className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-[10px] font-semibold ${tab === item.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}>{item.label}</button>)}</div><div className="pt-4"><DemoPanel tab={tab} /></div><p className="mt-2 text-[9px] text-muted-foreground">Illustrative sample content — not connected to customer data.</p></div></div>
      </section>

      <section id="trust" className="border-y border-border bg-card"><div className="mx-auto max-w-7xl px-5 py-16 lg:px-8"><div className="max-w-2xl"><p className="text-[10px] font-bold tracking-[.18em] text-primary">A BETTER REVIEW LOOP</p><h2 className="mt-3 text-3xl font-bold tracking-tight">AI-generated doesn't have to mean AI-guessed.</h2><p className="mt-4 text-sm leading-6 text-muted-foreground">BRD Agent helps teams examine the evidence behind extracted requirements, identify unresolved questions, and review assumptions before producing a formal requirements document.</p></div>      <div className="mt-10 grid gap-4 md:grid-cols-3">{([
        ["Evidence-linked requirements", "Keep requirements connected to the source materials that support them, where the available data provides that traceability.", FileText],
        ["Gaps, conflicts & clarifications", "Surface missing decisions, conflicting statements, and questions that need stakeholder input.", GitBranch],
        ["Structured BRD generation", "Bring reviewed requirements and explicit assumptions together into a structured Business Requirements Document.", FileCheck2],
      ] as const).map(([title, body, Icon]) => <div key={title} className="rounded-xl border border-border bg-background p-5"><Icon className="h-5 w-5 text-primary" /><h3 className="mt-5 text-sm font-semibold">{title}</h3><p className="mt-2 text-[12px] leading-5 text-muted-foreground">{body}</p></div>)}</div></div></section>

      <section id="workflow" className="mx-auto max-w-7xl px-5 py-20 lg:px-8"><div className="max-w-2xl"><p className="text-[10px] font-bold tracking-[.18em] text-primary">THE WORKFLOW</p><h2 className="mt-3 text-3xl font-bold tracking-tight">From raw information to a requirements document.</h2></div><div className="mt-12 grid gap-4 md:grid-cols-4">{([
        ["01", "Bring your sources together", "Upload project briefs, PRDs, meeting notes, and other supported documents.", Upload],
        ["02", "Extract requirements", "Organize source information into structured requirement categories.", Sparkles],
        ["03", "Review what needs attention", "Inspect evidence, clarify decisions, review assumptions, and investigate conflicts.", ShieldCheck],
        ["04", "Generate your BRD", "Produce a structured Business Requirements Document for review and sharing.", FileCheck2],
      ] as const).map(([number, title, body, Icon]) => <div key={number} className="relative rounded-xl border border-border bg-card p-5"><span className="font-mono text-[11px] text-primary">{number}</span><Icon className="mt-8 h-5 w-5 text-primary" /><h3 className="mt-4 text-sm font-semibold">{title}</h3><p className="mt-2 text-[12px] leading-5 text-muted-foreground">{body}</p></div>)}</div></section>

      <section id="features" className="border-t border-border bg-muted/30"><div className="mx-auto max-w-7xl space-y-5 px-5 py-20 lg:px-8"><div className="max-w-xl"><p className="text-[10px] font-bold tracking-[.18em] text-primary">WHY BRD AGENT</p><h2 className="mt-3 text-3xl font-bold tracking-tight">A workspace for decisions, not just generation.</h2></div><div className="grid gap-5 lg:grid-cols-3">{[["Understand every requirement in context.", "Inspect a requirement's origin, priority, confidence, and available supporting evidence.", "REQ-014 · MUST · Evidence linked"], ["Find unanswered questions before they become problems.", "Clarification questions, assumptions, and conflicts make decisions that still need review visible.", "2 gaps · 1 assumption to review"], ["Turn reviewed requirements into a document your team can work with.", "Bring the reviewed workflow together in a structured BRD that can be downloaded for stakeholder review.", "BRD · version 1 · ready for review"]].map(([title, body, label], index) => <div key={title} className={`rounded-2xl border border-border bg-card p-6 ${index === 1 ? "lg:translate-y-5" : ""}`}><div className="rounded-lg border border-border bg-muted/30 p-3 text-[10px] text-muted-foreground">{label}</div><h3 className="mt-6 text-lg font-semibold">{title}</h3><p className="mt-3 text-sm leading-6 text-muted-foreground">{body}</p></div>)}</div></div></section>

      <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8"><div className="grid gap-5 lg:grid-cols-2"><div className="rounded-2xl border border-border bg-card p-6"><h3 className="text-sm font-semibold">Scattered project information</h3><ul className="mt-5 space-y-3 text-[12px] text-muted-foreground">{["Meeting notes", "Different document formats", "Unclear decisions", "Conflicting statements", "Missing requirements"].map((item) => <li key={item} className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 rounded-full bg-warning" />{item}</li>)}</ul></div><div className="rounded-2xl border border-primary/20 bg-primary/5 p-6"><h3 className="text-sm font-semibold">An organized requirements workspace</h3><ul className="mt-5 space-y-3 text-[12px] text-muted-foreground">{["Structured requirements", "Traceable source references where available", "Visible clarification gaps", "Explicit assumptions", "A structured BRD"].map((item) => <li key={item} className="flex gap-2"><Check className="h-3.5 w-3.5 text-primary" />{item}</li>)}</ul></div></div><div className="mt-5 rounded-2xl border border-border bg-card p-6"><div className="flex items-start gap-3"><ShieldCheck className="h-5 w-5 shrink-0 text-primary" /><div><h3 className="text-sm font-semibold">Clarity over guesswork.</h3><p className="mt-2 max-w-2xl text-[12px] leading-5 text-muted-foreground">A useful requirements workflow distinguishes supported requirements, uncertain information, explicit assumptions, and unanswered questions so stakeholders know what still needs review.</p></div></div></div></section>

      <section className="mx-5 mb-16 rounded-2xl bg-primary px-6 py-14 text-center text-primary-foreground lg:mx-auto lg:max-w-7xl lg:px-8"><h2 className="text-3xl font-bold tracking-tight">Build your next BRD on a clearer foundation.</h2><p className="mx-auto mt-4 max-w-xl text-sm text-primary-foreground/80">Bring your source documents together and start turning project information into structured business requirements.</p><div className="mt-7 flex flex-wrap justify-center gap-3"><Link to="/projects" className="rounded-lg bg-white px-5 py-3 text-sm font-semibold text-primary hover:bg-white/90">Start a project</Link><a href="#workflow" className="rounded-lg border border-white/30 px-5 py-3 text-sm font-semibold hover:bg-white/10">Explore the workflow</a></div></section>
      <footer className="border-t border-border bg-card"><div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-8 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between lg:px-8"><div><Link to="/" className="font-bold text-foreground">BRD Agent</Link><p className="mt-1">AI-powered requirements engineering for clearer BRDs.</p></div><div className="flex flex-wrap gap-5"><a href="#product">Product</a><a href="#workflow">How it works</a><a href="#features">Features</a><Link to="/projects">Workspace</Link></div></div></footer>
    </main>
  );
}
