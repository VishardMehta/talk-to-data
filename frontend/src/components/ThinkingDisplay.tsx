import { motion, AnimatePresence } from "framer-motion";
import { Brain, Database, Zap, MessageSquare, CheckCircle2, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import type { ThinkingStep } from "@/types";
import { cn } from "@/lib/utils";

interface ThinkingDisplayProps {
  steps: ThinkingStep[];
  isThinking: boolean;
}

const STEP_CONFIG: Record<
  ThinkingStep["type"],
  { icon: React.ElementType; label: string; color: string; bg: string }
> = {
  routing: {
    icon: Brain,
    label: "Analyzing intent",
    color: "text-violet-600",
    bg: "bg-violet-50",
  },
  sql: {
    icon: Database,
    label: "Generating SQL",
    color: "text-blue-600",
    bg: "bg-blue-50",
  },
  executing: {
    icon: Zap,
    label: "Executing query",
    color: "text-amber-600",
    bg: "bg-amber-50",
  },
  answering: {
    icon: MessageSquare,
    label: "Formulating insight",
    color: "text-emerald-600",
    bg: "bg-emerald-50",
  },
  complete: {
    icon: CheckCircle2,
    label: "Complete",
    color: "text-emerald-600",
    bg: "bg-emerald-50",
  },
  error: {
    icon: AlertCircle,
    label: "Error",
    color: "text-red-500",
    bg: "bg-red-50",
  },
};

function PulsingDot() {
  return (
    <span className="flex h-2 w-2 relative">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500" />
    </span>
  );
}

export default function ThinkingDisplay({ steps, isThinking }: ThinkingDisplayProps) {
  const [expanded, setExpanded] = useState(true);

  if (steps.length === 0 && !isThinking) return null;

  const activeStep = steps.find((s) => s.status === "active");
  const doneCount = steps.filter((s) => s.status === "done").length;
  const totalSteps = 4;
  const progress = (doneCount / totalSteps) * 100;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 8, height: 0 }}
        animate={{ opacity: 1, y: 0, height: "auto" }}
        exit={{ opacity: 0, y: -8, height: 0 }}
        transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        className="mx-4 mb-3"
      >
        <div className="bg-gradient-to-r from-indigo-50 via-violet-50 to-purple-50 border border-indigo-100/80 rounded-2xl overflow-hidden">
          {/* Header */}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/40 transition-colors"
          >
            <div className="flex items-center gap-2 flex-1 min-w-0">
              {isThinking && <PulsingDot />}
              <span className="text-xs font-semibold text-indigo-700 truncate">
                {isThinking
                  ? activeStep
                    ? `${activeStep.message}...`
                    : "Thinking..."
                  : `Completed in ${steps.length} steps`}
              </span>
            </div>

            {/* Progress bar */}
            {isThinking && (
              <div className="w-20 h-1 bg-indigo-100 rounded-full overflow-hidden flex-shrink-0">
                <motion.div
                  className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.4 }}
                />
              </div>
            )}

            {expanded ? (
              <ChevronUp className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
            )}
          </button>

          {/* Steps */}
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4 space-y-2.5">
                  {steps.map((step, i) => {
                    const cfg = STEP_CONFIG[step.type];
                    const Icon = cfg.icon;
                    return (
                      <motion.div
                        key={step.id}
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className={cn(
                          "flex gap-3 rounded-xl p-3 transition-all",
                          step.status === "active"
                            ? "bg-white shadow-sm border border-indigo-100"
                            : step.status === "done"
                            ? "bg-white/60"
                            : "bg-white/30"
                        )}
                      >
                        <div
                          className={cn(
                            "w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0",
                            step.status === "done"
                              ? "bg-emerald-100"
                              : step.status === "active"
                              ? cfg.bg
                              : "bg-gray-100"
                          )}
                        >
                          {step.status === "active" ? (
                            <motion.div
                              animate={{ rotate: 360 }}
                              transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                            >
                              <Icon
                                className={cn(
                                  "w-3.5 h-3.5",
                                  step.status === "active" ? cfg.color : "text-gray-400"
                                )}
                              />
                            </motion.div>
                          ) : step.status === "done" ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                          ) : (
                            <Icon className="w-3.5 h-3.5 text-gray-300" />
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          <p
                            className={cn(
                              "text-xs font-medium",
                              step.status === "active"
                                ? "text-gray-800"
                                : step.status === "done"
                                ? "text-gray-600"
                                : "text-gray-400"
                            )}
                          >
                            {step.message}
                          </p>
                          {step.detail && step.status !== "pending" && (
                            <p className="text-xs text-gray-400 mt-0.5 font-mono truncate">
                              {step.detail}
                            </p>
                          )}
                        </div>

                        {step.status === "done" && (
                          <span className="text-xs text-emerald-500 font-medium flex-shrink-0">
                            done
                          </span>
                        )}
                        {step.status === "active" && (
                          <div className="flex items-center gap-1 flex-shrink-0">
                            {[0, 1, 2].map((i) => (
                              <motion.span
                                key={i}
                                animate={{ opacity: [0.3, 1, 0.3] }}
                                transition={{
                                  duration: 1.2,
                                  repeat: Infinity,
                                  delay: i * 0.2,
                                }}
                                className="w-1 h-1 rounded-full bg-indigo-400"
                              />
                            ))}
                          </div>
                        )}
                      </motion.div>
                    );
                  })}

                  {/* Pending placeholder steps */}
                  {isThinking &&
                    steps.length < totalSteps &&
                    Array.from({ length: totalSteps - steps.length }).map((_, i) => (
                      <div
                        key={`pending-${i}`}
                        className="flex gap-3 rounded-xl p-3 bg-white/20"
                      >
                        <div className="w-7 h-7 rounded-lg bg-gray-100/60 flex-shrink-0" />
                        <div className="flex-1 space-y-1.5">
                          <div className="h-2 w-24 bg-gray-200/60 rounded-full" />
                        </div>
                      </div>
                    ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
