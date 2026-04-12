import { motion } from 'framer-motion'

function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div className={`shimmer rounded-xl bg-gray-100 ${className}`} />
  )
}

export function MessageSkeleton() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3 px-4"
    >
      {/* Avatar */}
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex-shrink-0 flex items-center justify-center">
        <span className="text-white text-xs font-bold">AI</span>
      </div>

      <div className="flex-1 space-y-4 pt-1">
        {/* Typing dots */}
        <div className="flex items-center gap-2 h-7">
          <div className="flex items-center gap-1 bg-white border border-gray-100 rounded-2xl px-4 py-2 shadow-sm">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        </div>

        {/* Metric skeletons */}
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="bg-white border border-gray-100 rounded-2xl p-4 space-y-3">
              <SkeletonBlock className="h-3 w-16" />
              <SkeletonBlock className="h-7 w-24" />
              <SkeletonBlock className="h-3 w-12" />
            </div>
          ))}
        </div>

        {/* Chart skeleton */}
        <div className="bg-white border border-gray-100 rounded-2xl p-5 space-y-3">
          <SkeletonBlock className="h-4 w-32" />
          <SkeletonBlock className="h-44 w-full" />
        </div>
      </div>
    </motion.div>
  )
}

export default MessageSkeleton
