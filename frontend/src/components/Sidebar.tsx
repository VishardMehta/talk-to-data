import { motion, AnimatePresence } from 'framer-motion'
import {
  BarChart3, Clock, Sparkles, ChevronLeft, ChevronRight,
  RotateCcw, Database, Upload, Layers,
} from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { cn } from '@/lib/utils'

const SUGGESTIONS = [
  'What is total revenue?',
  'Top 3 cities by orders',
  'Revenue by region',
  'Show revenue trend',
  'Category breakdown',
  'Compare North vs South',
]

interface SidebarProps {
  onSuggestion: (q: string) => void
}

const sourceLabel: Record<string, { icon: React.ElementType; label: string }> = {
  csv: { icon: Upload, label: 'CSV File' },
  database: { icon: Database, label: 'Database' },
  sample: { icon: Layers, label: 'Sample Dataset' },
}

export default function Sidebar({ onSuggestion }: SidebarProps) {
  const { sidebarCollapsed, toggleSidebar, messages, clearChat, dataSource } = useAppStore()

  const historyItems = messages
    .filter((m: { role: string }) => m.role === 'user')
    .slice(-8)
    .reverse()

  const src = dataSource ? sourceLabel[dataSource] : null

  return (
    <motion.aside
      animate={{ width: sidebarCollapsed ? 64 : 260 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="relative flex-shrink-0 h-full bg-white border-r border-gray-100 flex flex-col overflow-hidden"
    >
      {/* Toggle button */}
      <button
        onClick={toggleSidebar}
        className="absolute -right-3 top-6 z-10 w-6 h-6 rounded-full bg-white border border-gray-200 flex items-center justify-center shadow-sm hover:shadow-md transition-shadow"
      >
        {sidebarCollapsed
          ? <ChevronRight className="w-3 h-3 text-gray-500" />
          : <ChevronLeft className="w-3 h-3 text-gray-500" />
        }
      </button>

      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-gray-100">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center flex-shrink-0 shadow-sm">
          <BarChart3 className="w-4 h-4 text-white" />
        </div>
        <AnimatePresence>
          {!sidebarCollapsed && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.2 }}
            >
              <p className="font-bold text-sm text-gray-900 tracking-tight">DataLens</p>
              <p className="text-xs text-gray-400">AI Analytics</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Data source badge */}
      <AnimatePresence>
        {!sidebarCollapsed && src && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mx-3 mt-3"
          >
            <div className="flex items-center gap-2 px-3 py-2 bg-indigo-50 rounded-xl border border-indigo-100">
              <src.icon className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
              <span className="text-xs font-medium text-indigo-700 truncate">{src.label}</span>
              <div className="ml-auto w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 overflow-y-auto py-4 space-y-6">
        {/* Try asking */}
        <div>
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                <div className="flex items-center gap-2 px-4 mb-2">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Try asking
                  </span>
                </div>
                <div className="space-y-0.5 px-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => onSuggestion(s)}
                      className="w-full text-left px-3 py-2 rounded-xl text-xs text-gray-600 hover:bg-indigo-50 hover:text-indigo-700 transition-colors duration-150 font-medium truncate"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {sidebarCollapsed && (
            <div className="flex justify-center">
              <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              </div>
            </div>
          )}
        </div>

        {/* History */}
        {historyItems.length > 0 && (
          <div>
            <AnimatePresence>
              {!sidebarCollapsed && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                >
                  <div className="flex items-center gap-2 px-4 mb-2">
                    <Clock className="w-3.5 h-3.5 text-gray-400" />
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      History
                    </span>
                  </div>
                  <div className="space-y-0.5 px-2">
                    {historyItems.map((m: { id: string; content: string }) => (
                      <button
                        key={m.id}
                        onClick={() => onSuggestion(m.content)}
                        className="w-full text-left px-3 py-2 rounded-xl text-xs text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors duration-150 truncate"
                      >
                        {m.content}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {sidebarCollapsed && (
              <div className="flex justify-center">
                <div className="w-8 h-8 rounded-xl bg-gray-50 flex items-center justify-center">
                  <Clock className="w-3.5 h-3.5 text-gray-400" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom actions */}
      <div className="border-t border-gray-100 p-3 space-y-1">
        <button
          onClick={clearChat}
          className={cn(
            'flex items-center gap-2.5 w-full px-3 py-2 rounded-xl text-xs font-medium text-gray-500 hover:bg-red-50 hover:text-red-600 transition-colors duration-150',
            sidebarCollapsed && 'justify-center'
          )}
        >
          <RotateCcw className="w-3.5 h-3.5 flex-shrink-0" />
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                Clear conversation
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </motion.aside>
  )
}
