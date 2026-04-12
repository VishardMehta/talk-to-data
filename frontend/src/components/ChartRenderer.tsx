import { motion } from "framer-motion";
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import type { ChartType } from "@/types";
import StatCard from "./StatCard";

const PALETTE = ["#60a5fa", "#818cf8", "#34d399", "#fbbf24", "#f472b6", "#22d3ee", "#a78bfa"];

const tooltipStyle = {
  contentStyle: {
    borderRadius: 10,
    border: "1px solid #424242",
    boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
    fontSize: 13,
    fontFamily: "Inter, sans-serif",
    background: "#2f2f2f",
    color: "#ececec",
  },
  labelStyle: { fontWeight: 600, color: "#ececec" },
  itemStyle: { color: "#b4b4b4" },
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
  chartType, data, xKey = "", yKey = "", nameKey = "", valueKey = "", title, columns, rows,
}: ChartRendererProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut", delay: 0.1 }}
    >
      {title && (
        <p className="text-sm font-medium text-[#8e8e8e] mb-3">{title}</p>
      )}

      {chartType === "stat_card" && data.length > 0 && (
        <StatCard
          label={xKey || Object.keys(data[0])[0]}
          value={String(data[0][yKey] ?? data[0][valueKey] ?? Object.values(data[0])[0])}
          change="+12.4%"
          trend="up"
          subtitle="vs. previous quarter"
        />
      )}

      {chartType === "line" && (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 8, right: 16, left: -16, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#424242" vertical={false} opacity={0.4} />
            <XAxis dataKey={xKey} tick={{ fontSize: 12, fill: "#8e8e8e" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 12, fill: "#8e8e8e" }} axisLine={false} tickLine={false} />
            <Tooltip {...tooltipStyle} />
            <Line
              type="monotone" dataKey={yKey} stroke="#60a5fa" strokeWidth={2.5}
              dot={false} activeDot={{ r: 6, fill: "#60a5fa", strokeWidth: 2, stroke: "#2f2f2f" }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {(chartType === "bar" || chartType === "histogram") && (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data} margin={{ top: 8, right: 16, left: -16, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#424242" vertical={false} opacity={0.3} />
            <XAxis dataKey={xKey} tick={{ fontSize: 12, fill: "#8e8e8e" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 12, fill: "#8e8e8e" }} axisLine={false} tickLine={false} />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey={yKey} radius={[6, 6, 0, 0]}>
              {data.map((_entry, idx) => (
                <Cell key={idx} fill={PALETTE[idx % PALETTE.length]} opacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      {chartType === "pie" && (
        <div className="flex items-center gap-8">
          <ResponsiveContainer width={220} height={220}>
            <PieChart>
              <Pie
                data={data} cx="50%" cy="50%" innerRadius={60} outerRadius={90}
                dataKey={valueKey || yKey} nameKey={nameKey || xKey}
                paddingAngle={3} strokeWidth={0}
              >
                {data.map((_entry, idx) => (
                  <Cell key={idx} fill={PALETTE[idx % PALETTE.length]} />
                ))}
              </Pie>
              <Tooltip {...tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>

          <div className="flex-1 space-y-3">
            {data.map((item, idx) => {
              const name = String(item[nameKey] ?? item[xKey] ?? "");
              const val = Number(item[valueKey] ?? item[yKey] ?? 0);
              const total = data.reduce((s, d) => s + Number(d[valueKey] ?? d[yKey] ?? 0), 0);
              const pct = total > 0 ? ((val / total) * 100).toFixed(0) : "0";
              return (
                <div key={idx} className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: PALETTE[idx % PALETTE.length] }} />
                  <span className="text-sm text-[#b4b4b4] flex-1 truncate">{name}</span>
                  <span className="text-sm font-semibold text-[#ececec]">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {chartType === "table" && (
        <div className="overflow-x-auto rounded-xl border border-[#424242]">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="bg-[#353535] border-b border-[#424242]">
                {(columns || (data[0] ? Object.keys(data[0]) : [])).map((col) => (
                  <th key={col} className="px-5 py-3 font-semibold text-[#b4b4b4] uppercase tracking-wider text-xs whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(rows ? rows : data.map((row) => Object.values(row))).map((row: unknown, i) => (
                <tr key={i} className={i % 2 === 0 ? "bg-[#2f2f2f]" : "bg-[#2a2a2a]"}>
                  {(row as unknown[]).map((cell, j) => (
                    <td key={j} className="px-5 py-3 text-[#ececec] whitespace-nowrap">{String(cell ?? "")}</td>
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
