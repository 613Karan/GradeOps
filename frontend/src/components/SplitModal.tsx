import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";

const API_ROOT = (import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1").replace(
  /\/api\/v1$/,
  ""
);

export function cropUrl(path: string | null): string | null {
  if (!path) return null;
  return `${API_ROOT}/${path.replace(/^\.\//, "")}`;
}

interface SplitModalProps {
  regionId: string;
  cropPath: string | null;
  examId: string;
  label: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function SplitModal({
  regionId,
  cropPath,
  examId,
  label,
  onClose,
  onSuccess,
}: SplitModalProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [splitRatios, setSplitRatios] = useState<number[]>([]);
  const [bandLabels, setBandLabels] = useState<string[]>([""]);
  const url = cropUrl(cropPath);

  function handleContainerClick(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0.01, Math.min(0.99, (e.clientY - rect.top) / rect.height));
    const newRatios = [...splitRatios, ratio].sort((a, b) => a - b);
    const insertIdx = newRatios.indexOf(ratio);
    setSplitRatios(newRatios);
    // Insert a new empty label slot after the band above the new cut line
    setBandLabels((prev) => [
      ...prev.slice(0, insertIdx + 1),
      "",
      ...prev.slice(insertIdx + 1),
    ]);
  }

  function removeSplit(idx: number, e: React.MouseEvent) {
    e.stopPropagation();
    setSplitRatios((prev) => prev.filter((_, i) => i !== idx));
    // Remove the band label below the removed cut line; the band above absorbs it
    setBandLabels((prev) => prev.filter((_, i) => i !== idx + 1));
  }

  function updateLabel(bandIdx: number, value: string) {
    setBandLabels((prev) => prev.map((l, i) => (i === bandIdx ? value : l)));
  }

  function toPixels(): number[] {
    const img = imgRef.current;
    if (!img) return [];
    return splitRatios.map((r) => Math.round(r * img.naturalHeight));
  }

  const hasAnyLabel = bandLabels.some((l) => l.trim() !== "");

  const splitMutation = useMutation({
    mutationFn: () =>
      api.post(`/exams/${examId}/regions/${regionId}/split`, {
        split_points: toPixels(),
        question_ids: bandLabels,
      }),
    onSuccess: () => {
      onSuccess();
      onClose();
    },
  });

  const bandCount = splitRatios.length + 1;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl w-full max-w-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Split region</h2>
            <p className="text-xs text-gray-500 mt-0.5">{label}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none px-1"
          >
            ×
          </button>
        </div>

        <p className="px-5 pt-3 pb-1 text-xs text-gray-500">
          Click the image to place cut lines.{" "}
          {splitRatios.length > 0
            ? `${splitRatios.length} cut${splitRatios.length > 1 ? "s" : ""} → ${bandCount} bands.`
            : "No cuts yet."}{" "}
          Label each band with a question number (e.g. Q1). Leave blank to discard that band.
        </p>

        {/* Scrollable image area */}
        <div className="flex-1 overflow-y-auto px-5 pb-3 min-h-0">
          {url ? (
            <div
              className="relative cursor-crosshair select-none"
              onClick={handleContainerClick}
            >
              <img
                ref={imgRef}
                src={url}
                alt="Answer region"
                className="w-full block rounded border border-gray-200"
                draggable={false}
              />
              {splitRatios.map((ratio, i) => (
                <div
                  key={i}
                  className="absolute left-0 right-0 flex items-center pointer-events-none"
                  style={{ top: `${ratio * 100}%`, transform: "translateY(-50%)" }}
                >
                  <div className="flex-1 border-t-2 border-red-500" />
                  <button
                    onClick={(e) => removeSplit(i, e)}
                    className="pointer-events-auto ml-1 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center hover:bg-red-600 shrink-0 leading-none"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-10">Image not available</p>
          )}
        </div>

        {/* Band labels — always visible, not inside scroll area */}
        <div className="px-5 py-3 border-t border-gray-100 space-y-2">
          <p className="text-xs font-medium text-gray-500">
            Band labels{" "}
            <span className="font-normal text-gray-400">(blank = discard that band)</span>
          </p>
          {bandLabels.map((lbl, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-14 shrink-0">Band {i + 1}</span>
              <input
                type="text"
                value={lbl}
                onChange={(e) => updateLabel(i, e.target.value)}
                placeholder="Q1, Q2…"
                className="flex-1 border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-gray-900 bg-white"
              />
            </div>
          ))}
        </div>

        <div className="px-5 py-4 border-t border-gray-200 flex items-center gap-2">
          <button
            onClick={() => { setSplitRatios([]); setBandLabels([""]); }}
            disabled={splitRatios.length === 0}
            className="border border-gray-300 text-gray-600 px-3 py-1.5 rounded-md text-xs font-medium hover:bg-gray-50 disabled:opacity-40"
          >
            Clear all
          </button>
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="border border-gray-300 text-gray-600 px-3 py-1.5 rounded-md text-xs font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={() => splitMutation.mutate()}
            disabled={splitRatios.length === 0 || !hasAnyLabel || splitMutation.isPending}
            className="bg-gray-900 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-gray-800 disabled:opacity-50"
          >
            {splitMutation.isPending
              ? "Splitting…"
              : `Apply ${splitRatios.length} cut${splitRatios.length !== 1 ? "s" : ""}`}
          </button>
        </div>

        {splitMutation.isError && (
          <p className="px-5 pb-3 text-xs text-red-500">Split failed — check server logs.</p>
        )}
      </div>
    </div>
  );
}
