import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from "react";
import { api } from "../api/client";
import type { ReviewItem, StepResult } from "../api/types";
import Layout from "../components/Layout";
import SplitModal, { cropUrl } from "../components/SplitModal";

const VERDICT_COLORS = {
  correct: "bg-green-100 text-green-800",
  partial: "bg-yellow-100 text-yellow-800",
  incorrect: "bg-red-100 text-red-800",
};

function StepRow({ step }: { step: StepResult }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-gray-100 last:border-0">
      <span className={`mt-0.5 shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${VERDICT_COLORS[step.verdict]}`}>
        {step.verdict}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800">{step.description}</p>
        <p className="text-xs text-gray-400 mt-0.5">{step.justification}</p>
      </div>
      <span className="shrink-0 text-sm font-medium text-gray-700">
        {step.awarded_points}/{step.max_points}
      </span>
    </div>
  );
}

interface RegionCardHandle {
  approve: () => void;
  toggleOverride: () => void;
  closeOverride: () => void;
}

const RegionCard = forwardRef<RegionCardHandle, { item: ReviewItem; examId: string; isFocused: boolean }>(
  function RegionCard({ item, examId, isFocused }, ref) {
    const qc = useQueryClient();
    const [overrideScore, setOverrideScore] = useState<string>("");
    const [overrideReason, setOverrideReason] = useState<string>("");
    const [showOverride, setShowOverride] = useState(false);
    const [showSplit, setShowSplit] = useState(false);
    const [imgExpanded, setImgExpanded] = useState(false);

    const regionId = item.answer_region.id;
    const { ai_score, max_score, final_score } = item.grade;
    const status = item.answer_region.status;
    const isResolved = status === "approved" || status === "overridden";
    const imgUrl = cropUrl(item.crop_path);

    const approve = useMutation({
      mutationFn: () =>
        api.post(`/review/${regionId}`, { final_score: ai_score }),
      onSuccess: () => qc.invalidateQueries({ queryKey: ["review", examId] }),
    });

    const submitOverride = useMutation({
      mutationFn: (score: number) =>
        api.post(`/review/${regionId}`, {
          final_score: score,
          override_reason: overrideReason || "TA manual override",
        }),
      onSuccess: () => {
        setShowOverride(false);
        setOverrideScore("");
        setOverrideReason("");
        qc.invalidateQueries({ queryKey: ["review", examId] });
      },
    });

    useImperativeHandle(ref, () => ({
      approve: () => { if (!isResolved && !approve.isPending) approve.mutate(); },
      toggleOverride: () => { if (!isResolved) setShowOverride((v) => !v); },
      closeOverride: () => setShowOverride(false),
    }));

    return (
      <>
        {showSplit && (
          <SplitModal
            regionId={regionId}
            cropPath={item.crop_path}
            examId={examId}
            label={`${item.answer_region.student_identifier} — ${item.answer_region.question_id.replace(/^q/i, "Q")}`}
            onClose={() => setShowSplit(false)}
            onSuccess={() => qc.invalidateQueries({ queryKey: ["review", examId] })}
          />
        )}

        <div className={`bg-white border rounded-lg p-5 transition-shadow ${
          isResolved
            ? "border-gray-100 opacity-70"
            : isFocused
            ? "border-gray-400 ring-2 ring-gray-200"
            : "border-gray-200"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-900">
                {item.answer_region.student_identifier} — {item.answer_region.question_id.replace(/^q/i, "Q")}
              </span>
              {isResolved && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                  {status}
                </span>
              )}
              {item.grade.plagiarism_flagged && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-medium">
                  Plagiarism suspected
                  {item.grade.plagiarism_similarity_score != null &&
                    ` (${Math.round(item.grade.plagiarism_similarity_score * 100)}% similar)`}
                </span>
              )}
            </div>
            <div className="text-sm font-semibold text-gray-900">
              {final_score ?? ai_score} / {max_score}
              <span className="text-xs font-normal text-gray-400 ml-1">
                {final_score != null ? "final" : "AI"}
              </span>
            </div>
          </div>

          {imgUrl && (
            <div className="mb-3">
              <img
                src={imgUrl}
                alt="Answer crop"
                onClick={() => setImgExpanded((v) => !v)}
                className={`w-full rounded border border-gray-200 cursor-pointer object-cover transition-all ${imgExpanded ? "" : "max-h-24"}`}
              />
              <p className="text-xs text-gray-400 mt-0.5">
                {imgExpanded ? "Click to collapse" : "Click to expand"}
              </p>
            </div>
          )}

          {item.transcript_text && (
            <div className="bg-gray-50 rounded-md p-3 mb-3 text-xs text-gray-600 font-mono leading-relaxed max-h-32 overflow-y-auto whitespace-pre-wrap">
              {item.transcript_text}
            </div>
          )}

          {item.step_results.length > 0 && (
            <div className="mb-3">
              {item.step_results.map((step) => (
                <StepRow key={step.step_id} step={step} />
              ))}
            </div>
          )}

          {item.overall_justification && (
            <p className="text-xs text-gray-400 italic mb-4">{item.overall_justification}</p>
          )}

          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              {!isResolved && (
                <>
                  <button
                    onClick={() => approve.mutate()}
                    disabled={approve.isPending}
                    className="bg-gray-900 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-gray-800 disabled:opacity-50"
                  >
                    Approve ({ai_score}/{max_score})
                  </button>
                  <button
                    onClick={() => setShowOverride((v) => !v)}
                    className="border border-gray-300 text-gray-600 px-3 py-1.5 rounded-md text-xs font-medium hover:bg-gray-50"
                  >
                    Override score
                  </button>
                </>
              )}
            </div>

            {showOverride && (
              <div className="border border-gray-200 rounded-md p-3 space-y-2 bg-gray-50">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    max={max_score}
                    step={0.5}
                    value={overrideScore}
                    onChange={(e) => setOverrideScore(e.target.value)}
                    placeholder={`Score (0–${max_score})`}
                    className="w-32 border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-gray-900 bg-white"
                  />
                </div>
                <input
                  type="text"
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Reason for override (required if score differs)"
                  className="w-full border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-gray-900 bg-white"
                />
                <button
                  onClick={() => submitOverride.mutate(parseFloat(overrideScore))}
                  disabled={submitOverride.isPending || overrideScore === ""}
                  className="bg-amber-500 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-amber-600 disabled:opacity-50"
                >
                  Submit override
                </button>
              </div>
            )}
          </div>
        </div>
      </>
    );
  }
);

const SHORTCUTS = [
  { keys: ["J", "K"], description: "Navigate down / up through the queue" },
  { keys: ["A"], description: "Approve the focused region (accepts AI score)" },
  { keys: ["E"], description: "Open or close the override panel" },
  { keys: ["Esc"], description: "Close the override panel" },
];

function ShortcutsPanel() {
  return (
    <div className="mb-5 bg-gray-50 border border-gray-200 rounded-lg p-4">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Keyboard shortcuts</p>
      <div className="space-y-2">
        {SHORTCUTS.map(({ keys, description }) => (
          <div key={description} className="flex items-center gap-3">
            <div className="flex gap-1 shrink-0">
              {keys.map((k) => (
                <kbd key={k} className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 rounded border border-gray-300 bg-white text-xs font-mono text-gray-700 shadow-sm">
                  {k}
                </kbd>
              ))}
            </div>
            <span className="text-xs text-gray-600">{description}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-gray-400">Shortcuts are disabled when an input field is focused.</p>
    </div>
  );
}

export default function ReviewQueue() {
  const { examId } = useParams<{ examId: string }>();
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [showShortcuts, setShowShortcuts] = useState(false);

  const focusedIndexRef = useRef(0);
  const itemsRef = useRef<ReviewItem[]>([]);
  const cardRefs = useRef<(RegionCardHandle | null)[]>([]);
  const cardElemRefs = useRef<(HTMLDivElement | null)[]>([]);

  const { data: items = [], isLoading } = useQuery<ReviewItem[]>({
    queryKey: ["review", examId],
    queryFn: () => api.get(`/review/queue?exam_id=${examId}`).then((r) => r.data),
  });

  useEffect(() => { focusedIndexRef.current = focusedIndex; }, [focusedIndex]);
  useEffect(() => { itemsRef.current = items; }, [items]);

  useEffect(() => {
    cardElemRefs.current[focusedIndex]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [focusedIndex]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const idx = focusedIndexRef.current;
      switch (e.key) {
        case "j": case "J":
          e.preventDefault();
          setFocusedIndex((i) => Math.min(i + 1, itemsRef.current.length - 1));
          break;
        case "k": case "K":
          e.preventDefault();
          setFocusedIndex((i) => Math.max(i - 1, 0));
          break;
        case "a": case "A":
          cardRefs.current[idx]?.approve();
          break;
        case "e": case "E":
          cardRefs.current[idx]?.toggleOverride();
          break;
        case "Escape":
          cardRefs.current[idx]?.closeOverride();
          break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const resolved = items.filter(
    (i) => i.answer_region.status === "approved" || i.answer_region.status === "overridden"
  ).length;

  const anyPlagiarism = items.some((i) => i.grade.plagiarism_flagged);

  return (
    <Layout>
      <div className="max-w-2xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Review queue</h1>
            {!isLoading && (
              <p className="text-sm text-gray-500 mt-0.5">
                {resolved}/{items.length} resolved
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowShortcuts((v) => !v)}
              className="text-sm text-gray-500 hover:text-gray-800 border border-gray-200 px-3 py-2 rounded-md hover:bg-gray-50"
              title="Keyboard shortcuts"
            >
              ⌨ Shortcuts
            </button>
            <Link
              to={`/exams/${examId}/results`}
              className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800"
            >
              View results →
            </Link>
          </div>
        </div>

        {showShortcuts && <ShortcutsPanel />}

        {isLoading && <p className="text-sm text-gray-400">Loading…</p>}

        {!isLoading && items.length > 0 && !anyPlagiarism && (
          <div className="mb-4 bg-green-50 border border-green-200 rounded-md px-4 py-3 text-sm text-green-700">
            No plagiarism detected.
          </div>
        )}

        <div className="space-y-4">
          {items.map((item, idx) => (
            <div
              key={item.answer_region.id}
              ref={(el) => { cardElemRefs.current[idx] = el; }}
              onClick={() => setFocusedIndex(idx)}
            >
              <RegionCard
                ref={(el) => { cardRefs.current[idx] = el; }}
                item={item}
                examId={examId!}
                isFocused={focusedIndex === idx}
              />
            </div>
          ))}
        </div>

        {!isLoading && items.length === 0 && (
          <div className="border border-dashed border-gray-300 rounded-lg p-12 text-center">
            <p className="text-gray-400 text-sm">No regions to review.</p>
          </div>
        )}

      </div>
    </Layout>
  );
}
