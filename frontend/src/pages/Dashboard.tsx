import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/useAppStore";
import type { DataSource } from "@/store/useAppStore";
import { generateId } from "@/lib/utils";
import {
  checkBackendHealth,
  uploadFile,
  streamQuery,
  clearSession,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import ChatMessage from "@/components/ChatMessage";
import ThinkingDisplay from "@/components/ThinkingDisplay";
import FileUpload from "@/components/ui/file-upload";
import { ShiningText } from "@/components/ui/shining-text";
import {
  Sparkles,
  ArrowUp,
  X,
  FileText,
  Plus,
} from "lucide-react";
import type { ThinkingStep, QueryResult } from "@/types";

export default function Dashboard() {
  const {
    messages,
    addMessage,
    isLoading,
    setLoading,
    isUploading,
    setUploading,
    uploadError,
    setUploadError,
    uploadInfo,
    dataSource,
    setDataSource,
    uploadedFile,
    setUploadedFile,
    sessionId,
    backendAvailable,
    setBackendAvailable,
    thinkingSteps,
    addThinkingStep,
    updateThinkingStep,
    clearThinkingSteps,
    resetForNewDataset,
    setUploadInfo,
    suggestedQuestions,
    setSuggestedQuestions,
  } = useAppStore();

  const [inputValue, setInputValue] = useState("");
  const [selectedSource, setSelectedSource] = useState<DataSource>("csv");
  const [file, setFile] = useState<File | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isEmpty = messages.length === 0;
  const activeSource = dataSource ?? selectedSource ?? "csv";
  const needsUpload = activeSource === "csv" || activeSource === "database" || activeSource === "json";
  const uploadReady = !!file && !!uploadInfo && !uploadError;
  const canSubmit =
    inputValue.trim().length > 0 &&
    !isLoading &&
    !isUploading &&
    uploadReady;

  // Health check on mount + retry every 30s if backend not available
  useEffect(() => {
    const check = () => checkBackendHealth().then((ok) => setBackendAvailable(ok));
    check();
    const interval = setInterval(() => {
      if (!backendAvailable) check();
    }, 30_000);
    return () => clearInterval(interval);
  }, [setBackendAvailable, backendAvailable]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, thinkingSteps]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [inputValue]);

  const handleFile = useCallback(
    async (f: File) => {
      setUploadError(null);
      setSuggestedQuestions([]);  // clear old suggestions immediately

      // 1. Reset all previous chat + dataset context
      if (sessionId) await clearSession(sessionId);
      resetForNewDataset();

      // 2. Set the new file in local + store state
      setFile(f);
      setUploadedFile(f);
      const ext = f.name.split(".").pop()?.toLowerCase();
      const src: DataSource = ext === "json" ? "json"
        : ext === "db" || ext === "sqlite" || ext === "sqlite3" ? "database"
        : "csv";
      setDataSource(src);

      // 3. Upload immediately (gate queries until done)
      if (backendAvailable) {
        setUploading(true);
        try {
          const res = await uploadFile(f, sessionId);
          if (!res.success) {
            console.error("[handleFile] Upload failed:", res.message);
            setUploadError(res.message ?? "Upload failed");
          } else {
            console.log(`[handleFile] Uploaded ${f.name}: ${res.rows} rows, ${res.columns} columns`);
            // Store upload metadata
            if (res.rows !== undefined && res.columns !== undefined) {
              setUploadInfo({ rows: res.rows, columns: res.columns });
            }
            // Store dynamic suggested questions from backend
            if (res.suggested_questions && res.suggested_questions.length > 0) {
              setSuggestedQuestions(res.suggested_questions);
            }
          }
        } catch (err) {
          console.error("[handleFile] Upload error:", err);
          setUploadError("Upload failed — check backend is running");
        } finally {
          setUploading(false);
        }
      }
    },
    [setUploadedFile, setDataSource, resetForNewDataset, sessionId, backendAvailable, setUploading, setUploadError, setUploadInfo, setSuggestedQuestions]
  );

  const handleQuery = useCallback(
    async (question: string, sourceFallback?: DataSource) => {
      if (isLoading) return;
      const resolvedSource = sourceFallback ?? dataSource ?? selectedSource ?? "csv";
      if (!dataSource) setDataSource(resolvedSource);
      clearThinkingSteps();

      const userMsgId = generateId();
      addMessage({ id: userMsgId, role: "user", content: question, timestamp: new Date() });

      const assistantMsgId = generateId();
      setLoading(true);

      if (backendAvailable) {
        const localSteps: ThinkingStep[] = [];
        const abort = streamQuery(question, sessionId, resolvedSource ?? "csv", {
          onThinkingStep: (step) => { localSteps.push(step); addThinkingStep(step); },
          onThinkingUpdate: (id, patch) => {
            const s = localSteps.find((s) => s.id === id);
            if (s) Object.assign(s, patch);
            updateThinkingStep(id, patch);
          },
          onResult: (result: QueryResult) => {
            setLoading(false);
            addMessage({
              id: assistantMsgId, role: "assistant", content: result.answer,
              timestamp: new Date(), queryResult: result,
              thinkingSteps: localSteps.map((s) => ({ ...s, status: "done" as const })),
            });
            clearThinkingSteps();
          },
          onError: (msg) => {
            setLoading(false);
            addMessage({
              id: assistantMsgId, role: "assistant",
              content: `Sorry, something went wrong: ${msg}`, timestamp: new Date(),
              thinkingSteps: localSteps.map((s) => ({ ...s, status: "done" as const })),
            });
            clearThinkingSteps();
          },
        });
        abortRef.current = abort;
      } else {
        setLoading(false);
        clearThinkingSteps();
        addMessage({
          id: assistantMsgId,
          role: "assistant",
          content: "Backend is unavailable. Start the API server and try again. Uploaded datasets are only answered from the live backend.",
          timestamp: new Date(),
        });
      }
    },
    [isLoading, addMessage, setLoading, backendAvailable, sessionId, dataSource, selectedSource, setDataSource, addThinkingStep, updateThinkingStep, clearThinkingSteps]
  );

  const handleSubmit = () => {
    const q = inputValue.trim();
    if (!q || !canSubmit) return;
    handleQuery(q);
    setInputValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  const handleSuggestion = (q: string) => {
    const source = activeSource ?? "csv";
    if (!activeSource) { setSelectedSource("csv"); setDataSource("csv"); }
    handleQuery(q, source);
  };

  useEffect(() => {
    return () => { abortRef.current?.(); if (sessionId) clearSession(sessionId); };
  }, [sessionId]);

  /* Get follow-ups from last assistant message */
  const lastAssistantMsg = [...messages].reverse().find((m) => m.role === "assistant");
  const followUps = lastAssistantMsg?.queryResult?.follow_ups;

  /* ═══════════════════════════════════════════
     SHARED INPUT BOX — exact same component
     ═══════════════════════════════════════════ */
  const renderInputBox = (placeholder: string) => (
    <div className="bg-[#2f2f2f] rounded-xl border border-[#424242] focus-within:border-[#555] transition-colors overflow-hidden">
      <textarea
        ref={textareaRef}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={isLoading}
        rows={1}
        placeholder={placeholder}
        className="w-full resize-none bg-transparent px-9 pt-5 pb-3 text-[15px] text-[#ececec] placeholder-[#6b6b6b] focus:outline-none leading-relaxed"
        style={{ minHeight: 52 }}
      />
      <div className="flex items-center justify-between px-4 py-2.5">
        <div className="flex items-center gap-1">
          <button onClick={() => setIsUploadOpen(true)}
            className="w-9 h-9 flex items-center justify-center rounded-lg text-[#6b6b6b] hover:text-white hover:bg-[#424242] transition-colors cursor-pointer" title="Attach data file">
            <Plus className="w-5 h-5" />
          </button>
        </div>
        <button onClick={handleSubmit} disabled={!canSubmit}
          className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-200 ${
            canSubmit ? "bg-white text-[#212121] hover:bg-gray-200 cursor-pointer" : "bg-[#424242] text-[#6b6b6b] cursor-not-allowed"
          }`}>
          <ArrowUp className="w-5 h-5" />
        </button>
      </div>
    </div>
  );

  /* ═══════════════════════════════════════════
     LANDING PAGE — perfectly centered
     ═══════════════════════════════════════════ */
  if (isEmpty && !isLoading) {
    return (
      <div className="flex h-screen bg-[#212121] overflow-hidden relative">
        <Sidebar onSuggestion={handleSuggestion} />
        
        <AnimatePresence>
          {isUploadOpen && (
            <FileUpload
              onFileSelected={(f) => {
                handleFile(f);
                setIsUploadOpen(false);
              }}
              onClose={() => setIsUploadOpen(false)}
            />
          )}
        </AnimatePresence>

        <main className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-[680px] px-6">
            {/* Heading — centered */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="text-center mb-8"
            >
              <h1 className="text-[32px] font-semibold text-[#ececec] tracking-tight leading-tight">
                What would you like to analyze today?
              </h1>
              <p className="text-[15px] text-[#8e8e8e] mt-3">
                Ask questions about your data in plain English
              </p>
            </motion.div>

            {/* Suggestion chips — from uploaded dataset profile */}
            {uploadedFile && suggestedQuestions.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1, duration: 0.3 }}
                className="flex flex-wrap gap-2.5 mb-4 justify-center"
              >
                {suggestedQuestions.map((s, i) => (
                  <button key={i} onClick={() => handleSuggestion(s)}
                    className="px-4 py-2.5 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-[#424242] hover:border-[#555] rounded-lg text-[14px] text-[#b4b4b4] hover:text-white transition-all duration-150 cursor-pointer">
                    {s}
                  </button>
                ))}
              </motion.div>
            )}

            {/* File preview + upload status */}
            <AnimatePresence>
              {file && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-3 space-y-2">
                  <div className={`flex items-center gap-3 bg-[#2f2f2f] border rounded-xl px-4 py-3 ${
                    isUploading ? "border-[#555]" : uploadError ? "border-red-500/50" : "border-[#424242]"
                  }`}>
                    <FileText className="w-5 h-5 text-[#b4b4b4] flex-shrink-0" />
                    <span className="text-sm text-[#ececec] truncate flex-1">{file.name}</span>
                    {isUploading ? (
                      <span className="text-xs text-[#8e8e8e] animate-pulse">Uploading…</span>
                    ) : (
                      <span className="text-xs text-[#8e8e8e]">{(file.size / 1024).toFixed(1)} KB</span>
                    )}
                    {!isUploading && (
                      <button onClick={() => { setFile(null); setUploadedFile(null); setUploadError(null); }} className="rounded-lg p-1.5 hover:bg-[#424242] transition-colors cursor-pointer">
                        <X className="w-4 h-4 text-[#8e8e8e]" />
                      </button>
                    )}
                  </div>
                  {uploadError && (
                    <p className="text-xs text-red-400 px-1">{uploadError}</p>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Input box — centered */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.4 }}
            >
              {renderInputBox("Ask anything about your data...")}
            </motion.div>
          </div>
        </main>
      </div>
    );
  }

  /* ═══════════════════════════════════════════
     CHAT VIEW — messages + centered bottom input
     ═══════════════════════════════════════════ */
  return (
    <div className="flex h-screen bg-[#212121] overflow-hidden relative">
      <Sidebar onSuggestion={handleSuggestion} />

      <AnimatePresence>
        {isUploadOpen && (
          <FileUpload
            onFileSelected={(f) => {
              handleFile(f);
              setIsUploadOpen(false);
            }}
            onClose={() => setIsUploadOpen(false)}
          />
        )}
      </AnimatePresence>

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Chat scroll area */}
        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "thin" }}>
          <div className="flex justify-center w-full">
          <div className="w-full max-w-[680px] py-8 px-6">
            <div className="space-y-8 pb-4">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} onFollowUp={handleQuery} />
              ))}

              {/* Live thinking */}
              {isLoading && thinkingSteps.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="flex gap-4">
                    <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center flex-shrink-0 mt-0.5 border border-[#424242]">
                      <Sparkles className="w-4 h-4 text-[#b4b4b4]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <ThinkingDisplay steps={thinkingSteps} isThinking={isLoading} />
                    </div>
                  </div>
                </motion.div>
              )}

              {isLoading && thinkingSteps.length === 0 && (
                <div className="flex gap-4 items-center">
                  <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center flex-shrink-0 border border-[#424242]">
                    <Sparkles className="w-4 h-4 text-[#b4b4b4]" />
                  </div>
                  <ShiningText text="Analyzing your data..." />
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </div>
          </div>
        </div>

        {/* ── Bottom input area — CENTERED ── */}
        <div className="shrink-0 w-full flex justify-center px-6 pb-6 pt-4">
          <div className="w-full max-w-[680px]">
            {/* Follow-up suggestion chips */}
            {!isLoading && followUps && followUps.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-4"
              >
                <p className="text-[11px] font-medium text-[#6b6b6b] uppercase tracking-wider mb-3 text-center">
                  Suggested next questions
                </p>
                <div className="flex flex-wrap gap-2.5 justify-center">
                  {followUps.map((q) => (
                    <button key={q} onClick={() => handleQuery(q)}
                      className="px-4 py-2.5 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-[#424242] hover:border-[#555] rounded-xl text-[13px] leading-relaxed text-[#b4b4b4] hover:text-white transition-all duration-150 cursor-pointer">
                      {q}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}

            {renderInputBox("Ask a follow-up question...")}
          </div>
        </div>
      </main>
    </div>
  );
}
