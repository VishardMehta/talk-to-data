import { motion, AnimatePresence } from "framer-motion";
import { Search, Database, Calculator, Lightbulb, CheckCircle2, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import type { ThinkingStep } from "@/types";
import { cn } from "@/lib/utils";

interface ThinkingDisplayProps {
  steps: ThinkingStep[];
  isThinking: boolean;
}

/* ── Human-readable step mapping ── */
const STEP_CONFIG: Record<
  ThinkingStep["type"],
  { icon: React.ElementType; label: string; tag: "Structured" | "Unstructured"; color: string }
> = {
  routing: {
    icon: Search,
    label: "Understanding your question",
    tag: "Unstructured",
    color: "text-blue-400",
  },
  sql: {
    icon: Database,
    label: "Identifying relevant data",
    tag: "Structured",
    color: "text-cyan-400",
  },
  executing: {
    icon: Calculator,
    label: "Performing calculations",
    tag: "Structured",
    color: "text-amber-400",
  },
  answering: {
    icon: Lightbulb,
    label: "Drawing conclusions",
    tag: "Unstructured",
    color: "text-emerald-400",
  },
  complete: {
    icon: CheckCircle2,
    label: "Complete",
    tag: "Structured",
    color: "text-emerald-400",
  },
  error: {
    icon: AlertCircle,
    label: "Error occurred",
    tag: "Unstructured",
    color: "text-red-400",
  },
};

function PulsingDot() {
  return (
    <span className="flex h-2 w-2 relative">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#b4b4b4] opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
    </span>
  );
}

export default function ThinkingDisplay({ steps, isThinking }: ThinkingDisplayProps) {
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0 && !isThinking) return null;

  const activeStep = steps.find((s) => s.status === "active");
  const doneCount = steps.filter((s) => s.status === "done").length;
  const totalSteps = 4;
  const progress = (doneCount / totalSteps) * 100;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="mb-4"
      >
        {/* Header — toggle */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-3 text-sm text-[#8e8e8e] hover:text-[#b4b4b4] transition-colors cursor-pointer py-1 group"
        >
          {isThinking && <PulsingDot />}
          <span className="font-medium">
            {isThinking
              ? activeStep
                ? STEP_CONFIG[activeStep.type]?.label ?? activeStep.message
                : "Analyzing..."
              : "How this answer was derived"}
          </span>

          {/* Progress bar while thinking */}
          {isThinking && (
            <div className="w-16 h-1 bg-[#424242] rounded-full overflow-hidden flex-shrink-0">
              <motion.div
                className="h-full bg-white/40 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>
          )}

          {!isThinking && (
            expanded
              ? <ChevronUp className="w-4 h-4 opacity-50 group-hover:opacity-100 transition-opacity" />
              : <ChevronDown className="w-4 h-4 opacity-50 group-hover:opacity-100 transition-opacity" />
          )}
        </button>

        {/* Steps panel */}
        <AnimatePresence>
          {(expanded || isThinking) && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="overflow-hidden"
            >
              <div className="mt-2 space-y-1 pl-1 border-l-2 border-[#353535] ml-1">
                {steps.map((step, i) => {
                  const cfg = STEP_CONFIG[step.type];
                  const Icon = cfg.icon;
                  const humanLabel = cfg.label;

                  return (
                    <motion.div
                      key={step.id}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="flex items-center gap-3 py-2 pl-4"
                    >
                      {/* Icon */}
                      {step.status === "active" ? (
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                        >
                          <Icon className={cn("w-4 h-4", cfg.color)} />
                        </motion.div>
                      ) : step.status === "done" ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <Icon className="w-4 h-4 text-[#555]" />
                      )}

                      {/* Label */}
                      <span
                        className={cn(
                          "text-sm flex-1",
                          step.status === "active" ? "text-[#ececec]" : step.status === "done" ? "text-[#8e8e8e]" : "text-[#555]"
                        )}
                      >
                        {humanLabel}
                      </span>

                      {/* Tag */}
                      <span
                        className={cn(
                          "text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded",
                          cfg.tag === "Structured"
                            ? "bg-cyan-500/10 text-cyan-400"
                            : "bg-violet-500/10 text-violet-400"
                        )}
                      >
                        {cfg.tag}
                      </span>

                      {/* Status */}
                      {step.status === "active" && (
                        <div className="flex items-center gap-1">
                          {[0, 1, 2].map((j) => (
                            <motion.span
                              key={j}
                              animate={{ opacity: [0.3, 1, 0.3] }}
                              transition={{ duration: 1.2, repeat: Infinity, delay: j * 0.2 }}
                              className="w-1 h-1 rounded-full bg-[#8e8e8e]"
                            />
                          ))}
                        </div>
                      )}
                    </motion.div>
                  );
                })}

                {/* Pending placeholder */}
                {isThinking &&
                  steps.length < totalSteps &&
                  Array.from({ length: totalSteps - steps.length }).map((_, i) => (
                    <div key={`p-${i}`} className="flex items-center gap-3 py-2 pl-4">
                      <div className="w-4 h-4 rounded bg-[#353535] animate-pulse" />
                      <div className="h-3 w-28 bg-[#353535] rounded animate-pulse" />
                    </div>
                  ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </AnimatePresence>
  );
}
