import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import type { MetricCard } from '@/store/useAppStore'
import { cn } from '@/lib/utils'

interface MetricCardsProps {
  metrics: MetricCard[]
}

const trendConfig = {
  up: {
    icon: TrendingUp,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
    border: 'border-emerald-100',
    badge: 'bg-emerald-50 text-emerald-700',
  },
  down: {
    icon: TrendingDown,
    color: 'text-red-500',
    bg: 'bg-red-50',
    border: 'border-red-100',
    badge: 'bg-red-50 text-red-600',
  },
  neutral: {
    icon: Minus,
    color: 'text-gray-400',
    bg: 'bg-gray-50',
    border: 'border-gray-100',
    badge: 'bg-gray-100 text-gray-600',
  },
}

export default function MetricCards({ metrics }: MetricCardsProps) {
  const cols = metrics.length === 1 ? 1 : metrics.length === 2 ? 2 : metrics.length === 3 ? 3 : 4

  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(${Math.min(cols, 4)}, minmax(0, 1fr))` }}
    >
      {metrics.map((metric, i) => {
        const trend: 'up' | 'down' | 'neutral' = metric.trend ?? 'neutral'
        const cfg = trendConfig[trend]
        const Icon = cfg.icon

        return (
          <motion.div
            key={metric.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06, duration: 0.3, ease: 'easeOut' }}
            className={cn(
              'relative bg-white rounded-2xl border p-4 overflow-hidden',
              'shadow-sm hover:shadow-md transition-shadow duration-200',
              cfg.border
            )}
          >
            {/* Subtle background glow */}
            <div className={cn('absolute inset-0 opacity-30', cfg.bg)} />

            <div className="relative">
              <div className="flex items-start justify-between mb-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  {metric.label}
                </p>
                <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center', cfg.bg)}>
                  <Icon className={cn('w-3.5 h-3.5', cfg.color)} />
                </div>
              </div>

              <p className="text-2xl font-bold text-gray-900 tracking-tight mb-2">
                {metric.value}
              </p>

              {metric.change && (
                <div className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold',
                  cfg.badge
                )}>
                  <Icon className="w-3 h-3" />
                  {metric.change}
                </div>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}
