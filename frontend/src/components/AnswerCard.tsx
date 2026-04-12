import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Code2 } from "lucide-react";
import type { QueryResult } from "@/types";
import ChartRenderer from "./ChartRenderer";
import { parseBold } from "@/utils/formatAnswer";

interface AnswerCardProps {
  result: QueryResult;
}

function RichText({ text }: { text: string }) {
  const parts = parseBold(text);
  return (
    <>
      {parts.map((p, i) =>
        p.bold ? (
          <strong key={i} className="font-semibold text-white">
            {p.text}
          </strong>
        ) : (
          <span key={i}>{p.text}</span>
        )
      )}
    </>
  );
}

export default function AnswerCard({ result }: AnswerCardProps) {
  const [sqlOpen, setSqlOpen] = useState(false);

  const hasChart =
    result.chart_type &&
    result.chart_type !== "stat_card" &&
    result.data &&
    result.data.length > 0;

  const hasStatCard =
    result.chart_type === "stat_card" && result.data && result.data.length > 0;

  const hasTable =
    result.chart_type === "table" &&
    ((result.columns && result.columns.length > 0) || (result.data && result.data.length > 0));

  return (
    <div className="space-y-5">
      {/* ─── Headline Insight (the final answer, prominent) ─── */}
      <div className="text-[16px] text-[#ececec] leading-[1.75]">
        <RichText text={result.answer} />
      </div>

      {/* ─── Metric Display (premium stat card) ─── */}
      {hasStatCard && (
        <ChartRenderer
          chartType="stat_card"
          data={result.data!}
          xKey={result.x_key}
          yKey={result.y_key}
        />
      )}

      {/* ─── Visualization ─── */}
      {hasChart && (
        <div className="bg-[#2a2a2a] border border-[#3a3a3a] rounded-xl p-5 overflow-hidden">
          <ChartRenderer
            chartType={result.chart_type!}
            data={result.data!}
            xKey={result.x_key}
            yKey={result.y_key}
            nameKey={result.name_key}
            valueKey={result.value_key}
          />
        </div>
      )}

      {/* ─── Data Table ─── */}
      {hasTable && (
        <div className="bg-[#2a2a2a] border border-[#3a3a3a] rounded-xl p-4 overflow-x-auto">
          <ChartRenderer chartType="table" data={result.data || []} columns={result.columns} rows={result.rows} />
        </div>
      )}

      {/* ─── Source & Confidence (subtle footer) ─── */}
      <div className="flex items-center gap-4 flex-wrap text-sm">
        {result.table_name && (
          <span className="text-[#6b6b6b]">
            Based on <span className="text-[#8e8e8e] font-medium">{result.table_name}</span>
          </span>
        )}
        {result.cached && (
          <span className="text-amber-400/80 font-medium">⚡ Cached</span>
        )}
        {result.confidence !== undefined && (
          <span className={`font-semibold px-2.5 py-0.5 rounded-md text-xs ${
            result.confidence >= 8 ? "bg-emerald-500/10 text-emerald-400"
            : result.confidence >= 5 ? "bg-amber-500/10 text-amber-400"
            : "bg-red-500/10 text-red-400"
          }`}>
            Confidence: {result.confidence}/10
          </span>
        )}
        {result.time_ms !== undefined && (
          <span className="text-[#6b6b6b]">{Math.round(result.time_ms)}ms</span>
        )}
      </div>

      {/* ─── SQL (hidden by default, opt-in) ─── */}
      {result.sql && (
        <div>
          <button
            onClick={() => setSqlOpen((v) => !v)}
            className="flex items-center gap-2 text-xs text-[#6b6b6b] hover:text-[#8e8e8e] transition-colors cursor-pointer py-1"
          >
            <Code2 className="w-3.5 h-3.5" />
            <span>Show technical details</span>
            {sqlOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          <AnimatePresence>
            {sqlOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden mt-2"
              >
                <pre className="text-xs font-mono bg-[#1a1a1a] text-emerald-400/80 rounded-lg p-4 overflow-x-auto leading-relaxed border border-[#2f2f2f]">
                  {result.sql}
                </pre>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
