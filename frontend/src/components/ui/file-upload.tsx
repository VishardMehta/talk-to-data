"use client";

import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import { UploadCloud, File as FileIcon, Loader, X } from "lucide-react";

const ACCEPTED_TYPES = ".csv,.tsv,.json,.jsonl,.parquet,.xlsx,.xls,.db,.sqlite,.sqlite3";
const ACCEPTED_LABEL = "CSV, JSON, Parquet, Excel, SQLite";

interface FileWithProgress {
  id: string;
  name: string;
  size: number;
  file: File;
}

interface FileUploadProps {
  /** Called with all selected files once they're all queued */
  onFilesSelected: (files: File[]) => void;
  /** Legacy single-file compat */
  onFileSelected?: (file: File) => void;
  onClose: () => void;
}

export default function FileUpload({ onFilesSelected, onFileSelected, onClose }: FileUploadProps) {
  const [items, setItems] = useState<FileWithProgress[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (fileList: FileList | File[]) => {
    const incoming = Array.from(fileList);
    if (!incoming.length) return;

    const deduped = incoming.filter((file, idx, all) =>
      all.findIndex((candidate) => (
        candidate.name === file.name
        && candidate.size === file.size
        && candidate.lastModified === file.lastModified
      )) === idx
    );

    if (!deduped.length) return;

    const newItems: FileWithProgress[] = deduped.map((f) => ({
      id: `${f.name}-${Date.now()}-${Math.random()}`,
      name: f.name,
      size: f.size,
      file: f,
    }));

    setItems((prev) => [...prev, ...newItems]);

    // Trigger real backend upload flow immediately; progress is shown by Dashboard.
    if (onFilesSelected) onFilesSelected(deduped);
    if (onFileSelected && deduped.length === 1) onFileSelected(deduped[0]);

    // Allow selecting the same file name again on next open.
    if (inputRef.current) {
      inputRef.current.value = "";
    }

    onClose();
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };
  const onDragOver = (e: DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const onDragLeave = () => setIsDragging(false);
  const onSelect = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) handleFiles(e.target.files);
  };

  const formatSize = (bytes: number) => {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.2 }}
        className="w-full max-w-lg mx-4 bg-[#1e1e1e] rounded-xl border border-[#333] shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-[16px] font-semibold text-[#ececec]">Upload Data</h2>
            <p className="text-xs text-[#6b6b6b] mt-0.5">Multiple files supported — each becomes a queryable table</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[#8e8e8e] hover:text-white hover:bg-[#2f2f2f] transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6">
          {/* Drop zone */}
          <motion.div
            onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            animate={{ borderColor: isDragging ? "#3b82f6" : "#424242", scale: isDragging ? 1.01 : 1 }}
            transition={{ duration: 0.15 }}
            className={clsx(
              "rounded-xl p-8 text-center cursor-pointer bg-[#252525] border border-dashed hover:border-[#555] transition-colors group",
              isDragging && "ring-2 ring-blue-500/30 border-blue-500"
            )}
          >
            <div className="flex flex-col items-center gap-4">
              <motion.div
                animate={{ y: isDragging ? [-4, 0, -4] : 0 }}
                transition={{ duration: 1.5, repeat: isDragging ? Infinity : 0, ease: "easeInOut" }}
              >
                <UploadCloud className={clsx(
                  "w-12 h-12",
                  isDragging ? "text-blue-400" : "text-[#6b6b6b] group-hover:text-[#b4b4b4] transition-colors"
                )} />
              </motion.div>
              <div className="space-y-1">
                <p className="text-[15px] font-medium text-[#ececec]">
                  {isDragging ? "Drop files here" : "Drop your data files here"}
                </p>
                <p className="text-sm text-[#8e8e8e]">
                  {isDragging
                    ? <span className="text-blue-400 font-medium">Release to upload</span>
                    : <><span className="text-blue-400 font-medium">browse</span> to choose</>
                  }
                </p>
                <p className="text-xs text-[#6b6b6b] mt-1">Supports {ACCEPTED_LABEL}</p>
              </div>
              <input
                ref={inputRef} type="file" hidden multiple
                onChange={onSelect} accept={ACCEPTED_TYPES}
              />
            </div>
          </motion.div>

          {/* File list */}
          <AnimatePresence>
            {items.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }} className="mt-4 space-y-2"
              >
                {items.map((item) => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    className="flex items-center gap-3 px-4 py-3 bg-[#252525] rounded-lg border border-[#333]"
                  >
                    <FileIcon className="w-4 h-4 text-[#8e8e8e] shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[#ececec] truncate">{item.name}</p>
                      <p className="text-xs text-[#6b6b6b]">{formatSize(item.size)}</p>
                    </div>
                    <Loader className="w-4 h-4 animate-spin text-blue-400 shrink-0" />
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </motion.div>
  );
}
