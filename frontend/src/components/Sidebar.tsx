import { motion, AnimatePresence } from 'framer-motion'
import {
  Clock, RotateCcw, Database, Upload, Layers, FileJson, Plus,
  PanelLeftClose, PanelLeft,
} from 'lucide-react'
import { useAppStore } from '@/store/useAppStore'
import { cn } from '@/lib/utils'

interface SidebarProps {
  onSuggestion: (q: string) => void
}

const sourceLabel: Record<string, { icon: React.ElementType; label: string }> = {
  csv: { icon: Upload, label: 'CSV File' },
  database: { icon: Database, label: 'Database' },
  json: { icon: FileJson, label: 'JSON File' },
  sample: { icon: Layers, label: 'Sample Dataset' },
}

export default function Sidebar({ onSuggestion }: SidebarProps) {
  const { sidebarCollapsed, toggleSidebar, messages, clearChat, dataSource } = useAppStore()

  const historyItems = messages
    .filter((m: { role: string }) => m.role === 'user')
    .slice(-10)
    .reverse()

  const src = dataSource ? sourceLabel[dataSource] : null

  return (
    <>
      {/* Toggle button — visible when sidebar is collapsed */}
      {sidebarCollapsed && (
        <button
          onClick={toggleSidebar}
          className="fixed left-4 top-4 z-50 w-9 h-9 rounded-lg flex items-center justify-center text-[#b4b4b4] hover:text-white hover:bg-[#2f2f2f] transition-colors cursor-pointer"
          title="Open sidebar"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
      )}

      <motion.aside
        animate={{ width: sidebarCollapsed ? 0 : 280 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="relative flex-shrink-0 h-full bg-[#171717] flex flex-col overflow-hidden"
      >
        {/* Top bar — toggle + title */}
        <div className="flex items-center gap-3 px-4 pt-4 pb-3">
          <button
            onClick={toggleSidebar}
            className="w-9 h-9 rounded-lg flex items-center justify-center text-[#b4b4b4] hover:text-white hover:bg-[#2f2f2f] transition-colors cursor-pointer flex-shrink-0"
            title="Close sidebar"
          >
            <PanelLeftClose className="w-5 h-5" />
          </button>
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.2 }}
              >
                <p className="font-semibold text-[15px] text-[#ececec] tracking-tight">DataLens</p>
                <p className="text-xs text-[#8e8e8e]">AI Analytics</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* New Chat button */}
        <AnimatePresence>
          {!sidebarCollapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="px-3 pb-2"
            >
              <button
                onClick={clearChat}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm text-[#b4b4b4] hover:bg-[#2f2f2f] hover:text-white transition-colors cursor-pointer"
              >
                <Plus className="w-4 h-4" />
                <span>New chat</span>
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Divider */}
        <div className="mx-4 border-t border-[#2a2a2a]" />

        {/* Data source badge */}
        <AnimatePresence>
          {!sidebarCollapsed && src && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mx-3 mt-3"
            >
              <div className="flex items-center gap-3 px-4 py-3 bg-[#2f2f2f] rounded-lg">
                <src.icon className="w-4 h-4 text-[#b4b4b4] flex-shrink-0" />
                <span className="text-sm text-[#ececec] truncate">{src.label}</span>
                <div className="ml-auto w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Scrollable area — history */}
        <div className="flex-1 overflow-y-auto py-3 space-y-1 px-3">
          {historyItems.length > 0 && (
            <AnimatePresence>
              {!sidebarCollapsed && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                >
                  <div className="flex items-center gap-2 px-3 mb-2">
                    <Clock className="w-3.5 h-3.5 text-[#8e8e8e]" />
                    <span className="text-xs font-medium text-[#8e8e8e] uppercase tracking-wider">
                      Recent
                    </span>
                  </div>
                  <div className="space-y-0.5">
                    {historyItems.map((m: { id: string; content: string }) => (
                      <button
                        key={m.id}
                        onClick={() => onSuggestion(m.content)}
                        className="w-full text-left px-4 py-3 rounded-lg text-sm text-[#b4b4b4] hover:bg-[#2f2f2f] hover:text-white transition-colors duration-150 truncate cursor-pointer"
                      >
                        {m.content}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          )}
        </div>

        {/* Bottom */}
        <div className="border-t border-[#2a2a2a] p-3">
          <button
            onClick={clearChat}
            className={cn(
              'flex items-center gap-3 w-full px-4 py-3 rounded-lg text-sm text-[#8e8e8e] hover:bg-[#2f2f2f] hover:text-red-400 transition-colors duration-150 cursor-pointer',
              sidebarCollapsed && 'justify-center'
            )}
          >
            <RotateCcw className="w-4 h-4 flex-shrink-0" />
            <AnimatePresence>
              {!sidebarCollapsed && (
                <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  Clear conversation
                </motion.span>
              )}
            </AnimatePresence>
          </button>
        </div>
      </motion.aside>
    </>
  )
}
