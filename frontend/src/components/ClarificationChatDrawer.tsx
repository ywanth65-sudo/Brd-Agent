import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  Send,
  X,
  RotateCcw,
  CheckCircle2,
  Bot,
  User,
  ArrowRight,
  HelpCircle,
  Zap,
  Check,
  FileText,
  Loader2,
} from 'lucide-react';
import { sendProjectChatMessage, getChatHistory } from '../api/projects';

import type { Project, Question, ChatMessage, UserProfileResponse } from '../types';

interface DisplayChatMessage extends ChatMessage {
  id: string;
  senderName?: string;
  senderRole?: string;
  resolvedQuestionId?: string | null;
  isReadyToGenerate?: boolean;
}

interface ClarificationChatDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  openQuestions: Question[];
  currentUserProfile?: UserProfileResponse | null;
  onClarificationResolved?: () => void;
  onNavigateToGenerate?: () => void;
}

export default function ClarificationChatDrawer({
  isOpen,
  onClose,
  project,
  openQuestions,
  currentUserProfile,
  onClarificationResolved,
  onNavigateToGenerate,
}: ClarificationChatDrawerProps) {

  const [messages, setMessages] = useState<DisplayChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to latest message
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, isSending]);

  // Set active highest priority question
  useEffect(() => {
    if (openQuestions && openQuestions.length > 0) {
      const sorted = [...openQuestions].sort((a, b) => b.priority - a.priority);
      setActiveQuestion(sorted[0]);
    } else {
      setActiveQuestion(null);
    }
  }, [openQuestions]);

  // Fetch persistent chat history from DB or initialize welcome message
  useEffect(() => {
    if (!isOpen || !project.id) return;

    let isMounted = true;
    setIsLoadingHistory(true);
    setHistoryError(null);
    setMessages([]);

    getChatHistory(project.id)
      .then((history) => {
        if (!isMounted) return;
        if (history && history.length > 0) {
          const loaded: DisplayChatMessage[] = history.map((record) => {
            const isBot = record.role === 'assistant';
            const formattedTime = record.created_at
              ? new Date(record.created_at).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : '';

            return {
              id: record.id,
              role: isBot ? 'assistant' : 'user',
              content: record.content,
              senderName:
                record.sender_name || (isBot ? 'AI Interviewer' : record.sender_email),
              senderRole: isBot ? 'Llama 3.3 70B' : 'Collaborator',
              timestamp: formattedTime,
            };
          });
          setMessages(loaded);
        } else {
          // No history yet, build welcome greeting
          const gapCount = openQuestions ? openQuestions.length : 0;
          let initialGreeting = `Hi! I'm your AI Lead Business Analyst. I've reviewed **${project.title}** and all uploaded grounding sources.`;

          if (gapCount > 0 && openQuestions[0]) {
            initialGreeting += `\n\nWe have **${gapCount} open ${
              gapCount === 1 ? 'clarification gap' : 'clarification gaps'
            }** that need stakeholder decisions before generating a complete BRD.\n\nLet's start with the top priority:\n**${
              openQuestions[0].question_text
            }**`;
            if (openQuestions[0].why_it_matters) {
              initialGreeting += `\n\n*(Why it matters: ${openQuestions[0].why_it_matters})*`;
            }
          } else {
            initialGreeting += `\n\nAll current requirements appear grounded and clear! You are ready to generate your formal BRD, or you can ask me questions about your architecture, user personas, or scope.`;
          }

          setMessages([
            {
              id: 'msg-welcome',
              role: 'assistant',
              content: initialGreeting,
              senderName: 'AI Interviewer',
              senderRole: 'Llama 3.3 70B',
              timestamp: new Date().toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              }),
            },
          ]);
        }
      })
      .catch((err) => {
        console.error('Failed to load chat history:', err);
        if (isMounted) {
          setHistoryError(err?.message || 'Unable to load conversation history.');
        }
      })
      .finally(() => {
        if (isMounted) setIsLoadingHistory(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, project.id, historyReloadKey]);


  // Focus textarea when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 150);
    }
  }, [isOpen]);

  const handleRefreshHistory = () => {
    setMessages([]);
    setHistoryReloadKey((value) => value + 1);
  };

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend ?? inputValue).trim();
    if (!text || isSending) return;

    const userSenderName = currentUserProfile?.full_name || currentUserProfile?.email || 'You';
    const userSenderRole = currentUserProfile?.role_title || 'Collaborator';

    const userMsgId = `user-${Date.now()}`;
    const userMsg: DisplayChatMessage = {
      id: userMsgId,
      role: 'user',
      content: text,
      senderName: userSenderName,
      senderRole: userSenderRole,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const newHistory: ChatMessage[] = [
      ...messages.map((m) => ({ role: m.role, content: m.content })),
      { role: 'user', content: text },
    ];

    setMessages((prev) => [...prev, userMsg]);
    setInputValue('');
    setSendError(null);
    setIsSending(true);

    try {
      const res = await sendProjectChatMessage(project.id, text, newHistory);

      const botMsg: DisplayChatMessage = {
        id: `bot-${Date.now()}`,
        role: 'assistant',
        content: res.reply,
        senderName: 'AI Interviewer',
        senderRole: 'Llama 3.3 70B',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        resolvedQuestionId: res.answered_question_id,
        isReadyToGenerate: res.is_ready_to_generate,
      };

      setMessages((prev) => [...prev, botMsg]);

      // If an answer was saved or project reached ready-to-generate, refresh dashboard
      if (res.answered_question_id || res.is_ready_to_generate) {
        onClarificationResolved?.();
      }
    } catch (err: any) {
      setMessages((prev) => prev.filter((message) => message.id !== userMsgId));
      setInputValue(text);
      setSendError(err.message || 'Unable to connect to the assistant.');
    } finally {
      setIsSending(false);
    }
  };


  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Determine quick replies from active question
  const getQuickReplies = (): string[] => {
    if (!activeQuestion) return [];
    if (activeQuestion.answer_format === 'YES_NO') {
      return ['Yes', 'No'];
    }
    if (activeQuestion.options && activeQuestion.options.length > 0) {
      return activeQuestion.options;
    }
    return [];
  };

  const quickReplies = getQuickReplies();

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-xs transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-over Drawer */}
      <aside
        id="clarification-chat-drawer"
        role="dialog"
        aria-label="AI Requirements Interviewer"
        className="fixed inset-y-0 right-0 z-50 w-full max-w-lg md:max-w-xl bg-slate-950 border-l border-slate-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300"
      >
        {/* Drawer Header */}
        <header className="p-4 border-b border-slate-800/90 bg-slate-900/60 backdrop-blur-md flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-cyan-500/20 to-brand-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shrink-0">
              <Bot className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-white tracking-tight truncate">
                  AI Requirements Interviewer
                </h2>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 flex items-center gap-1 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  Active
                </span>
              </div>
              <p className="text-xs text-slate-400 truncate">
                Interactive discovery & clarification for {project.title}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={handleRefreshHistory}
              title="Refresh conversation"
              className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              title="Close chat"
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Status Strip */}
        <div className="px-4 py-2 bg-slate-900/40 border-b border-slate-800/60 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-slate-400">
            <HelpCircle className="w-3.5 h-3.5 text-violet-400" />
            <span>Open Questions:</span>
            <span className="font-semibold text-slate-200">
              {openQuestions.length} remaining
            </span>
          </div>
          {project.status === 'READY_TO_GENERATE' && (
            <span className="text-[11px] font-medium text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Ready to Generate
            </span>
          )}
        </div>

        {/* Message Thread */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {historyError && (
            <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
              <div>{historyError}</div>
              <button
                type="button"
                onClick={() => setHistoryReloadKey((value) => value + 1)}
                className="mt-2 font-semibold text-rose-100 underline"
              >
                Refresh conversation
              </button>
            </div>
          )}

          {!isLoadingHistory && !historyError && messages.length === 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-center text-xs text-slate-400">
              No conversation yet. Ask about a requirement or clarify the project scope.
            </div>
          )}

          {isLoadingHistory && (
            <div className="flex items-center justify-center py-12 text-xs text-slate-400 gap-2.5">
              <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
              <span>Loading conversation history...</span>
            </div>
          )}

          {!isLoadingHistory && messages.map((msg) => {
            const isUser = msg.role === 'user';
            const senderLabel = msg.senderName || (isUser ? 'You' : 'AI Interviewer');
            const roleLabel = msg.senderRole || (isUser ? 'Collaborator' : 'Llama 3.3 70B');


            return (
              <div
                key={msg.id}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} gap-1`}
              >
                {/* Author attribution chip */}
                <div
                  className={`flex items-center gap-1.5 px-1 text-[11px] ${
                    isUser ? 'flex-row-reverse text-cyan-300' : 'text-slate-400'
                  }`}
                >
                  <span className="font-semibold text-slate-200">{senderLabel}</span>
                  {roleLabel && (
                    <span
                      className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full border ${
                        isUser
                          ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'
                          : 'bg-slate-800 text-slate-400 border-slate-700/80'
                      }`}
                    >
                      {roleLabel}
                    </span>
                  )}
                </div>

                <div
                  className={`flex gap-3 max-w-[88%] ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <div className="h-8 w-8 rounded-lg bg-slate-800 border border-slate-700/80 flex items-center justify-center text-cyan-400 shrink-0 mt-0.5">
                      <Sparkles className="w-4 h-4 text-cyan-400" />
                    </div>
                  )}

                  <div
                    className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                      isUser
                        ? 'bg-gradient-to-r from-brand-600 to-indigo-600 text-white rounded-tr-xs shadow-brand-500/10'
                        : 'bg-slate-900/90 border border-slate-800 text-slate-200 rounded-tl-xs'
                    }`}
                  >
                    {/* Markdown-style content rendering */}
                    <div className="whitespace-pre-wrap space-y-2">
                      {msg.content.split('\n\n').map((paragraph, idx) => (
                        <p key={idx} className="leading-relaxed">
                          {paragraph}
                        </p>
                      ))}
                    </div>

                    {/* Inline resolved question badge */}
                    {msg.resolvedQuestionId && (
                      <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span>✓ Requirement updated & grounded (ID: {msg.resolvedQuestionId})</span>
                      </div>
                    )}

                    {/* Ready to generate action button inside bot response */}
                    {msg.isReadyToGenerate && (
                      <div className="mt-3 pt-2 border-t border-slate-800/80">
                        <button
                          onClick={() => {
                            onClose();
                            onNavigateToGenerate?.();
                          }}
                          className="w-full mt-1 px-3 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 transition"
                        >
                          <FileText className="w-4 h-4" />
                          Ready to Generate — View & Compile BRD
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}

                    {/* Timestamp */}
                    {msg.timestamp && (
                      <div
                        className={`text-[10px] mt-1.5 ${
                          isUser ? 'text-brand-200/70 text-right' : 'text-slate-500'
                        }`}
                      >
                        {msg.timestamp}
                      </div>
                    )}
                  </div>

                  {isUser && (
                    <div className="h-8 w-8 rounded-lg bg-indigo-600/30 border border-indigo-500/30 flex items-center justify-center text-indigo-300 shrink-0 mt-0.5">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              </div>
            );
          })}


          {/* Typing/Thinking Indicator */}
          {isSending && (
            <div className="flex gap-3 justify-start animate-in fade-in duration-200">
              <div className="h-8 w-8 rounded-lg bg-slate-800 border border-slate-700/80 flex items-center justify-center text-cyan-400 shrink-0 mt-0.5">
                <Sparkles className="w-4 h-4 text-cyan-400 animate-pulse" />
              </div>
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl rounded-tl-xs px-4 py-3 text-xs text-slate-400 flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span>Analyzing & grounding response...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick-Reply Chips for Options */}
        {quickReplies.length > 0 && !isSending && (
          <div className="px-4 py-2 border-t border-slate-800/80 bg-slate-900/30">
            <p className="text-[11px] text-slate-400 mb-1.5 flex items-center gap-1 font-medium">
              <Zap className="w-3 h-3 text-amber-400" /> Quick select answer:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {quickReplies.map((opt, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleSend(opt)}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium bg-brand-500/10 hover:bg-brand-500/20 text-brand-300 border border-brand-500/30 hover:border-brand-500/50 transition flex items-center gap-1"
                >
                  <span>{opt}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Footer Input Bar */}
        <footer className="p-3 border-t border-slate-800 bg-slate-900/80 backdrop-blur-md">
          {sendError && (
            <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
              <span>{sendError}</span>
              <button
                type="button"
                onClick={() => handleSend()}
                disabled={isSending || !inputValue.trim()}
                className="font-semibold underline disabled:opacity-50"
              >
                Retry
              </button>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-end gap-2"
          >
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question or clarify a requirement..."
                rows={2}
                disabled={isSending}
                className="w-full resize-none rounded-xl bg-slate-900/90 border border-slate-700/80 px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 transition disabled:opacity-50"
              />
            </div>
            <button
              type="submit"
              disabled={isSending || !inputValue.trim()}
              className="p-3 rounded-xl bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white shadow-md shadow-brand-500/20 transition disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
              title="Send message"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1.5 px-1">
            <span>Press Enter to send, Shift+Enter for new line</span>
            <span>Grounds requirements immutably</span>
          </div>
        </footer>
      </aside>
    </>
  );
}
