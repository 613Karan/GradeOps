import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import Layout from "../components/Layout";

interface QuestionScore {
  question_id: string;
  final_score: number | null;
  ai_score: number;
  max_score: number;
  status: string;
}

interface StudentResult {
  student_identifier: string;
  questions: QuestionScore[];
  total_score: number;
  max_total: number;
  pending_count: number;
}

interface ExamResults {
  exam_id: string;
  exam_title: string;
  student_results: StudentResult[];
  total_regions: number;
  reviewed_regions: number;
}

const STATUS_BADGE: Record<string, string> = {
  approved:   "bg-green-100 text-green-700",
  overridden: "bg-amber-100 text-amber-700",
  graded:     "bg-blue-100 text-blue-700",
  flagged:    "bg-red-100 text-red-700",
  pending:    "bg-gray-100 text-gray-500",
};

// ── Stats helpers ─────────────────────────────────────────────────────────────

function mean(arr: number[]) {
  return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
}

function median(arr: number[]) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function stddev(arr: number[]) {
  const m = mean(arr);
  return arr.length
    ? Math.sqrt(arr.reduce((a, b) => a + (b - m) ** 2, 0) / arr.length)
    : 0;
}

function pct(score: number, max: number) {
  return max > 0 ? (score / max) * 100 : 0;
}

