import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  Database,
  BarChart3,
  CheckCircle2,
  FileText,
  X,
  FileJson,
} from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import type { DataSource } from "@/store/useAppStore";
import { cn } from "@/lib/utils";

const OPTIONS = [
  {
    id: "csv" as DataSource,
    icon: Upload,
    title: "Upload CSV",
    description: "Drag & drop or browse your CSV file",
    color: "from-violet-500 to-indigo-500",
    bg: "bg-violet-50 hover:bg-violet-100/80",
    border: "border-violet-200 hover:border-violet-400",
    iconBg: "bg-violet-100",
    iconColor: "text-violet-600",
  },
  {
    id: "database" as DataSource,
    icon: Database,
    title: "Upload Database",
    description: "Connect a .db or .sqlite file",
    color: "from-cyan-500 to-blue-500",
    bg: "bg-cyan-50 hover:bg-cyan-100/80",
    border: "border-cyan-200 hover:border-cyan-400",
    iconBg: "bg-cyan-100",
    iconColor: "text-cyan-600",
  },
  {
    id: "json" as DataSource,
    icon: FileJson,
    title: "Upload JSON",
    description: "JSON array or newline-delimited JSON",
    color: "from-amber-500 to-orange-500",
    bg: "bg-amber-50 hover:bg-amber-100/80",
    border: "border-amber-200 hover:border-amber-400",
    iconBg: "bg-amber-100",
    iconColor: "text-amber-600",
  },
  {
    id: "sample" as DataSource,
    icon: BarChart3,
    title: "Sample Dataset",
    description: "Explore with pre-loaded e-commerce data",
    color: "from-emerald-500 to-teal-500",
    bg: "bg-emerald-50 hover:bg-emerald-100/80",
    border: "border-emerald-200 hover:border-emerald-400",
    iconBg: "bg-emerald-100",
    iconColor: "text-emerald-600",
  },
];

const ACCEPT: Record<string, string> = {
  csv: ".csv",
  database: ".db,.sqlite,.sqlite3",
  json: ".json",
};

export default function DataSourceModal() {
  const { setDataSource, setUploadedFile } = useAppStore();
  const [selected, setSelected] = useState<DataSource>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const needsUpload =
    selected === "csv" || selected === "database" || selected === "json";
  const accept = selected ? (ACCEPT[selected] ?? "*") : "*";

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      setUploadedFile(f);
    },
    [setUploadedFile]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const canContinue =
    selected === "sample" || (needsUpload && file !== null);

  const handleContinue = () => {
    if (!canContinue) return;
    setDataSource(selected);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gradient-to-br from-slate-900/60 via-indigo-900/30 to-slate-900/60 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-2xl mx-4 bg-white rounded-3xl shadow-2xl shadow-black/10 overflow-hidden"
      >
        {/* Header gradient strip */}
        <div className="h-1 w-full bg-gradient-to-r from-violet-500 via-indigo-500 to-cyan-500" />

        <div className="p-8">
          {/* Title */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-4 tracking-wide uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
              DataLens AI
            </div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              Choose your data source
            </h1>
            <p className="text-gray-500 text-sm mt-2">
              Start by connecting your data — it only takes a second
            </p>
          </div>

          {/* Options — 2x2 grid */}
          <div className="grid grid-cols-2 gap-3 mb-6">
            {OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const isSelected = selected === opt.id;
              return (
                <motion.button
                  key={opt.id}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    setSelected(opt.id);
                    setFile(null);
                  }}
                  className={cn(
                    "relative flex items-center gap-3 p-4 rounded-2xl border-2 transition-all duration-200 text-left cursor-pointer group",
                    isSelected
                      ? cn(opt.bg, opt.border, "shadow-md shadow-black/5")
                      : "border-gray-200 bg-gray-50 hover:bg-gray-100/80 hover:border-gray-300"
                  )}
                >
                  {isSelected && (
                    <motion.div
                      layoutId="check"
                      className="absolute -top-2 -right-2"
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                    >
                      <CheckCircle2 className="w-5 h-5 text-indigo-600 fill-white" />
                    </motion.div>
                  )}
                  <div
                    className={cn(
                      "w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors",
                      isSelected ? opt.iconBg : "bg-gray-100"
                    )}
                  >
                    <Icon
                      className={cn(
                        "w-5 h-5",
                        isSelected ? opt.iconColor : "text-gray-500"
                      )}
                    />
                  </div>
                  <div>
                    <p
                      className={cn(
                        "font-semibold text-sm",
                        isSelected ? "text-gray-900" : "text-gray-700"
                      )}
                    >
                      {opt.title}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5 leading-tight">
                      {opt.description}
                    </p>
                  </div>
                </motion.button>
              );
            })}
          </div>

          {/* Upload zone */}
          <AnimatePresence>
            {needsUpload && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.25 }}
                className="overflow-hidden mb-6"
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept={accept}
                  className="hidden"
                  onChange={(e) =>
                    e.target.files?.[0] && handleFile(e.target.files[0])
                  }
                />
                {file ? (
                  <div className="flex items-center gap-3 p-4 bg-indigo-50 border-2 border-indigo-200 rounded-2xl">
                    <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center flex-shrink-0">
                      <FileText className="w-5 h-5 text-indigo-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-gray-900 truncate">
                        {file.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {(file.size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                    <button
                      onClick={() => setFile(null)}
                      className="text-gray-400 hover:text-gray-600 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    onClick={() => fileRef.current?.click()}
                    className={cn(
                      "flex flex-col items-center gap-2 p-6 border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-200",
                      dragging
                        ? "border-indigo-400 bg-indigo-50"
                        : "border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/50"
                    )}
                  >
                    <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center">
                      <Upload className="w-5 h-5 text-gray-400" />
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-gray-700">
                        Drop your file here, or{" "}
                        <span className="text-indigo-600">browse</span>
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {selected === "csv" && "CSV files only"}
                        {selected === "database" && "SQLite / .db files only"}
                        {selected === "json" && "JSON files only"}
                      </p>
                    </div>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* CTA */}
          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={handleContinue}
            disabled={!canContinue}
            className={cn(
              "w-full py-3.5 rounded-2xl font-semibold text-sm transition-all duration-200",
              canContinue
                ? "bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-200 hover:shadow-indigo-300 hover:opacity-95"
                : "bg-gray-100 text-gray-400 cursor-not-allowed"
            )}
          >
            {canContinue ? "Start Exploring →" : "Select a data source to continue"}
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
