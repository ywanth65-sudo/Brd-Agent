import { useState, type ReactNode } from "react";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard, FolderKanban, FileText, BrainCircuit, BadgeCheck, ListChecks, BarChart3,
  ClipboardList, Settings, HelpCircle, Bell, ChevronDown, ChevronRight, Menu, X, Hexagon, User, LogOut,
  Plus, LogIn, Sparkles, Users
} from "lucide-react";
import { useApp } from "@/context/AppContext";
import { CreateProjectModal } from "@/components/CreateProjectModal";
import ShareProjectModal from "@/components/ShareProjectModal";

const nav = [
  ["Dashboard", LayoutDashboard, "/"],
  ["Projects", FolderKanban, "/projects"],
  ["Documents", FileText, "/documents"],
  ["BRD Analysis", BrainCircuit, "/analysis"],
  ["AI Validations", BadgeCheck, "/validations"],
  ["Requirements", ListChecks, "/requirements"],
  ["Reports", BarChart3, "/reports"],
  ["Audit Log", ClipboardList, "/audit-log"],
  ["Settings", Settings, "/settings"],
] as const;

function Sidebar({
  active,
  onClose,
  onOpenCreate
}: {
  active: string;
  onClose?: () => void;
  onOpenCreate: () => void;
}) {
  const { activeProject } = useApp();

  return (
    <aside className="flex h-full w-[230px] flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <div className="relative grid h-8 w-8 place-items-center">
          <Hexagon className="h-8 w-8 text-sidebar-primary-foreground" strokeWidth={2.2} />
          <FileText className="absolute h-3.5 w-3.5 text-sidebar-primary-foreground" />
        </div>
        <span className="text-[15px] font-bold tracking-wide text-sidebar-primary-foreground">BRD AGENT</span>
        {onClose && (
          <button onClick={onClose} className="ml-auto lg:hidden">
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* New Project quick action */}
      <div className="px-3 pt-2 pb-1">
        <button
          onClick={() => {
            onClose?.();
            onOpenCreate();
          }}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-sidebar-primary/30 border border-sidebar-border px-3 py-2 text-[12.5px] font-medium text-sidebar-primary-foreground hover:bg-sidebar-primary/50 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>New Project</span>
        </button>
      </div>

      <nav className="mt-2 flex-1 space-y-1 px-2.5">
        {nav.map(([label, Icon, to]) => {
          const on = active === to;
          return (
            <Link
              key={label}
              to={to}
              onClick={() => onClose?.()}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-[13px] transition-colors duration-150 ${
                on
                  ? "bg-sidebar-primary font-medium text-sidebar-primary-foreground"
                  : "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Active project quick badge */}
      {activeProject && (
        <div className="mx-3 mb-3 rounded-lg border border-sidebar-border/80 bg-sidebar-accent/40 p-2.5 text-[11.5px]">
          <div className="text-[10px] uppercase tracking-wider text-sidebar-foreground/60 font-semibold">Active Project</div>
          <div className="truncate font-semibold text-sidebar-primary-foreground mt-0.5">{activeProject.title}</div>
          <div className="text-[10.5px] text-sidebar-foreground/70">{activeProject.id.slice(0, 8)}... • {activeProject.status}</div>
        </div>
      )}

      <div className="flex items-center gap-3 border-t border-sidebar-border px-5 py-4">
        <HelpCircle className="h-6 w-6 text-sidebar-foreground/70" />
        <div className="leading-tight">
          <div className="text-[13px] text-sidebar-primary-foreground">Need Help?</div>
          <Link to="/support" onClick={() => onClose?.()} className="text-[11px] text-sidebar-foreground/70 hover:underline">
            Contact Support
          </Link>
        </div>
      </div>
    </aside>
  );
}

function Header({
  onMenu,
  title,
  onOpenCreate,
  onOpenShare,
}: {
  onMenu: () => void;
  title: string;
  onOpenCreate: () => void;
  onOpenShare: () => void;
}) {
  const navigate = useNavigate();
  const {
    user,
    isAuthenticated,
    signOut,
    setShowAuthModal,
    activeProject,
    projects,
    setActiveProjectId,
    questions,
    refreshActiveProject,
  } = useApp();
  const [open, setOpen] = useState<"n" | "u" | "p" | null>(null);
  const toggle = (k: "n" | "u" | "p") => setOpen(open === k ? null : k);

  const userInitials = user?.email ? user.email.slice(0, 2).toUpperCase() : "AU";
  const userDisplayName = user?.email ? user.email.split("@")[0] : "Guest User";

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-card px-4 lg:px-6">
      <button onClick={onMenu} className="lg:hidden text-foreground">
        <Menu className="h-5 w-5" />
      </button>

      {/* Breadcrumbs & Active Project Selector */}
      <nav className="flex min-w-0 items-center gap-2 text-[13px] text-muted-foreground">
        <Link to="/projects" className="hidden hover:text-foreground sm:inline">
          Projects
        </Link>
        <ChevronRight className="hidden h-3.5 w-3.5 sm:inline" />

        {/* Project Selector dropdown */}
        <div className="relative">
          <button
            onClick={() => toggle("p")}
            className="flex items-center gap-1.5 font-medium text-foreground hover:text-primary transition-colors max-w-[200px] truncate"
          >
            <span className="truncate">{activeProject ? activeProject.title : "Select Project"}</span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          </button>

          {open === "p" && (
            <div className="absolute left-0 mt-2 w-64 rounded-md border border-border bg-popover shadow-xl py-1 z-30">
              <div className="px-3 py-1.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                Switch Project
              </div>
              <div className="max-h-56 overflow-y-auto divide-y divide-border/40">
                {projects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      setActiveProjectId(p.id);
                      setOpen(null);
                    }}
                    className={`w-full text-left px-3 py-2 text-[12.5px] hover:bg-muted transition-colors flex items-center justify-between ${
                      p.id === activeProject?.id ? "bg-accent/60 font-semibold text-primary" : ""
                    }`}
                  >
                    <span className="truncate">{p.title}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0 ml-2">
                      {p.status}
                    </span>
                  </button>
                ))}
              </div>
              <div className="p-2 border-t border-border mt-1">
                <button
                  onClick={() => {
                    setOpen(null);
                    onOpenCreate();
                  }}
                  className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded bg-primary/10 text-primary text-[12px] font-medium hover:bg-primary/20 transition-colors"
                >
                  <Plus className="h-3 w-3" />
                  <span>Create Project</span>
                </button>
              </div>
            </div>
          )}
        </div>

        <ChevronRight className="hidden h-3.5 w-3.5 md:inline" />
        <span className="truncate font-semibold text-foreground hidden md:inline">{title}</span>
      </nav>

      {/* Right side controls */}
      <div className="ml-auto flex items-center gap-3">
        {/* Quick Create Button */}
        <button
          onClick={onOpenCreate}
          className="hidden sm:flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-[12px] font-medium text-primary hover:bg-primary/20 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>New Project</span>
        </button>
        {activeProject && (
          <button
            onClick={onOpenShare}
            className="hidden sm:flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-[12px] font-medium text-primary hover:bg-primary/20 transition-colors"
            title="Share project and invite collaborators"
          >
            <Users className="h-3.5 w-3.5" />
            <span>Share / Invite</span>
            {(activeProject.collaborator_count ?? 0) > 0 && (
              <span className="rounded-full bg-primary/15 px-1.5 text-[10px]">
                {activeProject.collaborator_count}
              </span>
            )}
          </button>
        )}

        {/* Notifications (Open Clarification Questions count) */}
        <div className="relative">
          <button onClick={() => toggle("n")} className="relative rounded-md p-1.5 hover:bg-muted text-foreground">
            <Bell className="h-5 w-5 text-muted-foreground" />
            {questions.length > 0 && (
              <span className="absolute -right-0.5 -top-0.5 grid h-4 w-4 place-items-center rounded-full bg-primary text-[9px] font-semibold text-primary-foreground">
                {questions.length}
              </span>
            )}
          </button>
          {open === "n" && (
            <div className="absolute right-0 mt-2 w-72 rounded-md border border-border bg-popover shadow-xl z-30">
              <div className="border-b border-border px-4 py-2.5 text-[13px] font-semibold">
                Clarifications &amp; Alerts ({questions.length})
              </div>
              <div className="max-h-60 overflow-y-auto">
                {questions.length === 0 ? (
                  <div className="p-4 text-center text-[12px] text-muted-foreground">
                    No open clarification gaps pending.
                  </div>
                ) : (
                  questions.slice(0, 5).map((q) => (
                    <Link
                      key={q.id}
                      to="/analysis"
                      onClick={() => setOpen(null)}
                      className="block px-4 py-2.5 text-[12.5px] hover:bg-muted border-b border-border/40 last:border-0"
                    >
                      <div className="font-medium text-foreground truncate">{q.question_text}</div>
                      <div className="text-[11px] text-muted-foreground mt-0.5">Priority: {q.priority} • Impact: {q.impact}</div>
                    </Link>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* User Account / Auth */}
        {user ? (
          <div className="relative">
            <button onClick={() => toggle("u")} className="flex items-center gap-2.5">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-primary/20 text-primary text-[13px] font-semibold">
                {userInitials}
              </span>
              <span className="hidden text-left leading-tight sm:block">
                <span className="block text-[13px] font-semibold text-foreground truncate max-w-[120px]">
                  {userDisplayName}
                </span>
                <span className="block text-[11px] text-muted-foreground truncate max-w-[120px]">
                  {user.email}
                </span>
              </span>
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            </button>
            {open === "u" && (
              <div className="absolute right-0 mt-2 w-52 rounded-md border border-border bg-popover py-1 text-[13px] shadow-xl z-30">
                <div className="px-3 py-2 border-b border-border text-[11.5px] text-muted-foreground truncate">
                  Signed in as <br /><span className="font-semibold text-foreground">{user.email}</span>
                </div>
                <button
                  onClick={() => {
                    setOpen(null);
                    navigate({ to: "/profile" });
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 hover:bg-muted text-foreground"
                >
                  <User className="h-4 w-4 text-muted-foreground" />
                  <span>Profile</span>
                </button>
                <button
                  onClick={() => {
                    setOpen(null);
                    navigate({ to: "/settings" });
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 hover:bg-muted text-foreground"
                >
                  <Settings className="h-4 w-4 text-muted-foreground" />
                  <span>Settings</span>
                </button>
                <div className="border-t border-border my-1" />
                <button
                  onClick={async () => {
                    setOpen(null);
                    await signOut();
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 hover:bg-muted text-destructive font-medium"
                >
                  <LogOut className="h-4 w-4" />
                  <span>Sign Out</span>
                </button>
              </div>
            )}
          </div>
        ) : isAuthenticated ? null : (
          <button
            onClick={() => setShowAuthModal(true)}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-[12.5px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <LogIn className="h-3.5 w-3.5" />
            <span>Sign In</span>
          </button>
        )}
      </div>
    </header>
  );
}

const titles: Record<string, string> = {
  ...Object.fromEntries(nav.map(([l, , t]) => [t, l])),
  "/profile": "Profile",
  "/support": "Support",
};

export function Shell({ children }: { children: ReactNode }) {
  const path = useRouterState({ select: (r) => r.location.pathname });
  const [mobile, setMobile] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const { activeProject } = useApp();
  const { user, refreshActiveProject } = useApp();

  if (path === "/login") return <>{children}</>;

  const pageTitle = path === "/" ? (activeProject?.title ?? "Dashboard") : (titles[path] ?? "Page");

  return (
    <div className="flex min-h-screen w-full bg-background text-foreground">
      <div className="sticky top-0 hidden h-screen lg:block">
        <Sidebar active={path} onOpenCreate={() => setCreateOpen(true)} />
      </div>
      {mobile && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-foreground/40 backdrop-blur-xs" onClick={() => setMobile(false)} />
          <div className="relative h-full w-fit">
            <Sidebar
              active={path}
              onClose={() => setMobile(false)}
              onOpenCreate={() => setCreateOpen(true)}
            />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          title={pageTitle}
          onMenu={() => setMobile(true)}
          onOpenCreate={() => setCreateOpen(true)}
          onOpenShare={() => setShareOpen(true)}
        />
        <main className="flex-1 p-4 lg:p-5">{children}</main>
      </div>

      <CreateProjectModal isOpen={createOpen} onClose={() => setCreateOpen(false)} />
      {activeProject && (
        <ShareProjectModal
          isOpen={shareOpen}
          onClose={() => setShareOpen(false)}
          project={activeProject}
          currentUserId={user?.id}
          onCollaboratorChanged={() => void refreshActiveProject()}
        />
      )}
    </div>
  );
}
