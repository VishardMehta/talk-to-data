import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "@/store/useAppStore";
import { getMockResult } from "@/lib/mockData";
import { generateId, sleep } from "@/lib/utils";
import { selectChartType, inferKeys } from "@/utils/chartSelector";
import {
  checkBackendHealth,
  uploadFile,
  streamQuery,
  clearSession,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import { AIChatInput } from "@/components/ui/ai-chat-input";
import ChatMessage from "@/components/ChatMessage";
import { MessageSkeleton } from "@/components/LoadingSkeleton";
import ThinkingDisplay from "@/components/ThinkingDisplay";
import { Sparkles, Zap, ServerOff } from "lucide-react";
import type { ThinkingStep, QueryResult } from "@/types";

const GREETING_CHIPS = [
  "What is total revenue?",
  "Top 3 cities by orders",
  "Revenue by region",
  "Category breakdown",
];

export default function Dashboard() {
  const {
    messages,
    addMessage,
    updateMessage,
    isLoading,
    setLoading,
    dataSource,
    uploadedFile,
    sessionId,
    backendAvailable,
    setBackendAvailable,
    thinkingSteps,
    setThinkingSteps,
    addThinkingStep,
    updateThinkingStep,
    clearThinkingSteps,
  } = useAppStore();

  const [suggestion, setSuggestion] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);

  const isEmpty = messages.length === 0;

  // Check backend health on mount
  useEffect(() => {
    checkBackendHealth().then((ok) => {
      setBackendAvailable(ok);
    });
  }, [setBackendAvailable]);

  // Upload file when backend becomes available
  useEffect(() => {
    if (!backendAvailable || !uploadedFile || dataSource === "sample") return;
    uploadFile(uploadedFile, sessionId).then((res) => {
      if (!res.success) {
        console.warn("File upload failed:", res.message);
      }
    });
  }, [backendAvailable, uploadedFile, sessionId, dataSource]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, thinkingSteps]);

  const handleQuery = useCallback(
    async (question: string) => {
      if (isLoading) return;
      setSuggestion("");
      clearThinkingSteps();

      const userMsgId = generateId();
      addMessage({
        id: userMsgId,
        role: "user",
        content: question,
        timestamp: new Date(),
      });

      const assistantMsgId = generateId();
      setLoading(true);

      if (backendAvailable) {
        // --- Real backend path ---
        const localSteps: ThinkingStep[] = [];

        const addStep = (step: ThinkingStep) => {
          localSteps.push(step);
          addThinkingStep(step);
        };

        const markDone = (id: string) => {
          const s = localSteps.find((s) => s.id === id);
          if (s) s.status = "done";
          updateThinkingStep(id, { status: "done" });
        };

        const abort = streamQuery(
          question,
          sessionId,
          dataSource ?? "sample",
          {
            onThinkingStep: (step) => addStep(step),
            onThinkingUpdate: (id, patch) => {
              const s = localSteps.find((s) => s.id === id);
              if (s) Object.assign(s, patch);
              updateThinkingStep(id, patch);
            },
            onResult: (result: QueryResult) => {
              setLoading(false);
              addMessage({
                id: assistantMsgId,
                role: "assistant",
                content: result.answer,
                timestamp: new Date(),
                queryResult: result,
                thinkingSteps: [...localSteps.map((s) => ({ ...s, status: "done" as const }))],
              });
              clearThinkingSteps();
            },
            onError: (msg) => {
              setLoading(false);
              addMessage({
                id: assistantMsgId,
                role: "assistant",
                content: `Sorry, something went wrong: ${msg}`,
                timestamp: new Date(),
                thinkingSteps: localSteps.map((s) => ({ ...s, status: "done" as const })),
              });
              clearThinkingSteps();
            },
          }
        );
        abortRef.current = abort;
      } else {
        // --- Mock fallback path ---
        const stepIds = {
          routing: generateId(),
          sql: generateId(),
          executing: generateId(),
          answering: generateId(),
        };

        addThinkingStep({
          id: stepIds.routing,
          type: "routing",
          message: "Analyzing your question",
          status: "active",
          timestamp: Date.now(),
        });
        await sleep(500);
        updateThinkingStep(stepIds.routing, { status: "done" });

        addThinkingStep({
          id: stepIds.sql,
          type: "sql",
          message: "Generating SQL query",
          detail: "SELECT ... FROM orders GROUP BY ...",
          status: "active",
          timestamp: Date.now(),
        });
        await sleep(600);
        updateThinkingStep(stepIds.sql, { status: "done" });

        addThinkingStep({
          id: stepIds.executing,
          type: "executing",
          message: "Executing against database",
          status: "active",
          timestamp: Date.now(),
        });
        await sleep(400 + Math.random() * 300);
        updateThinkingStep(stepIds.executing, { status: "done" });

        addThinkingStep({
          id: stepIds.answering,
          type: "answering",
          message: "Formulating insight",
          status: "active",
          timestamp: Date.now(),
        });
        await sleep(400);
        updateThinkingStep(stepIds.answering, { status: "done" });

        // getMockResult now returns QueryResult directly
        const result: QueryResult = {
          ...getMockResult(question),
          question,
        };

        const finalSteps = [
          { id: stepIds.routing, type: "routing" as const, message: "Analyzed intent", status: "done" as const, timestamp: Date.now() },
          { id: stepIds.sql, type: "sql" as const, message: "Generated SQL query", detail: "SELECT region, SUM(revenue) FROM orders GROUP BY region", status: "done" as const, timestamp: Date.now() },
          { id: stepIds.executing, type: "executing" as const, message: "Executed against database", status: "done" as const, timestamp: Date.now() },
          { id: stepIds.answering, type: "answering" as const, message: "Formulated insight", status: "done" as const, timestamp: Date.now() },
        ];

        addMessage({
          id: assistantMsgId,
          role: "assistant",
          content: result.answer,
          timestamp: new Date(),
          queryResult: result,
          thinkingSteps: finalSteps,
        });

        clearThinkingSteps();
        setLoading(false);
      }
    },
    [
      isLoading,
      addMessage,
      setLoading,
      backendAvailable,
      sessionId,
      dataSource,
      addThinkingStep,
      updateThinkingStep,
      clearThinkingSteps,
    ]
  );

  const handleSuggestion = (q: string) => {
    setSuggestion(q);
    setTimeout(() => handleQuery(q), 50);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.();
      if (sessionId) clearSession(sessionId);
    };
  }, [sessionId]);

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar onSuggestion={handleSuggestion} />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 py-3 bg-white/80 backdrop-blur-sm border-b border-gray-100 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-xs font-medium text-gray-500">
              {dataSource === "sample"
                ? "Sample Dataset — E-Commerce (Jan 2024–Mar 2025)"
                : dataSource === "csv"
                ? "CSV File connected"
                : dataSource === "json"
                ? "JSON File connected"
                : "Database connected"}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {!backendAvailable && (
              <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
                <ServerOff className="w-3 h-3" />
                <span>Demo mode (backend offline)</span>
              </div>
            )}
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span>Powered by Groq · Qwen3-32B</span>
            </div>
          </div>
        </header>

        {/* Chat scroll area */}
        <div
          className="flex-1 overflow-y-auto"
          style={{ scrollbarWidth: "thin" }}
        >
          <div className="max-w-3xl mx-auto w-full py-6">
            <AnimatePresence mode="popLayout">
              {isEmpty ? (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -16 }}
                  transition={{ duration: 0.4 }}
                  className="flex flex-col items-center justify-center min-h-[55vh] px-6 text-center"
                >
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center mb-5 shadow-lg shadow-indigo-200">
                    <Sparkles className="w-7 h-7 text-white" />
                  </div>
                  <h1 className="text-2xl font-bold text-gray-900 tracking-tight mb-2">
                    Hello, what do you want to explore?
                  </h1>
                  <p className="text-gray-500 text-sm mb-8 max-w-md">
                    Ask any question about your data. I'll generate insights,
                    charts, and metrics instantly.
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {GREETING_CHIPS.map((chip) => (
                      <motion.button
                        key={chip}
                        whileHover={{ scale: 1.03 }}
                        whileTap={{ scale: 0.97 }}
                        onClick={() => handleSuggestion(chip)}
                        className="px-4 py-2 bg-white border border-gray-200 rounded-full text-sm text-gray-600 font-medium hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50 transition-all duration-150 shadow-sm"
                      >
                        {chip}
                      </motion.button>
                    ))}
                  </div>
                </motion.div>
              ) : (
                <div key="messages" className="space-y-6 pb-2">
                  {messages.map((msg) => (
                    <ChatMessage key={msg.id} message={msg} />
                  ))}

                  {/* Live thinking display during loading */}
                  {isLoading && thinkingSteps.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="px-4"
                    >
                      <div className="flex gap-3">
                        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm">
                          <Sparkles className="w-3.5 h-3.5 text-white" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <ThinkingDisplay
                            steps={thinkingSteps}
                            isThinking={isLoading}
                          />
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {isLoading && thinkingSteps.length === 0 && (
                    <MessageSkeleton />
                  )}

                  <div ref={bottomRef} />
                </div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Input area */}
        <div className="flex-shrink-0 px-6 py-4 bg-white/80 backdrop-blur-sm border-t border-gray-100">
          <AIChatInput
            onSubmit={handleQuery}
            disabled={isLoading}
            initialValue={suggestion}
            key={suggestion}
          />
        </div>
      </div>
    </div>
  );
}
