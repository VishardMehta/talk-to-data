"use client";

import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import {
  UploadCloud,
  File as FileIcon,
  Trash2,
  Loader,
  CheckCircle,
  X,
} from "lucide-react";

interface FileWithPreview {
  id: string;
  progress: number;
  name: string;
  size: number;
  type: string;
  file: File;
}

const ACCEPTED_TYPES = ".csv,.json,.parquet,.db,.sqlite,.sqlite3";
const ACCEPTED_LABEL = "CSV, JSON, Parquet, Database";

interface FileUploadProps {
  onFileSelected: (file: File) => void;
  onClose: () => void;
}

export default function FileUpload({ onFileSelected, onClose }: FileUploadProps) {
  const [files, setFiles] = useState<FileWithPreview[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (fileList: FileList) => {
    const newFiles = Array.from(fileList).map((file) => ({
      id: `${file.name}-${Date.now()}-${Math.random()}`,
      progress: 0,
      name: file.name,
      size: file.size,
      type: file.type,
      file,
    }));
    setFiles((prev) => [...prev, ...newFiles]);
    newFiles.forEach((f) => simulateUpload(f.id, f.file));
  };

  const simulateUpload = (id: string, file: File) => {
    let progress = 0;
    const interval = setInterval(() => {
      progress += Math.random() * 20 + 10;
      setFiles((prev) =>
        prev.map((f) =>
          f.id === id ? { ...f, progress: Math.min(progress, 100) } : f
        )
      );
      if (progress >= 100) {
        clearInterval(interval);
        // Trigger the callback once upload is "done"
        onFileSelected(file);
      }
    }, 200);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const onDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => setIsDragging(false);

  const onSelect = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) handleFiles(e.target.files);
  };

  const formatFileSize = (bytes: number): string => {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
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
          <h2 className="text-[16px] font-semibold text-[#ececec]">Upload Data</h2>
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
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            initial={false}
            animate={{
              borderColor: isDragging ? "#3b82f6" : "#333",
              scale: isDragging ? 1.01 : 1,
            }}
            transition={{ duration: 0.2 }}
            className={clsx(
              "relative rounded-xl p-8 text-center cursor-pointer bg-[#252525] border border-dashed border-[#424242] hover:border-[#555] transition-colors group",
              isDragging && "ring-2 ring-blue-500/30 border-blue-500"
            )}
          >
            <div className="flex flex-col items-center gap-4">
              <motion.div
                animate={{ y: isDragging ? [-4, 0, -4] : 0 }}
                transition={{
                  duration: 1.5,
                  repeat: isDragging ? Infinity : 0,
                  ease: "easeInOut",
                }}
              >
                <UploadCloud
                  className={clsx(
                    "w-12 h-12",
                    isDragging
                      ? "text-blue-400"
                      : "text-[#6b6b6b] group-hover:text-[#b4b4b4] transition-colors duration-200"
                  )}
                />
              </motion.div>

              <div className="space-y-1.5">
                <p className="text-[15px] font-medium text-[#ececec]">
                  {isDragging
                    ? "Drop files here"
                    : files.length > 0
                      ? "Add more files"
                      : "Drop your data file here"}
                </p>
                <p className="text-sm text-[#8e8e8e]">
                  {isDragging ? (
                    <span className="text-blue-400 font-medium">Release to upload</span>
                  ) : (
                    <>
                      or{" "}
                      <span className="text-blue-400 font-medium">browse</span>{" "}
                      to choose
                    </>
                  )}
                </p>
                <p className="text-xs text-[#6b6b6b] mt-1">
                  Supports {ACCEPTED_LABEL}
                </p>
              </div>

              <input
                ref={inputRef}
                type="file"
                hidden
                onChange={onSelect}
                accept={ACCEPTED_TYPES}
              />
            </div>
          </motion.div>

          {/* File list */}
          <AnimatePresence>
            {files.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-4 space-y-2"
              >
                {files.map((file) => (
                  <motion.div
                    key={file.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="flex items-center gap-3 px-4 py-3 bg-[#252525] rounded-lg border border-[#333]"
                  >
                    <FileIcon className="w-5 h-5 text-[#8e8e8e] flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[#ececec] truncate">{file.name}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-[#6b6b6b]">
                          {formatFileSize(file.size)}
                        </span>
                        <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${file.progress}%` }}
                            className={clsx(
                              "h-full rounded-full",
                              file.progress < 100 ? "bg-blue-500" : "bg-emerald-500"
                            )}
                          />
                        </div>
                        <span className="text-xs text-[#6b6b6b] w-8 text-right">
                          {Math.round(file.progress)}%
                        </span>
                      </div>
                    </div>
                    {file.progress < 100 ? (
                      <Loader className="w-4 h-4 animate-spin text-blue-400 flex-shrink-0" />
                    ) : (
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <CheckCircle className="w-4 h-4 text-emerald-500" />
                        <button
                          onClick={() => setFiles((prev) => prev.filter((f) => f.id !== file.id))}
                          className="w-6 h-6 flex items-center justify-center rounded text-[#6b6b6b] hover:text-red-400 transition-colors cursor-pointer"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
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
