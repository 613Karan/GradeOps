import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Course, Exam, ExamStatus } from "../api/types";
import Layout from "../components/Layout";
import { useAuth } from "../hooks/useAuth";

const STATUS_BADGE: Record<string, string> = {
  uploaded:   "bg-gray-100 text-gray-500",
  splitting:  "bg-blue-100 text-blue-600",
  split_done: "bg-amber-100 text-amber-700",
  ocr_running:"bg-blue-100 text-blue-600",
  ocr_done:   "bg-blue-100 text-blue-600",
  grading:    "bg-blue-100 text-blue-600",
  graded:     "bg-purple-100 text-purple-700",
  review:     "bg-amber-100 text-amber-700",
  completed:  "bg-green-100 text-green-700",
  failed:     "bg-red-100 text-red-600",
};

function actionFor(exam: Exam, role: string | null): React.ReactNode {
  const s = exam.status as ExamStatus;
  if (s === "split_done" && role !== "instructor") {
    return (
      <Link
        to={`/exams/${exam.id}/splits`}
        className="text-sm border border-gray-300 rounded-md px-3 py-1.5 text-gray-700 hover:bg-gray-50"
      >
        Mark regions →
      </Link>
    );
  }
  if (s === "review" || s === "graded" || s === "completed") {
    return (
      <Link
        to={`/review/${exam.id}`}
        className="text-sm border border-gray-300 rounded-md px-3 py-1.5 text-gray-700 hover:bg-gray-50"
      >
        Review queue →
      </Link>
    );
  }
  if (role === "instructor") {
    return (
      <Link
        to={`/exams/${exam.id}`}
        className="text-sm text-gray-400 hover:text-gray-600"
      >
        View status →
      </Link>
    );
  }
  return null;
}

export default function CourseExams() {
  const { id: courseId } = useParams<{ id: string }>();
  const { currentRole } = useAuth();
  const role = currentRole();

  const { data: course } = useQuery<Course>({
    queryKey: ["course", courseId],
    queryFn: () => api.get(`/courses/${courseId}`).then((r) => r.data),
  });

  const { data: exams = [], isLoading } = useQuery<Exam[]>({
    queryKey: ["course-exams", courseId],
    queryFn: () => api.get(`/courses/${courseId}/exams`).then((r) => r.data),
  });

  return (
    <Layout>
      <div className="max-w-3xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-sm text-gray-500 mb-0.5">
              <Link to="/dashboard" className="hover:underline">Courses</Link> /
            </p>
            <h1 className="text-2xl font-semibold text-gray-900">
              {course ? `${course.code} — ${course.name}` : "Loading…"}
            </h1>
          </div>
          {role === "instructor" && (
            <Link
              to={`/exams/new?course_id=${courseId}`}
              className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800"
            >
              Upload exam
            </Link>
          )}
        </div>

        {isLoading && <p className="text-sm text-gray-400">Loading exams…</p>}

        {!isLoading && exams.length === 0 && (
          <div className="border border-dashed border-gray-300 rounded-lg p-12 text-center">
            <p className="text-gray-500 text-sm">No exams uploaded yet.</p>
          </div>
        )}

        <div className="grid gap-3">
          {exams.map((exam) => (
            <div
              key={exam.id}
              className="bg-white border border-gray-200 rounded-lg p-5 flex items-center justify-between"
            >
              <div>
                <p className="font-medium text-gray-900">{exam.title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[exam.status] ?? STATUS_BADGE.uploaded}`}
                  >
                    {exam.status.replace(/_/g, " ")}
                  </span>
                  {exam.student_count != null && (
                    <span className="text-xs text-gray-400">
                      {exam.student_count} student{exam.student_count !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>
              {actionFor(exam, role)}
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
