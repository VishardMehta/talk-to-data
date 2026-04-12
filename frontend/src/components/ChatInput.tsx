import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { ArrowUp, Mic, Paperclip } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  onSubmit: (question: string) => void
  disabled?: boolean
  placeholder?: string
  initialValue?: string
}

export default function ChatInput({
  onSubmit,
  disabled = false,
  placeholder = 'Ask to explore your data...',
  initialValue = '',
}: ChatInputProps) {
  const [value, setValue] = useState(initialValue)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-fill from suggestion
  useEffect(() => {
    if (initialValue) {
      setValue(initialValue)
      textareaRef.current?.focus()
    }
  }, [initialValue])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`
  }, [value])

  const submit = () => {
    const q = value.trim()
    if (!q || disabled) return
    onSubmit(q)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const canSubmit = value.trim().length > 0 && !disabled

  return (
    <div className="w-full max-w-3xl mx-auto">
      <motion.div
        initial={false}
        animate={canSubmit ? { boxShadow: '0 0 0 2px rgba(99,102,241,0.2), 0 8px 32px rgba(99,102,241,0.08)' } : { boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}
        transition={{ duration: 0.2 }}
        className="relative bg-white rounded-2xl border border-gray-200 overflow-hidden"
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          rows={1}
          className="w-full resize-none bg-transparent px-5 pt-4 pb-12 text-sm text-gray-800 placeholder-gray-400 focus:outline-none leading-relaxed"
          style={{ minHeight: 56 }}
        />

        {/* Bottom bar */}
        <div className="absolute bottom-0 inset-x-0 flex items-center justify-between px-4 py-2.5 border-t border-gray-100 bg-gray-50/50">
          <div className="flex items-center gap-1">
            <button className="w-8 h-8 flex items-center justify-center rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
              <Paperclip className="w-4 h-4" />
            </button>
            <button className="w-8 h-8 flex items-center justify-center rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
              <Mic className="w-4 h-4" />
            </button>
            <span className="text-xs text-gray-300 ml-1">Shift+Enter for new line</span>
          </div>

          <motion.button
            whileTap={{ scale: 0.9 }}
            onClick={submit}
            disabled={!canSubmit}
            className={cn(
              'w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200',
              canSubmit
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200 hover:bg-indigo-700'
                : 'bg-gray-100 text-gray-300 cursor-not-allowed'
            )}
          >
            <ArrowUp className="w-4 h-4" />
          </motion.button>
        </div>
      </motion.div>
    </div>
  )
}
