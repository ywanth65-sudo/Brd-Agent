import { useState, useEffect, useCallback, type FormEvent } from 'react';
import {
  Users,
  Copy,
  Check,
  X,
  Trash2,
  Crown,
  Shield,
  Loader2,
  AlertCircle,
  Link as LinkIcon,
  Mail,
  Send,
  Clock,
  CheckCircle2,
} from 'lucide-react';
import {
  getCollaborators,
  getProjectInvitations,
  removeCollaborator,
  sendProjectInvitation,
} from '../api/projects';
import type { Project, CollaboratorResponse, InvitationResponse } from '../types';

interface ShareProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  currentUserId?: string;
  onCollaboratorChanged?: () => void;
}

export default function ShareProjectModal({
  isOpen,
  onClose,
  project,
  currentUserId,
  onCollaboratorChanged,
}: ShareProjectModalProps) {
  const [collaborators, setCollaborators] = useState<CollaboratorResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [removingUserId, setRemovingUserId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Email Invitation State
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'editor' | 'viewer'>('editor');
  const [isInviting, setIsInviting] = useState(false);
  const [inviteSuccessMessage, setInviteSuccessMessage] = useState<string | null>(null);
  const [pendingInvites, setPendingInvites] = useState<InvitationResponse[]>([]);


  const shareUrl = `${window.location.origin}/?join=${project.id}`;

  const fetchTeam = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await getCollaborators(project.id);
      setCollaborators(data);
      const invitations = await getProjectInvitations(project.id);
      setPendingInvites(invitations);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load team members.');
      setCollaborators([]);
      setPendingInvites([]);
    } finally {
      setIsLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    if (isOpen) {
      fetchTeam();
      setIsCopied(false);
    }
  }, [isOpen, fetchTeam]);

  if (!isOpen) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2500);
    } catch {
      // Fallback copy using textarea
      const el = document.createElement('textarea');
      el.value = shareUrl;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2500);
    }
  };

  const handleRemove = async (userId: string, userEmail: string) => {
    if (!confirm(`Are you sure you want to remove ${userEmail} from this project?`)) {
      return;
    }

    setRemovingUserId(userId);
    setErrorMessage(null);
    try {
      await removeCollaborator(project.id, userId);
      setCollaborators((prev) => prev.filter((c) => c.user_id !== userId));
      onCollaboratorChanged?.();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to remove collaborator.');
    } finally {
      setRemovingUserId(null);
    }
  };

  const handleSendInvite = async (e: FormEvent) => {
    e.preventDefault();
    const email = inviteEmail.trim().toLowerCase();
    if (!email || !email.includes('@')) {
      setErrorMessage('Please enter a valid email address.');
      return;
    }

    setIsInviting(true);
    setErrorMessage(null);
    setInviteSuccessMessage(null);

    try {
      await sendProjectInvitation(project.id, email, inviteRole);
      setInviteSuccessMessage(`Invitation dispatched to ${email}!`);
      setInviteEmail('');
      await fetchTeam();
      setTimeout(() => setInviteSuccessMessage(null), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to dispatch invitation.');
    } finally {
      setIsInviting(false);
    }
  };


  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-lg rounded-2xl bg-slate-900/95 border border-slate-800 shadow-2xl shadow-indigo-500/10 overflow-hidden flex flex-col">
        {/* Accent Bar */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-brand-500 via-indigo-500 to-cyan-500" />

        {/* Modal Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-800/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-brand-500/20">
              <Users className="w-5 h-5 text-cyan-300" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Share Project & Invite Collaborators
              </h3>
              <p className="text-xs text-slate-400 truncate max-w-[280px]">
                {project.title}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-5">
          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Share Link Box */}
          <div className="space-y-2">
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <LinkIcon className="w-3.5 h-3.5 text-cyan-400" />
                Invite Link
              </span>
              <span className="text-[11px] font-normal text-slate-400 lowercase">
                authenticate before joining
              </span>
            </label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  readOnly
                  value={shareUrl}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-slate-300 text-xs font-mono select-all focus:outline-none focus:border-cyan-500/50"
                  onClick={(e) => (e.target as HTMLInputElement).select()}
                />
              </div>
              <button
                id="btn-copy-share-link"
                onClick={handleCopy}
                className={`px-3.5 py-2.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 border transition shadow-sm ${
                  isCopied
                    ? 'bg-emerald-600/30 border-emerald-500/50 text-emerald-300'
                    : 'bg-brand-600/20 hover:bg-brand-600/30 border-brand-500/40 text-brand-300 hover:text-white'
                }`}
              >
                {isCopied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    Copy Link
                  </>
                )}
              </button>
            </div>
            <p className="text-[11px] text-slate-500">
              Recipients must authenticate before joining. Share links join with editor access. in clarification interviews.
            </p>
          </div>

          {/* Invite Teammate by Email Form */}
          <div className="space-y-2.5 pt-2 border-t border-slate-800">
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-indigo-400" />
                Invite by Email
              </span>
              <span className="text-[11px] font-normal text-slate-400 lowercase">
                direct team invitation
              </span>
            </label>
            <form onSubmit={handleSendInvite} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <input
                id="input-invite-email"
                type="email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="flex-1 px-3.5 py-2 rounded-xl bg-slate-950/80 border border-slate-700/80 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/50"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as 'editor' | 'viewer')}
                className="px-3 py-2 rounded-xl bg-slate-950/80 border border-slate-700/80 text-slate-300 text-xs focus:outline-none focus:border-indigo-500/60 capitalize"
              >
                <option value="editor">Editor</option>
                <option value="viewer">Viewer</option>
              </select>
              <button
                id="btn-send-invitation"
                type="submit"
                disabled={isInviting || !inviteEmail.trim()}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-brand-600 hover:from-indigo-500 hover:to-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-1.5 shadow-md shadow-indigo-500/20 transition disabled:opacity-50 shrink-0"
              >
                {isInviting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Inviting...
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    Send Invite
                  </>
                )}
              </button>
            </form>

            {inviteSuccessMessage && (
              <div className="flex items-center gap-1.5 text-xs text-emerald-400 pt-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{inviteSuccessMessage}</span>
              </div>
            )}
          </div>

          {/* Pending Invitations list */}
          {pendingInvites.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                Sent Invitations ({pendingInvites.length})
              </h4>
              <div className="space-y-1.5 max-h-32 overflow-y-auto pr-1">
                {pendingInvites.map((inv) => (
                  <div
                    key={inv.id}
                    className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/80 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <Mail className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                      <span className="text-slate-300 truncate">{inv.invitee_email}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 capitalize">
                        {inv.role}
                      </span>
                    </div>
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 shrink-0 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                      Pending
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Collaborator Roster */}
          <div className="space-y-3 pt-2 border-t border-slate-800">

            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-indigo-400" />
                Collaborators ({collaborators.length + (project.owner_email ? 1 : 0)})
              </h4>
              {isLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-400" />}
            </div>

            <div className="max-h-60 overflow-y-auto space-y-2 pr-1">
              {/* Owner card */}
              {project.owner_email && (
                <div className="p-3 rounded-xl bg-slate-950/60 border border-amber-500/30 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-300 font-bold text-xs shrink-0">
                      {project.owner_email[0].toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-white truncate">
                          {project.owner_email}
                        </span>
                        {project.is_owner && (
                          <span className="text-[10px] text-slate-400">(You)</span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400">Project Creator</p>
                    </div>
                  </div>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1 shrink-0">
                    <Crown className="w-3 h-3" />
                    Owner
                  </span>
                </div>
              )}

              {/* Collaborator items */}
              {collaborators.map((c) => {
                const displayName = c.full_name || c.user_email;
                const isCurrent = currentUserId === c.user_id;
                const isOwner = project.is_owner ?? false;

                return (
                  <div
                    key={c.id || c.user_id}
                    className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/80 flex items-center justify-between gap-3 hover:border-slate-700/80 transition"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 font-bold text-xs shrink-0">
                        {displayName[0].toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-slate-200 truncate">
                            {displayName}
                          </span>
                          {isCurrent && (
                            <span className="text-[10px] text-slate-400">(You)</span>
                          )}
                        </div>
                        {c.full_name && (
                          <p className="text-[11px] text-slate-500 truncate font-mono">
                            {c.user_email}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 capitalize">
                        {c.role || 'Editor'}
                      </span>

                      {/* Owner can remove non-owner collaborators */}
                      {isOwner && !isCurrent && (
                        <button
                          onClick={() => handleRemove(c.user_id, c.user_email)}
                          disabled={removingUserId === c.user_id}
                          className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 border border-transparent hover:border-rose-500/30 transition"
                          title="Remove collaborator"
                        >
                          {removingUserId === c.user_id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}

              {!isLoading && collaborators.length === 0 && !project.owner_email && (
                <div className="p-4 rounded-xl border border-dashed border-slate-800 text-center text-xs text-slate-500">
                  No teammates added yet. Share the invite link above!
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end p-4 border-t border-slate-800/80 bg-slate-950/40">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-300 bg-slate-800 hover:bg-slate-700 transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
