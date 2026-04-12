import { motion } from "framer-motion";
import { User, Sparkles, Copy, ThumbsUp, ThumbsDown, Check } from "lucide-react";
import { useState } from "react";
import type { Message } from "@/store/useAppStore";
import AnswerCard from "./AnswerCard";
import ThinkingDisplay from "./ThinkingDisplay";
import { cn } from "@/lib/utils";

interface ChatMessageProps {
  message: Message;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const [liked, setLiked] = useState<"up" | "down" | null>(null);

  const isUser = message.role === "user";

  const copyText = () => {
    const text = message.queryResult?.answer ?? message.content;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="flex justify-end px-4"
      >
        <div className="flex items-end gap-2 max-w-md">
          <div className="bg-gradient-to-br from-indigo-600 to-violet-600 text-white px-4 py-2.5 rounded-2xl rounded-br-sm text-sm font-medium shadow-sm shadow-indigo-100">
            {message.content}
          </div>
          <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0 mb-0.5">
            <User className="w-3.5 h-3.5 text-gray-600" />
          </div>
        </div>
      </motion.div>
    );
  }

  // Assistant message
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex gap-3 px-4 group"
    >
      {/* Avatar */}
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm">
        <Sparkles className="w-3.5 h-3.5 text-white" />
      </div>

      <div className="flex-1 space-y-3 min-w-0">
        {/* Thinking steps (collapsed once answer is shown) */}
        {message.thinkingSteps && message.thinkingSteps.length > 0 && (
          <ThinkingDisplay steps={message.thinkingSteps} isThinking={false} />
        )}

        {/* Answer card (rich result) */}
        {message.queryResult ? (
          <AnswerCard result={message.queryResult} />
        ) : (
          /* Plain text fallback */
          message.content && (
            <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-700 leading-relaxed shadow-sm">
              {message.content}
            </div>
          )
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <span className="text-xs text-gray-400">
            {message.timestamp.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={copyText}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            >
              {copied ? (
                <Check className="w-3 h-3 text-emerald-500" />
              ) : (
                <Copy className="w-3 h-3" />
              )}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
            <button
              onClick={() => setLiked(liked === "up" ? null : "up")}
              className={cn(
                "p-1.5 rounded-lg transition-colors",
                liked === "up"
                  ? "text-emerald-600 bg-emerald-50"
                  : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              )}
            >
              <ThumbsUp className="w-3 h-3" />
            </button>
            <button
              onClick={() => setLiked(liked === "down" ? null : "down")}
              className={cn(
                "p-1.5 rounded-lg transition-colors",
                liked === "down"
                  ? "text-red-500 bg-red-50"
                  : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              )}
            >
              <ThumbsDown className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
