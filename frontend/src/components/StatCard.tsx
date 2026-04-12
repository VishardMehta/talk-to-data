import { motion } from "framer-motion";

interface StatCardProps {
  label?: string;
  value: string | number;
  subtitle?: string;
}

export default function StatCard({ label, value, subtitle }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-600 via-violet-600 to-purple-700 p-6 text-white shadow-lg shadow-indigo-200"
    >
      {/* Ambient glow */}
      <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-white/10 blur-2xl" />
      <div className="absolute -bottom-6 -left-6 w-24 h-24 rounded-full bg-white/5 blur-xl" />

      <div className="relative text-center">
        {label && (
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-200 mb-3">
            {label}
          </p>
        )}
        <p className="text-4xl font-bold tracking-tight mb-1">{value}</p>
        {subtitle && (
          <p className="text-sm text-indigo-200 mt-2">{subtitle}</p>
        )}
      </div>
    </motion.div>
  );
}
