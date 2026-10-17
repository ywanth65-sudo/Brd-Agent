import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import AuthModal from "@/components/AuthModal";
import { useApp } from "@/context/AppContext";
import { LogOut, ArrowRight, ShieldCheck } from "lucide-react";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in — BRD Agent" },
      { name: "description", content: "Sign in to BRD Agent workspace." },
      { property: "og:title", content: "Sign in — BRD Agent" },
      { property: "og:description", content: "Sign in to BRD Agent workspace." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Login,
});

function Login() {
  const { isAuthenticated, user, signOut } = useApp();
  const navigate = useNavigate();

  if (!user) {
    return (
      <div className="relative min-h-screen bg-slate-950">
        <AuthModal isOpen={true} onSuccess={() => navigate({ to: "/workspace" })} />
      </div>
    );
  }

  return (
    <div className="grid min-h-screen place-items-center bg-background p-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 text-center shadow-lg">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary mb-3">
          <ShieldCheck className="h-6 w-6" />
        </div>
        <h1 className="text-[18px] font-bold text-foreground">BRD AGENT</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Currently signed in as{" "}
          <span className="font-medium text-foreground">
            {user?.email || "Guest User (demo mode)"}
          </span>
        </p>

        <div className="mt-6 flex flex-col gap-2.5">
          <Link
            to="/"
            className="flex items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-[13px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <span>Open Workspace</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
          <button
            onClick={() => signOut()}
            className="flex items-center justify-center gap-2 rounded-lg border border-border py-2 text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Sign Out</span>
          </button>
        </div>
      </div>
    </div>
  );
}
