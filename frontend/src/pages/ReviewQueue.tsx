import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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

function RegionCard({ item, examId }: { item: ReviewItem; examId: string }) {
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

      <div className={`bg-white border rounded-lg p-5 ${isResolved ? "border-gray-100 opacity-70" : "border-gray-200"}`}>
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

export default function ReviewQueue() {
  const { examId } = useParams<{ examId: string }>();

  const { data: items = [], isLoading } = useQuery<ReviewItem[]>({
    queryKey: ["review", examId],
    queryFn: () => api.get(`/review/queue?exam_id=${examId}`).then((r) => r.data),
  });

  const resolved = items.filter(
    (i) => i.answer_region.status === "approved" || i.answer_region.status === "overridden"
  ).length;

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
          <Link
            to={`/exams/${examId}/results`}
            className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800"
          >
            View results →
          </Link>
        </div>

        {isLoading && <p className="text-sm text-gray-400">Loading…</p>}

        <div className="space-y-4">
          {items.map((item) => (
            <RegionCard key={item.answer_region.id} item={item} examId={examId!} />
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
