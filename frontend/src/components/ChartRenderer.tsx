import { motion } from "framer-motion";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { ChartType } from "@/types";
import StatCard from "./StatCard";

const PALETTE = ["#7c3aed", "#a78bfa", "#4f46e5", "#6d28d9", "#8b5cf6", "#06b6d4", "#10b981"];

const tooltipStyle = {
  contentStyle: {
    borderRadius: 12,
    border: "1px solid #e5e7eb",
    boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
    fontSize: 12,
    fontFamily: "Inter, sans-serif",
    background: "#fff",
  },
  labelStyle: { fontWeight: 600, color: "#111827" },
  itemStyle: { color: "#6366f1" },
};

interface ChartRendererProps {
  chartType: ChartType;
  data: Record<string, unknown>[];
  xKey?: string;
  yKey?: string;
  nameKey?: string;
  valueKey?: string;
  title?: string;
  columns?: string[];
  rows?: unknown[][];
}

export default function ChartRenderer({
  chartType,
  data,
  xKey = "",
  yKey = "",
  nameKey = "",
  valueKey = "",
  title,
  columns,
  rows,
}: ChartRendererProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut", delay: 0.1 }}
      className="bg-gray-50/80 rounded-xl p-4 mt-4 border border-gray-100"
    >
      {title && (
        <p className="text-xs font-semibold text-gray-700 mb-3 tracking-wide uppercase">
          {title}
        </p>
      )}

      {chartType === "stat_card" && data.length > 0 && (
        <StatCard
          label={xKey || Object.keys(data[0])[0]}
          value={String(data[0][yKey] ?? data[0][valueKey] ?? Object.values(data[0])[0])}
        />
      )}

      {chartType === "line" && (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ top: 4, right: 16, left: -20, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} opacity={0.6} />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip {...tooltipStyle} />
            <Line
              type="monotone"
              dataKey={yKey}
              stroke="#7c3aed"
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 6, fill: "#7c3aed", strokeWidth: 2, stroke: "#fff" }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {(chartType === "bar" || chartType === "histogram") && (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 4, right: 16, left: -20, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} opacity={0.4} />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey={yKey} radius={[6, 6, 0, 0]}>
              {data.map((_entry, idx) => (
                <Cell
                  key={idx}
                  fill={PALETTE[idx % PALETTE.length]}
                  opacity={0.9}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      {chartType === "pie" && (
        <div className="flex items-center gap-6">
          <ResponsiveContainer width={220} height={220}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                dataKey={valueKey || yKey}
                nameKey={nameKey || xKey}
                paddingAngle={3}
                strokeWidth={0}
              >
                {data.map((_entry, idx) => (
                  <Cell key={idx} fill={PALETTE[idx % PALETTE.length]} />
                ))}
              </Pie>
              <Tooltip {...tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>

          <div className="flex-1 space-y-2">
            {data.map((item, idx) => {
              const name = String(item[nameKey] ?? item[xKey] ?? "");
              const val = Number(item[valueKey] ?? item[yKey] ?? 0);
              const total = data.reduce((s, d) => s + Number(d[valueKey] ?? d[yKey] ?? 0), 0);
              const pct = total > 0 ? ((val / total) * 100).toFixed(0) : "0";
              return (
                <div key={idx} className="flex items-center gap-2.5">
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: PALETTE[idx % PALETTE.length] }}
                  />
                  <span className="text-xs text-gray-600 flex-1 truncate">{name}</span>
                  <span className="text-xs font-semibold text-gray-800">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {chartType === "table" && (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="bg-gray-100/80 border-b border-gray-200">
                {(columns || (data[0] ? Object.keys(data[0]) : [])).map((col) => (
                  <th
                    key={col}
                    className="px-4 py-2.5 font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(rows
                ? rows
                : data.map((row) => Object.values(row))
              ).map((row: unknown, i) => (
                <tr
                  key={i}
                  className={i % 2 === 0 ? "bg-white" : "bg-gray-50/60"}
                >
                  {(row as unknown[]).map((cell, j) => (
                    <td key={j} className="px-4 py-2.5 text-gray-700 whitespace-nowrap">
                      {String(cell ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </motion.div>
  );
}
