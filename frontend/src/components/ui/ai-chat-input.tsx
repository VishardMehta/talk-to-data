import * as React from "react";
import { useState, useEffect, useRef } from "react";
import { Lightbulb, Mic, Globe, Paperclip, ArrowUp } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

const DEFAULT_PLACEHOLDERS = [
  "Ask to explore your data...",
  "What is total revenue?",
  "Show me top 5 cities by orders",
  "Revenue trend over time",
  "Compare North vs South region",
  "Category breakdown by sales",
];

const placeholderContainerVariants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.018 } },
  exit: { transition: { staggerChildren: 0.010, staggerDirection: -1 as const } },
};

const letterVariants = {
  initial: { opacity: 0, filter: "blur(8px)", y: 6 },
  animate: {
    opacity: 1,
    filter: "blur(0px)",
    y: 0,
    transition: {
      opacity: { duration: 0.2 },
      filter: { duration: 0.3 },
      y: { type: "spring" as const, stiffness: 80, damping: 20 },
    },
  },
  exit: {
    opacity: 0,
    filter: "blur(8px)",
    y: -6,
    transition: {
      opacity: { duration: 0.15 },
      filter: { duration: 0.25 },
      y: { type: "spring" as const, stiffness: 80, damping: 20 },
    },
  },
};

interface AIChatInputProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
  placeholders?: string[];
  initialValue?: string;
}

const AIChatInput = ({
  onSubmit,
  disabled = false,
  placeholders = DEFAULT_PLACEHOLDERS,
  initialValue = "",
}: AIChatInputProps) => {
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [showPlaceholder, setShowPlaceholder] = useState(true);
  const [isActive, setIsActive] = useState(false);
  const [thinkActive, setThinkActive] = useState(false);
  const [deepSearchActive, setDeepSearchActive] = useState(false);
  const [inputValue, setInputValue] = useState(initialValue);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync initial value
  useEffect(() => {
    if (initialValue) setInputValue(initialValue);
  }, [initialValue]);

  // Cycle placeholder text
  useEffect(() => {
    if (isActive || inputValue) return;
    const interval = setInterval(() => {
      setShowPlaceholder(false);
      setTimeout(() => {
        setPlaceholderIndex((prev) => (prev + 1) % placeholders.length);
        setShowPlaceholder(true);
      }, 350);
    }, 3000);
    return () => clearInterval(interval);
  }, [isActive, inputValue, placeholders.length]);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target as Node)
      ) {
        if (!inputValue) setIsActive(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [inputValue]);

  // Auto-resize
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, [inputValue]);

  const handleActivate = () => setIsActive(true);

  const handleSubmit = () => {
    const q = inputValue.trim();
    if (!q || disabled) return;
    onSubmit(q);
    setInputValue("");
    setIsActive(false);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSubmit = inputValue.trim().length > 0 && !disabled;
  const expanded = isActive || !!inputValue;

  return (
    <div className="w-full max-w-3xl mx-auto" ref={wrapperRef}>
      <motion.div
        animate={
          expanded
            ? {
                boxShadow:
                  "0 8px 40px rgba(99,102,241,0.15), 0 0 0 2px rgba(99,102,241,0.12)",
              }
            : {
                boxShadow: "0 4px 24px rgba(0,0,0,0.06)",
              }
        }
        transition={{ duration: 0.25 }}
        className="relative bg-white rounded-2xl border border-gray-200 overflow-hidden"
        onClick={handleActivate}
      >
        {/* Textarea + animated placeholder */}
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={onKeyDown}
            onFocus={handleActivate}
            disabled={disabled}
            rows={1}
            className="w-full resize-none bg-transparent px-5 pt-4 pb-3 pr-14 text-sm text-gray-800 placeholder-transparent focus:outline-none leading-relaxed"
            style={{ minHeight: 56 }}
            aria-label="Query input"
          />

          {/* Animated placeholder */}
          <div className="absolute left-5 top-0 h-14 flex items-center pointer-events-none">
            <AnimatePresence mode="wait">
              {showPlaceholder && !isActive && !inputValue && (
                <motion.span
                  key={placeholderIndex}
                  className="text-gray-400 text-sm select-none"
                  variants={placeholderContainerVariants}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                  style={{ whiteSpace: "nowrap" }}
                >
                  {placeholders[placeholderIndex].split("").map((char, i) => (
                    <motion.span
                      key={i}
                      variants={letterVariants}
                      style={{ display: "inline-block" }}
                    >
                      {char === " " ? "\u00A0" : char}
                    </motion.span>
                  ))}
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 bg-gray-50/40">
          <div className="flex items-center gap-1">
            <button
              type="button"
              tabIndex={-1}
              className="w-8 h-8 flex items-center justify-center rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              title="Attach file"
            >
              <Paperclip className="w-4 h-4" />
            </button>
            <button
              type="button"
              tabIndex={-1}
              className="w-8 h-8 flex items-center justify-center rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              title="Voice input"
            >
              <Mic className="w-4 h-4" />
            </button>

            {/* Expanded controls */}
            <AnimatePresence>
              {expanded && (
                <motion.div
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -8 }}
                  transition={{ duration: 0.2 }}
                  className="flex items-center gap-2 ml-1"
                >
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setThinkActive((a) => !a);
                    }}
                    className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-all group ${
                      thinkActive
                        ? "bg-blue-600/10 border border-blue-400/40 text-blue-700"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                    }`}
                  >
                    <Lightbulb
                      className={`w-3.5 h-3.5 transition-all ${
                        thinkActive
                          ? "fill-yellow-300 text-yellow-500"
                          : "group-hover:text-yellow-500"
                      }`}
                    />
                    Think
                  </button>

                  <motion.button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeepSearchActive((a) => !a);
                    }}
                    initial={false}
                    animate={{ width: deepSearchActive ? 110 : 34 }}
                    transition={{ type: "spring", stiffness: 200, damping: 25 }}
                    className={`flex items-center gap-1.5 py-1.5 rounded-full text-xs font-medium overflow-hidden whitespace-nowrap transition-colors ${
                      deepSearchActive
                        ? "bg-blue-600/10 border border-blue-400/40 text-blue-700 px-3"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200 justify-center"
                    }`}
                  >
                    <Globe className="w-3.5 h-3.5 flex-shrink-0" />
                    <motion.span
                      animate={{ opacity: deepSearchActive ? 1 : 0 }}
                      transition={{ duration: 0.15 }}
                    >
                      Deep Search
                    </motion.span>
                  </motion.button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <motion.button
            whileTap={{ scale: 0.88 }}
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={`w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200 ${
              canSubmit
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-200 hover:bg-indigo-700"
                : "bg-gray-100 text-gray-300 cursor-not-allowed"
            }`}
          >
            <ArrowUp className="w-4 h-4" />
          </motion.button>
        </div>
      </motion.div>

      <p className="text-center text-xs text-gray-400 mt-2">
        Press Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
};

export { AIChatInput };
