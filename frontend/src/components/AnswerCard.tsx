import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Code2, Sparkles } from "lucide-react";
import type { QueryResult } from "@/types";
import ChartRenderer from "./ChartRenderer";
import { parseBold } from "@/utils/formatAnswer";
import { cn } from "@/lib/utils";

interface AnswerCardProps {
  result: QueryResult;
}

function RichText({ text }: { text: string }) {
  const parts = parseBold(text);
  return (
    <>
      {parts.map((p, i) =>
        p.bold ? (
          <strong key={i} className="font-semibold text-gray-900">
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
    result.chart_type === "stat_card" &&
    result.data &&
    result.data.length > 0;

  const hasTable =
    result.chart_type === "table" &&
    ((result.columns && result.columns.length > 0) ||
      (result.data && result.data.length > 0));

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="bg-white border border-gray-100 rounded-2xl rounded-tl-sm shadow-sm overflow-hidden"
    >
      <div className="px-5 py-4 space-y-4">
        {/* Interpreted as */}
        {result.interpreted_as && (
          <p className="text-xs text-violet-500 italic flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 flex-shrink-0" />
            I interpreted your question as:{" "}
            <span className="font-medium">{result.interpreted_as}</span>
          </p>
        )}

        {/* Answer text */}
        <p className="text-sm text-gray-700 leading-relaxed">
          <RichText text={result.answer} />
        </p>

        {/* Stat card */}
        {hasStatCard && (
          <ChartRenderer
            chartType="stat_card"
            data={result.data!}
            xKey={result.x_key}
            yKey={result.y_key}
          />
        )}

        {/* Chart */}
        {hasChart && (
          <ChartRenderer
            chartType={result.chart_type!}
            data={result.data!}
            xKey={result.x_key}
            yKey={result.y_key}
            nameKey={result.name_key}
            valueKey={result.value_key}
            title={result.question}
          />
        )}

        {/* Table */}
        {hasTable && (
          <ChartRenderer
            chartType="table"
            data={result.data || []}
            columns={result.columns}
            rows={result.rows}
          />
        )}

        {/* SQL section */}
        {result.sql && (
          <div>
            <button
              onClick={() => setSqlOpen((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-violet-500 transition-colors"
            >
              <Code2 className="w-3.5 h-3.5" />
              <span>View SQL</span>
              {sqlOpen ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
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
                  <pre className="text-xs font-mono bg-gray-950 text-emerald-400 rounded-xl p-4 overflow-x-auto leading-relaxed">
                    {result.sql}
                  </pre>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-1 border-t border-gray-50">
          {result.table_name && (
            <p className="text-xs text-gray-400">
              Based on:{" "}
              <span className="font-medium text-gray-500">{result.table_name}</span>
            </p>
          )}
          <div className="flex items-center gap-3 ml-auto">
            {result.cached && (
              <span className="text-xs text-amber-500 font-medium">⚡ cached</span>
            )}
            {result.confidence !== undefined && (
              <span
                className={cn(
                  "text-xs font-semibold px-2 py-0.5 rounded-full",
                  result.confidence >= 8
                    ? "bg-emerald-50 text-emerald-600"
                    : result.confidence >= 5
                    ? "bg-amber-50 text-amber-600"
                    : "bg-red-50 text-red-500"
                )}
              >
                {result.confidence}/10
              </span>
            )}
            {result.time_ms !== undefined && (
              <span className="text-xs text-gray-400">{Math.round(result.time_ms)}ms</span>
            )}
          </div>
        </div>

        {/* Follow-up questions */}
        {result.follow_ups && result.follow_ups.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              You might also ask
            </p>
            <div className="flex flex-wrap gap-2">
              {result.follow_ups.map((q) => (
                <button
                  key={q}
                  className="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs rounded-full font-medium transition-colors border border-indigo-100 hover:border-indigo-200"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
