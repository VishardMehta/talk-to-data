import { motion } from "framer-motion";
import { User, Sparkles, Copy, ThumbsUp, ThumbsDown, Check } from "lucide-react";
import { useState } from "react";
import type { Message } from "@/store/useAppStore";
import AnswerCard from "./AnswerCard";
import ThinkingDisplay from "./ThinkingDisplay";
import { cn } from "@/lib/utils";

interface ChatMessageProps {
  message: Message;
  onFollowUp?: (q: string) => void;
}

export default function ChatMessage({ message, onFollowUp }: ChatMessageProps) {
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
        className="flex justify-end"
      >
        <div className="flex items-end gap-3 max-w-lg">
          <div className="bg-[#2f2f2f] text-[#ececec] px-5 py-3 rounded-2xl rounded-br-md text-[15px] leading-relaxed border border-[#424242]">
            {message.content}
          </div>
          <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center flex-shrink-0 mb-0.5 border border-[#424242]">
            <User className="w-4 h-4 text-[#b4b4b4]" />
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex gap-4 group"
    >
      {/* Avatar */}
      <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center flex-shrink-0 mt-0.5 border border-[#424242]">
        <Sparkles className="w-4 h-4 text-[#b4b4b4]" />
      </div>

      <div className="flex-1 space-y-4 min-w-0">
        {/* Thinking steps */}
        {message.thinkingSteps && message.thinkingSteps.length > 0 && (
          <ThinkingDisplay steps={message.thinkingSteps} isThinking={false} />
        )}

        {/* Answer */}
        {message.queryResult ? (
          <AnswerCard result={message.queryResult} />
        ) : (
          message.content && (
            <div className="text-[15px] text-[#ececec] leading-[1.75]">
              {message.content}
            </div>
          )
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <span className="text-xs text-[#6b6b6b]">
            {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={copyText}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-[#6b6b6b] hover:text-white hover:bg-[#2f2f2f] transition-colors cursor-pointer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
            <button
              onClick={() => setLiked(liked === "up" ? null : "up")}
              className={cn(
                "p-2 rounded-lg transition-colors cursor-pointer",
                liked === "up" ? "text-emerald-400 bg-emerald-500/10" : "text-[#6b6b6b] hover:text-white hover:bg-[#2f2f2f]"
              )}
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setLiked(liked === "down" ? null : "down")}
              className={cn(
                "p-2 rounded-lg transition-colors cursor-pointer",
                liked === "down" ? "text-red-400 bg-red-500/10" : "text-[#6b6b6b] hover:text-white hover:bg-[#2f2f2f]"
              )}
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
