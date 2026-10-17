import { createFileRoute } from "@tanstack/react-router";
import { Actions, KeyFindings, KPIs, ValidationSummary, exportCsv } from "@/components/brd/Panels";
import { useApp } from "@/context/AppContext";
import { Download, FileSpreadsheet } from "lucide-react";

export const Route = createFileRoute("/reports")({
  head: () => ({
    meta: [
      { title: "Reports — BRD Agent" },
      { name: "description", content: "Executive BRD reports, KPI dashboards, and export tools in BRD Agent." },
      { property: "og:title", content: "Reports — BRD Agent" },
      { property: "og:description", content: "Executive BRD reports, KPI dashboards, and export tools in BRD Agent." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Page,
});

function Page() {
  const { downloadDocx, isGeneratingBRD, requirements, activeProject, brdVersion } = useApp();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[18px] font-semibold text-foreground">Project Reports & Exports</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportCsv(requirements, activeProject?.title)}
            className="flex items-center gap-1.5 rounded-md border border-border bg-card px-3.5 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-400" />
            Export CSV
          </button>
          <button
            onClick={() => downloadDocx()}
            disabled={isGeneratingBRD || !brdVersion}
            title={!brdVersion ? "Generate the BRD before downloading a Word document" : "Download the generated BRD"}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-1.5 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            Download Word (.docx)
          </button>
        </div>
      </div>

      <Actions />
      <KPIs />
      <div className="grid gap-3 md:grid-cols-2">
        <KeyFindings />
        <ValidationSummary />
      </div>
    </div>
  );
}
