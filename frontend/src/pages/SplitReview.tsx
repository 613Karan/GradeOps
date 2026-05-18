import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRef, useState, useMemo, useEffect } from "react";
import { api } from "../api/client";
import type { AnswerRegionRead, Exam, RubricQuestion } from "../api/types";
import Layout from "../components/Layout";
import { cropUrl } from "../components/SplitModal";

export default function SplitReview() {
  const { id: examId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const imgRef = useRef<HTMLImageElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: exam } = useQuery<Exam>({
    queryKey: ["exam", examId],
    queryFn: () => api.get(`/exams/${examId}`).then((r) => r.data),
  });

  const { data: regions = [], isLoading, refetch: refetchRegions } = useQuery<AnswerRegionRead[]>({
    queryKey: ["regions", examId],
    queryFn: () => api.get(`/exams/${examId}/regions`).then((r) => r.data),
  });

  // Capture unsplit regions once on first non-empty load.
  // If a split 404s (region already gone), refetch and reinitialise.
  const [workQueue, setWorkQueue] = useState<AnswerRegionRead[] | null>(null);
  useEffect(() => {
    if (regions.length > 0 && workQueue === null) {
      setWorkQueue(regions.filter((r) => r.question_id === "unsplit"));
    }
  }, [regions, workQueue]);

  const rubricQuestions: RubricQuestion[] = useMemo(
    () => exam?.rubric?.questions ?? [],
    [exam]
  );

  const [studentIdx, setStudentIdx] = useState(0);
  const [splitRatios, setSplitRatios] = useState<number[]>([]);
  const [bandLabels, setBandLabels] = useState<string[]>([""]);
  const [doneCount, setDoneCount] = useState(0);

  const currentRegion = workQueue?.[studentIdx];
  const totalStudents = workQueue?.length ?? 0;
  const allDone = totalStudents > 0 && doneCount >= totalStudents;

  function handleImageClick(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0.01, Math.min(0.99, (e.clientY - rect.top) / rect.height));
    const newRatios = [...splitRatios, ratio].sort((a, b) => a - b);
    const insertIdx = newRatios.indexOf(ratio);
    const autoLabel = rubricQuestions[insertIdx + 1]?.question_id ?? "";
    const newLabels = [
      ...bandLabels.slice(0, insertIdx + 1),
      autoLabel,
      ...bandLabels.slice(insertIdx + 1),
    ];
    setSplitRatios(newRatios);
    setBandLabels(newLabels);
  }

  function removeSplit(idx: number, e: React.MouseEvent) {
    e.stopPropagation();
    setSplitRatios((prev) => prev.filter((_, i) => i !== idx));
    setBandLabels((prev) => prev.filter((_, i) => i !== idx + 1));
  }

  function updateLabel(bandIdx: number, value: string) {
    setBandLabels((prev) => prev.map((l, i) => (i === bandIdx ? value : l)));
  }

  function clearAll() {
    setSplitRatios([]);
    const firstLabel = rubricQuestions[0]?.question_id ?? "";
    setBandLabels([firstLabel]);
  }

  function resetForNextStudent() {
    setSplitRatios([]);
    const firstLabel = rubricQuestions[0]?.question_id ?? "";
    setBandLabels([firstLabel]);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }

  function toPixels(): number[] {
    const img = imgRef.current;
    if (!img) return [];
    return splitRatios.map((r) => Math.round(r * img.naturalHeight));
  }

  const splitMutation = useMutation({
    mutationFn: () =>
      api.post(`/exams/${examId}/regions/${currentRegion!.id}/split`, {
        split_points: toPixels(),
        question_ids: bandLabels,
      }),
    onSuccess: () => {
      setDoneCount((c) => c + 1);
      if (studentIdx < totalStudents - 1) {
        setStudentIdx((i) => i + 1);
        resetForNextStudent();
      }
    },
    onError: async (err: any) => {
      // Region already split (404) — reinitialise work queue from fresh data
      if (err?.response?.status === 404) {
        const fresh = await refetchRegions();
        const unsplit = (fresh.data ?? []).filter((r) => r.question_id === "unsplit");
        setWorkQueue(unsplit);
        setStudentIdx(0);
        setDoneCount(0);
        resetForNextStudent();
      }
    },
  });

  const startGradingMutation = useMutation({
    mutationFn: () => api.post(`/exams/${examId}/start-grading`),
    onSuccess: () => navigate(`/exams/${examId}`),
  });

  // Pre-fill first band label when rubric loads
  useEffect(() => {
    if (rubricQuestions.length > 0 && bandLabels[0] === "") {
      setBandLabels([rubricQuestions[0].question_id]);
    }
  }, [rubricQuestions]);

  // ── Loading / empty states ────────────────────────────────────────────────

  if (isLoading || workQueue === null) {
    return (
      <Layout>
        <p className="text-sm text-gray-400">Loading regions…</p>
      </Layout>
    );
  }

  if (workQueue.length === 0) {
    return (
      <Layout>
        <div className="max-w-2xl">
          <h1 className="text-2xl font-semibold text-gray-900 mb-3">Mark answer regions</h1>
          <p className="text-sm text-gray-500 mb-4">
            All scripts have already been split. You can start grading.
          </p>
          <button
            onClick={() => startGradingMutation.mutate()}
            disabled={startGradingMutation.isPending}
            className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
          >
            {startGradingMutation.isPending ? "Starting…" : "Start grading →"}
          </button>
        </div>
      </Layout>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const imgUrl = currentRegion ? cropUrl(currentRegion.crop_path) : null;
  const bandCount = splitRatios.length + 1;
  const hasAnyLabel = bandLabels.some((l) => l.trim() !== "");
  const canApply = splitRatios.length > 0 && hasAnyLabel;

  return (
    <Layout>
      <div className="max-w-2xl">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Mark answer regions</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Student {studentIdx + 1} of {totalStudents}
              {currentRegion && (
                <span className="font-mono ml-2 text-gray-400">
                  {currentRegion.student_identifier}
                </span>
              )}
            </p>
          </div>

          {allDone && (
            <button
              onClick={() => startGradingMutation.mutate()}
              disabled={startGradingMutation.isPending}
              className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800 disabled:opacity-50 shrink-0"
            >
              {startGradingMutation.isPending ? "Starting…" : "Start grading →"}
            </button>
          )}
        </div>

        {/* Progress bar */}
        <div className="bg-gray-100 rounded-full h-1 mb-5 overflow-hidden">
          <div
            className="bg-gray-900 h-full rounded-full transition-all duration-300"
            style={{ width: `${(doneCount / totalStudents) * 100}%` }}
          />
        </div>

        {/* Rubric reference */}
        <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 mb-4">
          <p className="text-xs font-medium text-gray-500 mb-1.5">
            Questions in rubric — use these IDs to label bands
          </p>
          <div className="flex flex-wrap gap-2">
            {rubricQuestions.map((q) => (
              <span
                key={q.question_id}
                className="inline-flex items-center gap-1 text-xs bg-white border border-gray-200 rounded px-2 py-0.5"
              >
                <span className="font-mono font-medium text-gray-800">
                  {q.question_id}
                </span>
                <span className="text-gray-400 truncate max-w-[140px]">
                  {q.question_text}
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* Scrollable image + cut lines */}
        <div className="bg-white border border-gray-200 rounded-lg mb-4 overflow-hidden">
          <p className="px-4 pt-3 pb-1 text-xs text-gray-500">
            Click anywhere on the image to place a cut line.{" "}
            {splitRatios.length > 0
              ? `${splitRatios.length} cut${splitRatios.length !== 1 ? "s" : ""} → ${bandCount} bands.`
              : "No cuts yet — the whole script will become one region."}
          </p>

          <div ref={scrollRef} className="overflow-y-auto px-4 pb-4" style={{ maxHeight: "70vh" }}>
            {imgUrl ? (
              <div
                className="relative cursor-crosshair select-none"
                onClick={handleImageClick}
              >
                <img
                  ref={imgRef}
                  src={imgUrl}
                  alt="Student answer script"
                  className="w-full block rounded border border-gray-100"
                  draggable={false}
                />

                {splitRatios.map((ratio, i) => (
                  <div
                    key={i}
                    className="absolute left-0 right-0 flex items-center"
                    style={{ top: `${ratio * 100}%`, transform: "translateY(-50%)" }}
                  >
                    <div className="flex-1 border-t-2 border-red-500 pointer-events-none" />
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
        </div>

        {/* Band labels */}
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 mb-4">
          <p className="text-xs font-medium text-gray-500 mb-2">
            Band labels{" "}
            <span className="font-normal text-gray-400">(blank = discard that band)</span>
          </p>
          <div className="space-y-2">
            {bandLabels.map((lbl, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="text-xs text-gray-400 w-14 shrink-0">Band {i + 1}</span>
                <input
                  type="text"
                  value={lbl}
                  onChange={(e) => updateLabel(i, e.target.value)}
                  placeholder="q1, q2…"
                  className="flex-1 border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-gray-900 bg-white font-mono"
                />
                {rubricQuestions[i] && (
                  <span className="text-xs text-gray-400 truncate max-w-[180px]">
                    {rubricQuestions[i].question_text}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Action row */}
        <div className="flex items-center gap-2">
          <button
            onClick={clearAll}
            disabled={splitRatios.length === 0}
            className="border border-gray-300 text-gray-600 px-3 py-2 rounded-md text-sm font-medium hover:bg-gray-50 disabled:opacity-40"
          >
            Clear all
          </button>

          <div className="flex-1" />

          {splitMutation.isError && (
            <span className="text-xs text-red-500">Split failed — check server logs.</span>
          )}

          {allDone ? (
            <span className="text-xs text-green-600 font-medium">All students split ✓</span>
          ) : (
            <button
              onClick={() => splitMutation.mutate()}
              disabled={!canApply || splitMutation.isPending}
              className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800 disabled:opacity-40"
            >
              {splitMutation.isPending
                ? "Splitting…"
                : studentIdx < totalStudents - 1
                ? `Apply cuts → student ${studentIdx + 2}`
                : "Apply cuts — done"}
            </button>
          )}
        </div>

        {startGradingMutation.isError && (
          <p className="mt-3 text-xs text-red-500">
            Failed to start grading — check server logs.
          </p>
        )}
      </div>
    </Layout>
  );
}
