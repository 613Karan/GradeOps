import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Exam, ExamStatus as TExamStatus } from "../api/types";
import Layout from "../components/Layout";
import { useAuth } from "../hooks/useAuth";

type VisualStep = "uploaded" | "splitting" | "splits_ready" | "ocr" | "grading" | "ready";

const STATUS_STEPS: VisualStep[] = [
  "uploaded",
  "splitting",
  "splits_ready",
  "ocr",
  "grading",
  "ready",
];

const STATUS_LABELS: Record<VisualStep, string> = {
  uploaded: "Uploaded",
  splitting: "Splitting",
  splits_ready: "Splits ready",
  ocr: "OCR",
  grading: "Grading",
  ready: "Ready",
};

function toVisualStep(status: TExamStatus): VisualStep | "error" {
  switch (status) {
    case "uploaded":    return "uploaded";
    case "splitting":   return "splitting";
    case "split_done":  return "splits_ready";
    case "ocr_running":
    case "ocr_done":    return "ocr";
    case "grading":
    case "graded":      return "grading";
    case "review":
    case "completed":   return "ready";
    case "failed":      return "error";
    default:            return "uploaded";
  }
}

function StatusPipeline({ status }: { status: TExamStatus }) {
  const visual = toVisualStep(status);

  if (visual === "error") {
    return <p className="text-sm text-red-600">Pipeline failed. Check server logs.</p>;
  }

  const currentIdx = STATUS_STEPS.indexOf(visual);

  return (
    <div className="flex items-center gap-0 flex-wrap">
      {STATUS_STEPS.map((step, i) => {
        const done = i < currentIdx;
        const active = i === currentIdx;
        return (
          <div key={step} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium border-2
                  ${done ? "bg-gray-900 border-gray-900 text-white" : ""}
                  ${active ? "border-gray-900 text-gray-900 bg-white animate-pulse" : ""}
                  ${!done && !active ? "border-gray-300 text-gray-300 bg-white" : ""}
                `}
              >
                {done ? "✓" : i + 1}
              </div>
              <span
                className={`text-xs mt-1 whitespace-nowrap ${
                  active ? "text-gray-900 font-medium" : "text-gray-400"
                }`}
              >
                {STATUS_LABELS[step]}
              </span>
            </div>
            {i < STATUS_STEPS.length - 1 && (
              <div className={`h-0.5 w-10 mb-5 ${done ? "bg-gray-900" : "bg-gray-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function ExamStatusPage() {
  const { id } = useParams<{ id: string }>();
  const { currentRole } = useAuth();
  const role = currentRole();
  const queryClient = useQueryClient();

  const { data: exam } = useQuery<Exam>({
    queryKey: ["exam", id],
    queryFn: () => api.get(`/exams/${id}`).then((r) => r.data),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return 3000;
      const visual = toVisualStep(status);
      return visual === "splits_ready" || visual === "ready" ? false : 3000;
    },
  });

  const retryGradingMutation = useMutation({
    mutationFn: () => api.post(`/exams/${id}/start-grading`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["exam", id] }),
  });

  const visual = exam ? toVisualStep(exam.status) : null;

  return (
    <Layout>
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold text-gray-900 mb-1">
          {exam?.title ?? "Loading…"}
        </h1>
        <p className="text-sm text-gray-500 mb-8">Exam ID: {id}</p>

        <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6 overflow-x-auto">
          {exam ? (
            <StatusPipeline status={exam.status} />
          ) : (
            <p className="text-sm text-gray-400">Loading pipeline status…</p>
          )}
        </div>

        {/* Failed — offer retry if splitting was already done */}
        {visual === "error" && (
          <div className="mb-4 flex items-center gap-3">
            <p className="text-sm text-gray-500">
              Grading pipeline failed.{" "}
              {role !== "instructor" && "You can retry if regions are already split."}
            </p>
            {role !== "instructor" && (
              <button
                onClick={() => retryGradingMutation.mutate()}
                disabled={retryGradingMutation.isPending}
                className="shrink-0 bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
              >
                {retryGradingMutation.isPending ? "Starting…" : "Retry grading →"}
              </button>
            )}
            {retryGradingMutation.isError && (
              <p className="text-xs text-red-500">
                Retry failed — splits may not be complete yet. Go to Mark regions first.
              </p>
            )}
          </div>
        )}

        {/* Splits ready — TA marks answer regions before grading starts */}
        {visual === "splits_ready" && role !== "instructor" && (
          <div className="mb-4">
            <p className="text-sm text-gray-600 mb-3">
              Pages have been split into answer regions. Mark each question's region
              before starting OCR and grading.
            </p>
            <Link
              to={`/exams/${id}/splits`}
              className="inline-block bg-gray-900 text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-gray-800"
            >
              Mark regions →
            </Link>
          </div>
        )}

        {visual === "splits_ready" && role === "instructor" && (
          <p className="text-sm text-gray-400 mb-4">
            Waiting for a TA to mark answer regions before grading begins.
          </p>
        )}

        {/* Grading done — open TA review queue */}
        {visual === "ready" && (
          <Link
            to={`/review/${id}`}
            className="inline-block bg-gray-900 text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-gray-800"
          >
            Open review queue →
          </Link>
        )}

        {/* Pipeline still running */}
        {visual && visual !== "splits_ready" && visual !== "ready" && visual !== "error" && (
          <p className="text-sm text-gray-400">
            Pipeline is running. This page updates automatically.
          </p>
        )}
      </div>
    </Layout>
  );
}
