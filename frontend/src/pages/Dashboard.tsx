import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/useAppStore";
import type { DataSource } from "@/store/useAppStore";
import { getMockResult } from "@/lib/mockData";
import { generateId, sleep } from "@/lib/utils";
import {
  checkBackendHealth,
  uploadFile,
  streamQuery,
  clearSession,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import ChatMessage from "@/components/ChatMessage";
import ThinkingDisplay from "@/components/ThinkingDisplay";
import { ShiningText } from "@/components/ui/shining-text";
import {
  Sparkles,
  Upload,
  Database,
  BarChart3,
  FileJson,
  ArrowUp,
  X,
  FileText,
  Plus,
} from "lucide-react";
import type { ThinkingStep, QueryResult } from "@/types";

/* ─── Data source options ─── */
const SOURCE_OPTIONS: {
  id: DataSource;
  icon: React.ElementType;
  label: string;
  accept?: string;
}[] = [
  { id: "csv", icon: Upload, label: "CSV", accept: ".csv" },
  { id: "database", icon: Database, label: "Database", accept: ".db,.sqlite,.sqlite3" },
  { id: "json", icon: FileJson, label: "JSON", accept: ".json" },
  { id: "sample", icon: BarChart3, label: "Sample Data" },
];

const SUGGESTIONS = [
  "What is total revenue?",
  "Top 3 cities by orders",
  "Revenue by region",
  "Category breakdown",
];

export default function Dashboard() {
  const {
    messages,
    addMessage,
    isLoading,
    setLoading,
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
  } = useAppStore();

  const [inputValue, setInputValue] = useState("");
  const [selectedSource, setSelectedSource] = useState<DataSource>(null);
  const [file, setFile] = useState<File | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isEmpty = messages.length === 0;
  const activeSource = dataSource ?? selectedSource;
  const needsUpload = activeSource === "csv" || activeSource === "database" || activeSource === "json";
  const canSubmit =
    inputValue.trim().length > 0 &&
    !isLoading &&
    (activeSource === "sample" || (needsUpload && file !== null));

  useEffect(() => {
    checkBackendHealth().then((ok) => setBackendAvailable(ok));
  }, [setBackendAvailable]);

  useEffect(() => {
    if (!backendAvailable || !uploadedFile || dataSource === "sample") return;
    uploadFile(uploadedFile, sessionId).then((res) => {
      if (!res.success) console.warn("File upload failed:", res.message);
    });
  }, [backendAvailable, uploadedFile, sessionId, dataSource]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, thinkingSteps]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [inputValue]);

  const handleSelectSource = (src: DataSource) => {
    setSelectedSource(src);
    setFile(null);
    if (src === "sample") setDataSource("sample");
  };

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      setUploadedFile(f);
    },
    [setUploadedFile]
  );

  const handleQuery = useCallback(
    async (question: string, sourceFallback?: DataSource) => {
      if (isLoading) return;
      const resolvedSource = sourceFallback ?? dataSource ?? selectedSource ?? "sample";
      if (!dataSource) setDataSource(resolvedSource);
      clearThinkingSteps();

      const userMsgId = generateId();
      addMessage({ id: userMsgId, role: "user", content: question, timestamp: new Date() });

      const assistantMsgId = generateId();
      setLoading(true);

      if (backendAvailable) {
        const localSteps: ThinkingStep[] = [];
        const abort = streamQuery(question, sessionId, resolvedSource ?? "sample", {
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
        const stepIds = { routing: generateId(), sql: generateId(), executing: generateId(), answering: generateId() };
        addThinkingStep({ id: stepIds.routing, type: "routing", message: "Understanding your question", status: "active", timestamp: Date.now() });
        await sleep(600);
        updateThinkingStep(stepIds.routing, { status: "done" });
        addThinkingStep({ id: stepIds.sql, type: "sql", message: "Identifying relevant data", status: "active", timestamp: Date.now() });
        await sleep(700);
        updateThinkingStep(stepIds.sql, { status: "done" });
        addThinkingStep({ id: stepIds.executing, type: "executing", message: "Performing calculations", status: "active", timestamp: Date.now() });
        await sleep(500 + Math.random() * 300);
        updateThinkingStep(stepIds.executing, { status: "done" });
        addThinkingStep({ id: stepIds.answering, type: "answering", message: "Drawing conclusions", status: "active", timestamp: Date.now() });
        await sleep(500);
        updateThinkingStep(stepIds.answering, { status: "done" });

        const result: QueryResult = { ...getMockResult(question), question };
        addMessage({
          id: assistantMsgId, role: "assistant", content: result.answer,
          timestamp: new Date(), queryResult: result,
          thinkingSteps: [
            { id: stepIds.routing, type: "routing", message: "Understanding your question", status: "done", timestamp: Date.now() },
            { id: stepIds.sql, type: "sql", message: "Identifying relevant data", status: "done", timestamp: Date.now() },
            { id: stepIds.executing, type: "executing", message: "Performing calculations", status: "done", timestamp: Date.now() },
            { id: stepIds.answering, type: "answering", message: "Drawing conclusions", status: "done", timestamp: Date.now() },
          ],
        });
        clearThinkingSteps();
        setLoading(false);
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
    const source = activeSource ?? "sample";
    if (!activeSource) { setSelectedSource("sample"); setDataSource("sample"); }
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
    <div className="bg-[#2f2f2f] rounded-2xl border border-[#424242] focus-within:border-[#555] transition-colors overflow-hidden">
      <textarea
        ref={textareaRef}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={isLoading}
        rows={1}
        placeholder={placeholder}
        className="w-full resize-none bg-transparent px-5 pt-4 pb-3 text-[15px] text-[#ececec] placeholder-[#6b6b6b] focus:outline-none leading-relaxed"
        style={{ minHeight: 52 }}
      />
      <div className="flex items-center justify-between px-3 py-2">
        <div className="flex items-center gap-1">
          <input ref={fileInputRef} type="file" className="hidden"
            accept={SOURCE_OPTIONS.find((o) => o.id === activeSource)?.accept ?? "*"}
            onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }}
          />
          <button onClick={() => fileInputRef.current?.click()}
            className="w-9 h-9 flex items-center justify-center rounded-xl text-[#6b6b6b] hover:text-white hover:bg-[#424242] transition-colors cursor-pointer" title="Attach file">
            <Plus className="w-5 h-5" />
          </button>
        </div>
        <button onClick={handleSubmit} disabled={!canSubmit}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 ${
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
      <div className="flex h-screen bg-[#212121] overflow-hidden">
        <Sidebar onSuggestion={handleSuggestion} />

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

            {/* Suggestion chips — above input on landing */}
            {activeSource && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1, duration: 0.3 }}
                className="flex flex-wrap gap-2.5 mb-4 justify-center"
              >
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => handleSuggestion(s)}
                    className="px-4 py-2.5 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-[#424242] hover:border-[#555] rounded-xl text-[14px] text-[#b4b4b4] hover:text-white transition-all duration-150 cursor-pointer">
                    {s}
                  </button>
                ))}
              </motion.div>
            )}

            {/* File preview */}
            <AnimatePresence>
              {file && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-3">
                  <div className="flex items-center gap-3 bg-[#2f2f2f] border border-[#424242] rounded-xl px-4 py-3">
                    <FileText className="w-5 h-5 text-[#b4b4b4] flex-shrink-0" />
                    <span className="text-sm text-[#ececec] truncate flex-1">{file.name}</span>
                    <span className="text-xs text-[#8e8e8e]">{(file.size / 1024).toFixed(1)} KB</span>
                    <button onClick={() => { setFile(null); setUploadedFile(null); }} className="rounded-lg p-1.5 hover:bg-[#424242] transition-colors cursor-pointer">
                      <X className="w-4 h-4 text-[#8e8e8e]" />
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Input box — centered */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.4 }}
            >
              {renderInputBox(
                activeSource ? "Ask anything about your data..." : "Select a data source below, then ask..."
              )}
            </motion.div>

            {/* Data source pills — centered */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.25, duration: 0.3 }}
              className="flex items-center justify-center gap-2.5 mt-4 flex-wrap"
            >
              {SOURCE_OPTIONS.map((opt) => {
                const Icon = opt.icon;
                const isSelected = activeSource === opt.id;
                return (
                  <button key={opt.id} onClick={() => handleSelectSource(opt.id)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-[14px] font-medium transition-all duration-150 border cursor-pointer ${
                      isSelected ? "bg-[#3a3a3a] border-[#555] text-white" : "bg-transparent border-[#424242] text-[#6b6b6b] hover:bg-[#2f2f2f] hover:text-[#b4b4b4] hover:border-[#555]"
                    }`}>
                    <Icon className="w-4 h-4" />
                    <span>{opt.label}</span>
                  </button>
                );
              })}
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
    <div className="flex h-screen bg-[#212121] overflow-hidden">
      <Sidebar onSuggestion={handleSuggestion} />

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
        <div className="flex-shrink-0 w-full flex justify-center px-6 pb-5 pt-2">
          <div className="w-full max-w-[680px]">
            {/* Follow-up suggestion chips */}
            {!isLoading && followUps && followUps.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-3"
              >
                <p className="text-[11px] font-medium text-[#6b6b6b] uppercase tracking-wider mb-2 text-center">
                  Suggested next questions
                </p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {followUps.map((q) => (
                    <button key={q} onClick={() => handleQuery(q)}
                      className="px-4 py-2 bg-[#2f2f2f] hover:bg-[#3a3a3a] border border-[#424242] hover:border-[#555] rounded-xl text-[13px] text-[#b4b4b4] hover:text-white transition-all duration-150 cursor-pointer">
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
