import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/useAppStore";
import type { DataSource } from "@/store/useAppStore";
import { generateId } from "@/lib/utils";
import {
  checkBackendHealth,
  uploadFilesWithProgress,
  streamQuery,
  clearSession,
  removeUploadedTable,
  type UploadProgressEvent,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import ChatMessage from "@/components/ChatMessage";
import ThinkingDisplay from "@/components/ThinkingDisplay";
import FileUpload from "@/components/ui/file-upload";
import { ShiningText } from "@/components/ui/shining-text";
import { Sparkles, ArrowUp, X, FileText, Plus, Database } from "lucide-react";
import type { ThinkingStep, QueryResult } from "@/types";

export default function Dashboard() {
  const {
    messages, addMessage, isLoading, setLoading,
    isUploading, setUploading, uploadError, setUploadError,
    uploadInfo, dataSource, setDataSource,
    uploadedFile, setUploadedFile,
    uploadedFiles, setUploadedFiles,
    sessionId, backendAvailable, setBackendAvailable,
    thinkingSteps, addThinkingStep, updateThinkingStep, clearThinkingSteps,
    resetForNewDataset, setUploadInfo, suggestedQuestions, setSuggestedQuestions,
    clearChat,
  } = useAppStore();

  const [inputValue, setInputValue] = useState("");
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<UploadProgressEvent | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const uploadOpsRef = useRef(0);
  const abortRef = useRef<(() => void) | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isEmpty = messages.length === 0;
  const activeSource: DataSource = dataSource ?? "csv";
  // Ready when at least one file is fully profiled (rows > 0)
  const readyFileCount = uploadedFiles.filter((f) => f.rows > 0).length;
  const hasPendingFiles = uploadedFiles.some((f) => f.rows === 0);
  const uploadReady = readyFileCount > 0;
  const canSubmit = inputValue.trim().length > 0 && !isLoading && !isUploading && uploadReady;

  const stageHint = (stage: string) => {
    const map: Record<string, string> = {
      dataset_uploaded: "Dataset upload received",
      duckdb: "Loading into DuckDB (large JSON may take 1-3 minutes)",
      yaml_engine: "Understanding schema (YAML engine)",
      yaml_generated: "Semantic YAML generated",
      semantic_embedding: "Building semantic query context",
      ready: "Ready to query",
    };
    return map[stage] ?? "Processing dataset";
  };

  useEffect(() => {
    const check = () => checkBackendHealth().then((ok) => setBackendAvailable(ok));
    check();
    const interval = setInterval(() => { if (!backendAvailable) check(); }, 30_000);
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

  const handleFiles = useCallback(
    async (newFiles: File[]) => {
      if (!newFiles.length) return;

      if (isLoading) {
        abortRef.current?.();
        abortRef.current = null;
        setLoading(false);
        clearThinkingSteps();
      }

      setUploadError(null);
      setUploadStatus(null);
      setUploadProgress({
        percent: 0,
        stage: "dataset_uploaded",
        message: "Preparing upload...",
      });
      setSuggestedQuestions([]);

      // Fresh session reset only on very first upload.
      // Same-filename replacement is handled server-side without wiping all tables.
      const isFirstUpload = uploadedFiles.length === 0;
      if (isFirstUpload) {
        if (sessionId) await clearSession(sessionId);
        resetForNewDataset();
      }

      // Set primary file for legacy display
      const first = newFiles[0];
      setUploadedFile(first);
      const ext = first.name.split(".").pop()?.toLowerCase();
      const src: DataSource =
        ext === "json" ? "json"
        : ext === "db" || ext === "sqlite" || ext === "sqlite3" ? "database"
        : "csv";
      setDataSource(src);

      // Reflect selected files in UI immediately (before backend profiling)
      const pendingBatch = newFiles.map((f) => ({
        file: f,
        tableName: `pending:${f.name}:${Date.now()}:${Math.random().toString(36).slice(2, 7)}`,
        rows: 0,
        columns: 0,
      }));
      setUploadedFiles((prev) => {
        const without = prev.filter((item) => !newFiles.some((f) => item.file.name === f.name));
        return [...without, ...pendingBatch];
      });

      uploadOpsRef.current += 1;
      setUploading(true);
      try {
        const res = await uploadFilesWithProgress(newFiles, sessionId, (event) => {
          setUploadProgress(event);
        });
        if (!res.success) {
          setUploadError(res.message ?? "Upload failed");
          // Revert pending entries to prior state on failure
          setUploadedFiles((prev) => prev.filter((item) => item.rows > 0));
          const remaining = useAppStore.getState().uploadedFiles;
          if (remaining.length > 0) {
            setUploadedFile(remaining[0].file);
            setUploadInfo({ rows: remaining[0].rows, columns: remaining[0].columns });
          } else {
            // Keep failed selection visible so user can retry/remove and still see error context.
            setUploadedFile(first);
            setUploadInfo(null);
          }
          setUploadProgress(null);
        } else {
          const tableList = (res.tables && res.tables.length > 0)
            ? res.tables
            : (typeof res.rows === "number" && typeof res.columns === "number")
              ? [{
                  name: pendingBatch[0]?.tableName ?? `table_${Date.now()}`,
                  filename: res.filename ?? first.name,
                  rows: res.rows,
                  columns: res.columns,
                }]
              : [];

          const profiled = tableList.map((tbl) => {
            const sourceFile = newFiles.find((f) => f.name === tbl.filename) ?? newFiles[0];
            return { file: sourceFile, tableName: tbl.name, rows: tbl.rows, columns: tbl.columns };
          });
          setUploadedFiles((prev) => {
            const without = prev.filter((item) => !newFiles.some((f) => item.file.name === f.name));
            return profiled.length > 0
              ? [...without, ...profiled]
              : [...without, ...pendingBatch];
          });

          const firstTbl = tableList[0];
          if (firstTbl) setUploadInfo({ rows: firstTbl.rows, columns: firstTbl.columns });
          if (res.suggested_questions?.length) setSuggestedQuestions(res.suggested_questions);
          if (res.errors?.length) console.warn("[upload] partial errors:", res.errors);

          // Surface clear status so user always knows what happened
          setUploadStatus(res.message ?? null);
          setUploadProgress({
            percent: 100,
            stage: "ready",
            message: "Data is ready. You can now query.",
          });
          setTimeout(() => setUploadStatus(null), 4000);
        }
      } catch (err) {
        setUploadError("Upload failed — is the backend running?");
        setUploadedFiles((prev) => prev.filter((item) => item.rows > 0));
        const remaining = useAppStore.getState().uploadedFiles;
        if (remaining.length > 0) {
          setUploadedFile(remaining[0].file);
          setUploadInfo({ rows: remaining[0].rows, columns: remaining[0].columns });
        } else {
          // Keep failed selection visible so user can retry/remove and still see error context.
          setUploadedFile(first);
          setUploadInfo(null);
        }
        setUploadProgress(null);
      } finally {
        uploadOpsRef.current = Math.max(0, uploadOpsRef.current - 1);
        setUploading(uploadOpsRef.current > 0);
      }
    },
    [sessionId, isLoading, setLoading, clearThinkingSteps,
     setUploadedFile, setDataSource, resetForNewDataset,
     setUploading, setUploadError, setUploadInfo, setSuggestedQuestions,
     setUploadedFiles, uploadedFiles]
  );

  const handleQuery = useCallback(
    async (question: string, sourceFallback?: DataSource) => {
      if (isLoading || isUploading) return;

      const hasUploadedData = useAppStore.getState().uploadedFiles.some((f) => f.rows > 0);
      if (!hasUploadedData) {
        addMessage({
          id: generateId(),
          role: "assistant",
          content: "Please upload at least one data file before asking questions.",
          timestamp: new Date(),
        });
        return;
      }

      const resolvedSource = sourceFallback ?? dataSource ?? "csv";
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
          id: assistantMsgId, role: "assistant",
          content: "Backend is unavailable. Start the API server and try again.",
          timestamp: new Date(),
        });
      }
    },
    [isLoading, isUploading, addMessage, setLoading, backendAvailable, sessionId, dataSource,
     setDataSource, addThinkingStep, updateThinkingStep, clearThinkingSteps]
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

  const handleSuggestion = (q: string) => handleQuery(q, activeSource ?? "csv");

  const handleHistoryJump = useCallback((messageId: string) => {
    messageRefs.current[messageId]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const removeFile = useCallback(async (tableName: string) => {
    const previous = useAppStore.getState().uploadedFiles;
    const next = previous.filter((f) => f.tableName !== tableName);

    if (next.length === previous.length) return;

    setUploadError(null);
    setUploadedFiles(next);

    if (next.length > 0) {
      setUploadedFile(next[0].file);
      setUploadInfo({ rows: next[0].rows, columns: next[0].columns });
    } else {
      setUploadedFile(null);
      setUploadInfo(null);
      setDataSource(null);
      setUploadProgress(null);
      setUploadStatus(null);
      setSuggestedQuestions([]);
    }

    try {
      const res = await removeUploadedTable(sessionId, tableName);
      if (!res.ok) {
        throw new Error("Failed to remove table from backend session");
      }

      // Data context changed; clear chat and thinking to avoid stale follow-ups.
      clearChat();
      clearThinkingSteps();

      if (next.length === 0 || res.remaining_tables <= 0) {
        await clearSession(sessionId);
      }
    } catch {
      // Roll back optimistic UI update on backend failure.
      setUploadedFiles(previous);
      if (previous.length > 0) {
        setUploadedFile(previous[0].file);
        setUploadInfo({ rows: previous[0].rows, columns: previous[0].columns });
      } else {
        setUploadedFile(null);
        setUploadInfo(null);
      }
      setUploadError("Could not remove the file from session. Please try again.");
    }
  }, [sessionId, clearChat, clearThinkingSteps, setDataSource, setUploadError, setUploadedFile, setUploadedFiles, setUploadInfo, setSuggestedQuestions]);

  useEffect(() => {
    return () => { abortRef.current?.(); if (sessionId) clearSession(sessionId); };
  }, [sessionId]);

  const lastAssistantMsg = [...messages].reverse().find((m) => m.role === "assistant");
  const followUps = lastAssistantMsg?.queryResult?.follow_ups;

  /* ── Shared input box ── */
  const renderInputBox = (placeholder: string) => (
    <div className="bg-[#2f2f2f] rounded border border-[#424242] focus-within:border-[#555] transition-colors overflow-hidden">
      <textarea
        ref={textareaRef}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={isLoading || isUploading}
        rows={1}
        placeholder={placeholder}
        className="w-full resize-none bg-transparent text-[15px] text-[#ececec] placeholder-[#6b6b6b] focus:outline-none leading-relaxed"
        style={{ minHeight: 52, paddingLeft: 20, paddingRight: 20, paddingTop: 16, paddingBottom: 12 }}
      />
      <div className="flex items-center justify-between px-5 py-3">
        <button
          onClick={() => setIsUploadOpen(true)}
          className="w-9 h-9 flex items-center justify-center rounded-lg text-[#6b6b6b] hover:text-white hover:bg-[#424242] transition-colors cursor-pointer"
          title="Add data file"
        >
          <Plus className="w-5 h-5" />
        </button>
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-200 ${
            canSubmit
              ? "bg-white text-[#212121] hover:bg-gray-200 cursor-pointer"
              : "bg-[#424242] text-[#6b6b6b] cursor-not-allowed"
          }`}
        >
          <ArrowUp className="w-5 h-5" />
        </button>
      </div>
    </div>
  );

  /* ── File chips strip ── */
  const renderFileChips = () => {
    const hasAnyUploadUi = (
      uploadedFiles.length > 0
      || Boolean(uploadedFile)
      || Boolean(uploadError)
      || Boolean(uploadStatus)
      || isUploading
      || Boolean(uploadProgress)
    );
    if (!hasAnyUploadUi) return null;

    // Show uploaded-files list (new) or legacy single file
    const display = uploadedFiles.length > 0 ? uploadedFiles : null;
    const showLegacyCard = !display && Boolean(uploadedFile);

    return (
      <div className="flex flex-wrap gap-2.5 mb-3">
        {display ? (
          display.map((info) => (
            <div
              key={info.tableName}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg border text-sm ${
                isUploading
                  ? "border-[#555] bg-[#2f2f2f]"
                  : uploadError
                  ? "border-red-500/50 bg-[#2f2f2f]"
                  : "border-[#424242] bg-[#2f2f2f]"
              }`}
            >
              <Database className="w-4 h-4 text-[#b4b4b4] shrink-0" />
              <span className="text-[#ececec] truncate max-w-55">{info.file.name}</span>
              {info.rows === 0 ? (
                isUploading ? (
                  <span className="text-xs text-[#8e8e8e] animate-pulse">uploading…</span>
                ) : (
                  <span className="text-xs text-[#8e8e8e]">selected</span>
                )
              ) : (
                <span className="text-xs text-[#8e8e8e]">
                  {info.rows.toLocaleString()} rows
                </span>
              )}
              {!isUploading && (
                <button
                  onClick={() => { void removeFile(info.tableName); }}
                  className="p-0.5 rounded hover:bg-[#424242] transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5 text-[#6b6b6b]" />
                </button>
              )}
            </div>
          ))
        ) : showLegacyCard ? (
          <div className={`flex items-center gap-3 bg-[#2f2f2f] border rounded px-4 py-3 ${
            isUploading ? "border-[#555]" : uploadError ? "border-red-500/50" : "border-[#424242]"
          }`}>
            <FileText className="w-5 h-5 text-[#b4b4b4] shrink-0" />
            <span className="text-sm text-[#ececec] truncate flex-1">{uploadedFile?.name}</span>
            {isUploading && <span className="text-xs text-[#8e8e8e] animate-pulse">Uploading…</span>}
            {!isUploading && (
              <button
                onClick={() => {
                  setUploadedFile(null);
                  setUploadInfo(null);
                  setSuggestedQuestions([]);
                  setUploadedFiles([]);
                  setDataSource(null);
                  void clearSession(sessionId);
                }}
                className="p-1 rounded hover:bg-[#424242] transition-colors cursor-pointer"
                title="Remove file"
              >
                <X className="w-4 h-4 text-[#6b6b6b]" />
              </button>
            )}
          </div>
        ) : null}

        {!display && !showLegacyCard && isUploading && (
          <div className="w-full rounded-lg border border-[#424242] bg-[#232323] px-3 py-2.5">
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-[#b4b4b4]">{uploadProgress?.message ?? "Processing dataset..."}</span>
              <span className="text-[#8e8e8e]">{uploadProgress?.percent ?? 0}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-[#3a3a3a] overflow-hidden">
              <div
                className="h-full bg-emerald-500 transition-all duration-300"
                style={{ width: `${Math.max(0, Math.min(100, uploadProgress?.percent ?? 0))}%` }}
              />
            </div>
            <p className="text-[11px] text-[#8e8e8e] mt-1.5">
              {stageHint(uploadProgress?.stage ?? "dataset_uploaded")}
            </p>
          </div>
        )}
        {hasPendingFiles && isUploading && !uploadError && (
          <div className="w-full rounded-lg border border-[#424242] bg-[#232323] px-3 py-2.5">
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-[#b4b4b4]">{uploadProgress?.message ?? "Processing dataset..."}</span>
              <span className="text-[#8e8e8e]">{uploadProgress?.percent ?? 0}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-[#3a3a3a] overflow-hidden">
              <div
                className="h-full bg-emerald-500 transition-all duration-300"
                style={{ width: `${Math.max(0, Math.min(100, uploadProgress?.percent ?? 0))}%` }}
              />
            </div>
            <p className="text-[11px] text-[#8e8e8e] mt-1.5">
              {stageHint(uploadProgress?.stage ?? "dataset_uploaded")}
            </p>
          </div>
        )}
        {uploadError && <p className="w-full text-xs text-red-400 px-1">{uploadError}</p>}
        {uploadStatus && !uploadError && !isUploading && (
          <p className="w-full text-xs text-emerald-400/80 px-1">{uploadStatus}</p>
        )}
        {isUploading && (
          <p className="w-full text-xs text-[#8e8e8e] px-1">Please wait, data is still being processed.</p>
        )}
      </div>
    );
  };

  /* ── Landing page ── */
  if (isEmpty && !isLoading) {
    return (
      <div className="flex h-screen bg-[#212121] overflow-hidden">
        <Sidebar onSuggestion={handleSuggestion} onHistoryJump={handleHistoryJump} />
        <AnimatePresence>
          {isUploadOpen && (
            <FileUpload
              onFilesSelected={(files) => { handleFiles(files); }}
              onClose={() => setIsUploadOpen(false)}
            />
          )}
        </AnimatePresence>

        <main className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-190 px-6 md:px-8">
            <motion.div
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }} className="text-center mb-8"
            >
              <h1 className="text-[32px] font-semibold text-[#ececec] tracking-tight leading-tight">
                What would you like to analyze today?
              </h1>
              <p className="text-[15px] text-[#8e8e8e] mt-3">
                Ask questions about your data in plain English
              </p>
            </motion.div>

            {uploadedFiles.length > 0 && suggestedQuestions.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
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

            <AnimatePresence>
              {(uploadedFiles.length > 0 || uploadedFile) && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  {renderFileChips()}
                </motion.div>
              )}
            </AnimatePresence>

            <motion.div
              initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.4 }}
            >
              {renderInputBox("Ask anything about your data...")}
            </motion.div>
          </div>
        </main>
      </div>
    );
  }

  /* ── Chat view ── */
  return (
    <div className="flex h-screen bg-[#212121] overflow-hidden">
      <Sidebar onSuggestion={handleSuggestion} onHistoryJump={handleHistoryJump} />
      <AnimatePresence>
        {isUploadOpen && (
          <FileUpload
            onFilesSelected={(files) => { handleFiles(files); }}
            onClose={() => setIsUploadOpen(false)}
          />
        )}
      </AnimatePresence>

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "thin" }}>
          <div className="flex justify-center w-full">
            <div className="w-full max-w-190 py-8 px-6 md:px-8">
              <div className="space-y-8 pb-4">
                {messages.map((msg) => (
                  <div key={msg.id} ref={(el) => { messageRefs.current[msg.id] = el; }} id={`message-${msg.id}`}>
                    <ChatMessage message={msg} onFollowUp={handleQuery} />
                  </div>
                ))}

                {isLoading && thinkingSteps.length > 0 && (
                  <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <div className="flex gap-4">
                      <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center shrink-0 mt-0.5 border border-[#424242]">
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
                    <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center shrink-0 border border-[#424242]">
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

        {/* Bottom input */}
        <div className="shrink-0 w-full flex justify-center px-6 md:px-8 pb-6 pt-4">
          <div className="w-full max-w-190">
            {!isLoading && followUps && followUps.length > 0 && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mb-4">
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
