import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { ArrowUp, Mic, Paperclip } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  onSubmit: (question: string) => void
  disabled?: boolean
  placeholder?: string
  initialValue?: string
  onAttach?: () => void
  onVoice?: () => void
  showToolbar?: boolean
}

export default function ChatInput({
  onSubmit,
  disabled = false,
  placeholder = 'Ask to explore your data...',
  initialValue = '',
  onAttach,
  onVoice,
  showToolbar = true,
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
        animate={canSubmit ? { boxShadow: '0 0 0 1px rgba(94,94,94,0.8), 0 10px 30px rgba(0,0,0,0.32)' } : { boxShadow: '0 4px 20px rgba(0,0,0,0.24)' }}
        transition={{ duration: 0.2 }}
        className="relative bg-[#2f2f2f] rounded-xl border border-[#424242] overflow-hidden"
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          rows={1}
          className="w-full resize-none bg-transparent px-5 pt-4 pb-12 text-[15px] text-[#ececec] placeholder-[#8e8e8e] focus:outline-none leading-relaxed"
          style={{ minHeight: 56 }}
        />

        {/* Bottom bar */}
        <div className="absolute bottom-0 inset-x-0 flex items-center justify-between px-4 py-2.5 border-t border-[#3a3a3a] bg-[#2a2a2a]">
          {showToolbar ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={onAttach}
                disabled={disabled || !onAttach}
                aria-label="Attach file"
                className="w-8 h-8 flex items-center justify-center rounded-lg text-[#8e8e8e] hover:text-white hover:bg-[#424242] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={onVoice}
                disabled={disabled || !onVoice}
                aria-label="Voice input"
                className="w-8 h-8 flex items-center justify-center rounded-lg text-[#8e8e8e] hover:text-white hover:bg-[#424242] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Mic className="w-4 h-4" />
              </button>
              <span className="text-xs text-[#8e8e8e] ml-1">Shift+Enter for new line</span>
            </div>
          ) : (
            <div />
          )}

          <motion.button
            type="button"
            whileTap={{ scale: 0.9 }}
            onClick={submit}
            disabled={!canSubmit}
            className={cn(
              'w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200',
              canSubmit
                ? 'bg-white text-[#212121] hover:bg-gray-200'
                : 'bg-[#424242] text-[#6b6b6b] cursor-not-allowed'
            )}
          >
            <ArrowUp className="w-4 h-4" />
          </motion.button>
        </div>
      </motion.div>
    </div>
  )
}