function fmt(n: number, decimals = 1) {
  return n.toFixed(decimals);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-semibold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function DistributionBar({
  buckets,
  maxCount,
}: {
  buckets: { label: string; count: number }[];
  maxCount: number;
}) {
  return (
    <div className="flex items-end gap-1.5 h-32">
      {buckets.map((b) => {
        const heightPct = maxCount > 0 ? (b.count / maxCount) * 100 : 0;
        return (
          <div key={b.label} className="flex flex-col items-center flex-1 gap-1">
            <span className="text-xs text-gray-500">{b.count > 0 ? b.count : ""}</span>
            <div
              className="w-full rounded-t-sm bg-gray-800"
              style={{ height: `${Math.max(heightPct, b.count > 0 ? 4 : 0)}%` }}
            />
            <span className="text-xs text-gray-400 whitespace-nowrap">{b.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function Statistics({ data }: { data: ExamResults }) {
  const students = data.student_results;
  if (students.length === 0) {
    return <p className="text-sm text-gray-400">No data yet.</p>;
  }

  const percentages = students.map((s) => pct(s.total_score, s.max_total));
  const rawScores = students.map((s) => s.total_score);
  const maxTotal = students[0]?.max_total ?? 0;

  const classMean = mean(percentages);
  const classMedian = median(percentages);
  const classSD = stddev(percentages);
  const highest = Math.max(...percentages);
  const lowest = Math.min(...percentages);

  // Distribution buckets: 0–10, 10–20, …, 90–100
  const bucketLabels = ["0–10", "10–20", "20–30", "30–40", "40–50",
                        "50–60", "60–70", "70–80", "80–90", "90–100"];
  const bucketCounts = Array(10).fill(0);
  percentages.forEach((p) => {
    const idx = Math.min(Math.floor(p / 10), 9);
    bucketCounts[idx]++;
  });
  const buckets = bucketLabels.map((label, i) => ({ label, count: bucketCounts[i] }));
  const maxBucketCount = Math.max(...bucketCounts, 1);

  // Per-question stats
  const allQids = Array.from(
    new Set(students.flatMap((s) => s.questions.map((q) => q.question_id)))
  ).sort();

  const qStats = allQids.map((qid) => {
    const qs = students.flatMap((s) => s.questions.filter((q) => q.question_id === qid));
    const scores = qs.map((q) => q.final_score ?? q.ai_score);
    const maxPossible = qs[0]?.max_score ?? 0;
    const avg = mean(scores);
    return { qid, avg, maxPossible, avgPct: pct(avg, maxPossible) };
  });

  return (
    <div className="space-y-8">
      {/* Summary cards */}
      <div>
        <h2 className="text-sm font-medium text-gray-700 mb-3">Class summary</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <StatCard label="Students" value={String(students.length)} />
          <StatCard label="Mean" value={`${fmt(classMean)}%`} sub={`${fmt(mean(rawScores))} / ${fmt(maxTotal)} pts`} />
          <StatCard label="Median" value={`${fmt(classMedian)}%`} />
          <StatCard label="Std dev" value={`${fmt(classSD)}%`} />
          <StatCard label="Range" value={`${fmt(lowest)}–${fmt(highest)}%`} />
        </div>
      </div>

      {/* Score distribution */}
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-medium text-gray-700 mb-4">Score distribution (%)</h2>
        <DistributionBar buckets={buckets} maxCount={maxBucketCount} />
      </div>

      {/* Per-question breakdown */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <h2 className="text-sm font-medium text-gray-700">Per-question averages</h2>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-5 py-2.5 font-medium text-gray-600">Question</th>
              <th className="text-right px-5 py-2.5 font-medium text-gray-600">Avg score</th>
              <th className="text-right px-5 py-2.5 font-medium text-gray-600">Max</th>
              <th className="text-right px-5 py-2.5 font-medium text-gray-600">Avg %</th>
              <th className="px-5 py-2.5 text-gray-600">Performance</th>
            </tr>
          </thead>
          <tbody>
            {qStats.map(({ qid, avg, maxPossible, avgPct }) => (
              <tr key={qid} className="border-t border-gray-50 hover:bg-gray-50">
                <td className="px-5 py-3 font-medium text-gray-900">{qid}</td>
                <td className="px-5 py-3 text-right text-gray-700">{fmt(avg)}</td>
                <td className="px-5 py-3 text-right text-gray-400">{maxPossible}</td>
                <td className="px-5 py-3 text-right text-gray-700">{fmt(avgPct)}%</td>
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-gray-100 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${avgPct >= 70 ? "bg-green-500" : avgPct >= 40 ? "bg-amber-400" : "bg-red-400"}`}
                        style={{ width: `${avgPct}%` }}
                      />
                    </div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GradesTable({ data }: { data: ExamResults }) {
  const allQuestionIds = Array.from(
    new Set(data.student_results.flatMap((s) => s.questions.map((q) => q.question_id)))
  ).sort();

  return (
    <>
      {data.reviewed_regions < data.total_regions && (
        <div className="mb-4 bg-amber-50 border border-amber-200 rounded-md px-4 py-3 text-sm text-amber-800">
          {data.total_regions - data.reviewed_regions} region(s) not yet reviewed — AI estimate shown for those.
        </div>
      )}
      <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              <th className="text-left px-4 py-3 font-medium text-gray-700 whitespace-nowrap">Student</th>
              {allQuestionIds.map((qid) => (
                <th key={qid} className="text-center px-3 py-3 font-medium text-gray-700 whitespace-nowrap">{qid}</th>
              ))}
              <th className="text-right px-4 py-3 font-medium text-gray-700 whitespace-nowrap">Total</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700 whitespace-nowrap">%</th>
            </tr>
          </thead>
          <tbody>
            {data.student_results.map((student) => {
              const byQid = Object.fromEntries(student.questions.map((q) => [q.question_id, q]));
              const p = student.max_total > 0
                ? Math.round((student.total_score / student.max_total) * 100)
                : 0;
              return (
                <tr key={student.student_identifier} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-4 py-3 whitespace-nowrap">
                    {(() => {
                      const parts = student.student_identifier.split(" — ");
                      return parts.length === 2 ? (
                        <div>
                          <p className="font-medium text-gray-900">{parts[0]}</p>
                          <p className="text-xs text-gray-500">{parts[1]}</p>
                        </div>
                      ) : (
                        <p className="font-medium text-gray-900">{student.student_identifier}</p>
                      );
                    })()}
                    {student.pending_count > 0 && (
                      <span className="text-xs text-amber-600">({student.pending_count} pending)</span>
                    )}
                  </td>
                  {allQuestionIds.map((qid) => {
                    const q = byQid[qid];
                    if (!q) return <td key={qid} className="px-3 py-3 text-center text-gray-300">—</td>;
                    const displayed = q.final_score ?? q.ai_score;
                    return (
                      <td key={qid} className="px-3 py-3 text-center">
                        <div className="flex flex-col items-center gap-1">
                          <span className="font-medium text-gray-800">{displayed}/{q.max_score}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded-full ${STATUS_BADGE[q.status] ?? STATUS_BADGE.pending}`}>
                            {q.status}
                          </span>
                        </div>
                      </td>
                    );
                  })}
                  <td className="px-4 py-3 text-right font-semibold text-gray-900 whitespace-nowrap">
                    {student.total_score}/{student.max_total}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 whitespace-nowrap">{p}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data.student_results.length === 0 && (
          <div className="p-12 text-center text-sm text-gray-400">No graded regions found yet.</div>
        )}
      </div>
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Tab = "grades" | "statistics";

export default function ExamResults() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<Tab>("grades");

  const { data, isLoading } = useQuery<ExamResults>({
    queryKey: ["results", id],
    queryFn: () => api.get(`/exams/${id}/results`).then((r) => r.data),
  });

  if (isLoading) {
    return <Layout><p className="text-sm text-gray-400">Loading results…</p></Layout>;
  }
  if (!data) return null;

  return (
    <Layout>
      <div className="max-w-5xl">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">{data.exam_title}</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {data.reviewed_regions}/{data.total_regions} regions reviewed
            </p>
          </div>
          <Link
            to={`/review/${id}`}
            className="text-sm text-gray-600 hover:text-gray-900 border border-gray-200 px-3 py-1.5 rounded-md hover:bg-gray-50"
          >
            ← Back to review queue
          </Link>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 border-b border-gray-200">
          {(["grades", "statistics"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium capitalize -mb-px border-b-2 transition-colors ${
                tab === t
                  ? "border-gray-900 text-gray-900"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === "grades" ? <GradesTable data={data} /> : <Statistics data={data} />}
      </div>
    </Layout>
  );
}
