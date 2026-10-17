import { useState } from "react";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { Card } from "@/components/brd/Panels";
import { useApp } from "@/context/AppContext";
import { CreateProjectModal } from "@/components/CreateProjectModal";
import { Plus, FolderKanban, Search, ChevronRight, Sparkles } from "lucide-react";

export const Route = createFileRoute("/projects")({
  head: () => ({
    meta: [
      { title: "Projects — BRD Agent" },
      { name: "description", content: "Active BRD projects, requirements synthesis and documents." },
    ],
  }),
  component: Page,
});

function Page() {
  const { projects, activeProjectId, setActiveProjectId } = useApp();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  const filtered = projects.filter((p) =>
    (p.title || "").toLowerCase().includes(search.toLowerCase()) ||
    (p.idea || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold text-foreground">Projects Workspace</h1>
          <p className="text-[12.5px] text-muted-foreground">Manage your AI-powered Business Requirements Documents</p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-[12.5px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
        >
          <Plus className="h-4 w-4" />
          <span>New Project</span>
        </button>
      </div>

      <div className="relative max-w-md">
        <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search projects by title or scope..."
          className="w-full pl-9 pr-3 py-2 text-[13px] bg-card border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>

      <Card className="divide-y divide-border">
        {filtered.length === 0 ? (
          <div className="p-12 text-center">
            <FolderKanban className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
            <h3 className="text-[14px] font-semibold text-foreground">No projects found</h3>
            <p className="text-[12px] text-muted-foreground mt-1 mb-4">
              {search ? "No projects match your search query." : "You haven't created any BRD projects yet."}
            </p>
            <button
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-1.5 text-[12.5px] font-medium text-primary-foreground"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Create Project</span>
            </button>
          </div>
        ) : (
          filtered.map((p) => {
            const isActive = p.id === activeProjectId;
            const created = p.created_at
              ? new Date(p.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
              : "Recently";

            return (
              <div
                key={p.id}
                onClick={() => {
                  setActiveProjectId(p.id);
                  navigate({ to: "/workspace" });
                }}
                className={`flex items-center justify-between p-4 cursor-pointer transition-colors hover:bg-muted/60 ${
                  isActive ? "bg-accent/40" : ""
                }`}
              >
                <div className="min-w-0 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-[14px] text-foreground truncate">{p.title}</span>
                    {isActive && (
                      <span className="text-[10px] bg-primary/10 text-primary border border-primary/20 px-1.5 py-0.2 rounded font-semibold uppercase">
                        Current
                      </span>
                    )}
                  </div>
                  <p className="text-[12px] text-muted-foreground mt-1 line-clamp-1">{p.idea}</p>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-2">
                    <span>ID: <code className="font-mono">{p.id.slice(0, 8)}</code></span>
                    <span>•</span>
                    <span>Created {created}</span>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-[11px] font-semibold uppercase px-2 py-0.5 rounded border border-border bg-muted/80 text-foreground">
                    {p.status}
                  </span>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </div>
            );
          })
        )}
      </Card>

      <CreateProjectModal isOpen={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
