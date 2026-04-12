import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface StatCardProps {
  label?: string;
  value: string | number;
  subtitle?: string;
  change?: string;
  trend?: "up" | "down" | "neutral";
}

export default function StatCard({ label, value, subtitle, change, trend = "neutral" }: StatCardProps) {
  const trendColors = {
    up: { text: "text-emerald-400", bg: "bg-emerald-500/10", icon: TrendingUp },
    down: { text: "text-red-400", bg: "bg-red-500/10", icon: TrendingDown },
    neutral: { text: "text-[#8e8e8e]", bg: "bg-[#424242]", icon: Minus },
  };

  const t = trendColors[trend];
  const TrendIcon = t.icon;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="relative overflow-hidden rounded-xl bg-[#2f2f2f] border border-[#424242] p-6"
    >
      <div className="space-y-3">
        {label && (
          <p className="text-sm font-medium text-[#8e8e8e] uppercase tracking-wider">
            {label}
          </p>
        )}
        <div className="flex items-end gap-3">
          <p className="text-3xl font-bold text-[#ececec] tracking-tight">{value}</p>
          {change && (
            <div className={`flex items-center gap-1 px-2.5 py-1 rounded-lg ${t.bg}`}>
              <TrendIcon className={`w-3.5 h-3.5 ${t.text}`} />
              <span className={`text-sm font-semibold ${t.text}`}>{change}</span>
            </div>
          )}
        </div>
        {subtitle && (
          <p className="text-sm text-[#8e8e8e]">{subtitle}</p>
        )}
      </div>
    </motion.div>
  );
}
