import { motion } from 'framer-motion'
import { Sparkles } from 'lucide-react'

function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div className={`rounded-lg bg-[#424242] animate-pulse ${className}`} />
  )
}

export function MessageSkeleton() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-4"
    >
      <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex-shrink-0 flex items-center justify-center border border-[#424242]">
        <Sparkles className="w-4 h-4 text-[#b4b4b4]" />
      </div>

      <div className="flex-1 space-y-4 pt-1">
        {/* Typing dots */}
        <div className="flex items-center gap-2 h-8">
          <div className="flex items-center gap-1.5 bg-[#2f2f2f] border border-[#424242] rounded-xl px-5 py-3">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        </div>

        {/* Metric skeletons */}
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="bg-[#2f2f2f] border border-[#424242] rounded-xl p-5 space-y-3">
              <SkeletonBlock className="h-3 w-16" />
              <SkeletonBlock className="h-7 w-24" />
              <SkeletonBlock className="h-3 w-12" />
            </div>
          ))}
        </div>

        {/* Chart skeleton */}
        <div className="bg-[#2f2f2f] border border-[#424242] rounded-xl p-5 space-y-3">
          <SkeletonBlock className="h-4 w-32" />
          <SkeletonBlock className="h-44 w-full" />
        </div>
      </div>
    </motion.div>
  )
}

export default MessageSkeleton
