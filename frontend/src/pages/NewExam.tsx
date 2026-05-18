import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Course } from "../api/types";
import Layout from "../components/Layout";
import { useState } from "react";

interface Fields {
  title: string;
  course_id: string;
  is_math_subject: boolean;
  rubric_json: string;
  pdf_file: FileList;
  answer_key_pdf: FileList;
}

const RUBRIC_PLACEHOLDER = JSON.stringify(
  {
    questions: [
      {
        question_id: "q1",
        question_text: "Explain Newton's second law",
        max_marks: 5,
        logic_steps: [
          { id: "step_1", description: "State F = ma", points: 1 },
          { id: "step_2", description: "Define each variable", points: 2 },
          { id: "step_3", description: "Provide a worked example", points: 2 },
        ],
      },
    ],
  },
  null,
  2
);

export default function NewExam() {
  const { register, handleSubmit, formState: { errors } } = useForm<Fields>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: courses = [] } = useQuery<Course[]>({
    queryKey: ["courses"],
    queryFn: () => api.get("/courses/").then((r) => r.data),
  });

  async function onSubmit(data: Fields) {
    setLoading(true);
    setError(null);
    try {
      // Validate rubric JSON before sending
      JSON.parse(data.rubric_json);
    } catch {
      setError("Rubric JSON is not valid");
      setLoading(false);
      return;
    }

    try {
      const form = new FormData();
      form.append("title", data.title);
      form.append("course_id", data.course_id);
      form.append("is_math_subject", String(data.is_math_subject ?? false));
      form.append("rubric_json", data.rubric_json);
      form.append("pdf_file", data.pdf_file[0]);
      if (data.answer_key_pdf?.[0]) {
        form.append("answer_key_pdf", data.answer_key_pdf[0]);
      }

      const { data: exam } = await api.post("/exams/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      navigate(`/exams/${exam.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  const defaultCourse = searchParams.get("course_id") ?? "";

  return (
    <Layout>
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">Upload exam</h1>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 bg-white border border-gray-200 rounded-lg p-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <input
              {...register("title", { required: true })}
              placeholder="Midterm Exam 1"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
            />
            {errors.title && <p className="text-xs text-red-600 mt-1">Required</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Course</label>
            <select
              {...register("course_id", { required: true })}
              defaultValue={defaultCourse}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
            >
              <option value="">Select a course…</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
            {errors.course_id && <p className="text-xs text-red-600 mt-1">Required</p>}
          </div>

          <div className="flex items-start gap-3 p-3 bg-gray-50 border border-gray-200 rounded-md">
            <input
              type="checkbox"
              id="is_math_subject"
              {...register("is_math_subject")}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 text-gray-900 focus:ring-gray-900"
            />
            <div>
              <label htmlFor="is_math_subject" className="text-sm font-medium text-gray-700 cursor-pointer">
                Math-heavy subject
              </label>
              <p className="text-xs text-gray-400 mt-0.5">
                Routes OCR to Gemini Flash for better transcription of equations, derivations, and LaTeX notation.
              </p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Exam PDF</label>
            <input
              type="file"
              accept="application/pdf"
              {...register("pdf_file", { required: true })}
              className="w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
            />
            {errors.pdf_file && <p className="text-xs text-red-600 mt-1">Required</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Answer key PDF{" "}
              <span className="font-normal text-gray-400">(optional — enables RAG grading)</span>
            </label>
            <input
              type="file"
              accept="application/pdf"
              {...register("answer_key_pdf")}
              className="w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Rubric <span className="font-normal text-gray-400">(JSON)</span>
            </label>
            <textarea
              {...register("rubric_json", { required: true })}
              rows={14}
              defaultValue={RUBRIC_PLACEHOLDER}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-gray-900"
            />
            {errors.rubric_json && <p className="text-xs text-red-600 mt-1">Required</p>}
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-3 pt-1">
            <button
              type="submit"
              disabled={loading}
              className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
            >
              {loading ? "Uploading…" : "Upload & grade"}
            </button>
            <button
              type="button"
              onClick={() => navigate("/dashboard")}
              className="text-gray-600 px-4 py-2 rounded-md text-sm hover:bg-gray-100"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </Layout>
  );
}
