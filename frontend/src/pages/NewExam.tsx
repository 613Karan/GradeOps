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
  pdf_file: FileList;
  answer_key_pdf: FileList;
}

// ── Rubric builder types ──────────────────────────────────────────────────────

interface LogicStep {
  description: string;
  points: number;
}

interface RubricQuestion {
  question_text: string;
  logic_steps: LogicStep[];
}

function makeQuestion(): RubricQuestion {
  return { question_text: "", logic_steps: [{ description: "", points: 1 }] };
}

function serializeRubric(questions: RubricQuestion[]): string {
  return JSON.stringify({
    questions: questions.map((q, qi) => ({
      question_id: `q${qi + 1}`,
      question_text: q.question_text,
      max_marks: q.logic_steps.reduce((sum, s) => sum + (Number(s.points) || 0), 0),
      logic_steps: q.logic_steps.map((s, si) => ({
        id: `step_${si + 1}`,
        description: s.description,
        points: Number(s.points) || 0,
      })),
    })),
  });
}

// ── Rubric builder component ──────────────────────────────────────────────────

function RubricBuilder({
  questions,
  onChange,
}: {
  questions: RubricQuestion[];
  onChange: (q: RubricQuestion[]) => void;
}) {
  function updateQuestion(qi: number, patch: Partial<RubricQuestion>) {
    const next = questions.map((q, i) => (i === qi ? { ...q, ...patch } : q));
    onChange(next);
  }

  function removeQuestion(qi: number) {
    onChange(questions.filter((_, i) => i !== qi));
  }

  function addStep(qi: number) {
    const next = questions.map((q, i) =>
      i === qi
        ? { ...q, logic_steps: [...q.logic_steps, { description: "", points: 1 }] }
        : q
    );
    onChange(next);
  }

  function updateStep(qi: number, si: number, patch: Partial<LogicStep>) {
    const next = questions.map((q, i) =>
      i === qi
        ? {
            ...q,
            logic_steps: q.logic_steps.map((s, j) => (j === si ? { ...s, ...patch } : s)),
          }
        : q
    );
    onChange(next);
  }

  function removeStep(qi: number, si: number) {
    const next = questions.map((q, i) =>
      i === qi ? { ...q, logic_steps: q.logic_steps.filter((_, j) => j !== si) } : q
    );
    onChange(next);
  }

  return (
    <div className="space-y-4">
      {questions.map((q, qi) => {
        const total = q.logic_steps.reduce((sum, s) => sum + (Number(s.points) || 0), 0);
        return (
          <div key={qi} className="border border-gray-200 rounded-lg overflow-hidden">
            {/* Question header */}
            <div className="flex items-center justify-between bg-gray-50 px-4 py-2.5 border-b border-gray-200">
              <span className="text-sm font-semibold text-gray-700">Q{qi + 1}</span>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400">{total} pt{total !== 1 ? "s" : ""} total</span>
                {questions.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeQuestion(qi)}
                    className="text-xs text-red-500 hover:text-red-700"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>

            <div className="p-4 space-y-3">
              {/* Question text */}
              <input
                type="text"
                value={q.question_text}
                onChange={(e) => updateQuestion(qi, { question_text: e.target.value })}
                placeholder="Question text (e.g. Derive the escape velocity formula)"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-gray-900"
              />

              {/* Steps */}
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-500">Grading steps</p>
                {q.logic_steps.map((step, si) => (
                  <div key={si} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={step.description}
                      onChange={(e) => updateStep(qi, si, { description: e.target.value })}
                      placeholder={`Step ${si + 1} description`}
                      className="flex-1 border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-gray-900"
                    />
                    <input
                      type="number"
                      min={0}
                      step={0.5}
                      value={step.points}
                      onChange={(e) => updateStep(qi, si, { points: parseFloat(e.target.value) || 0 })}
                      className="w-20 border border-gray-300 rounded-md px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-1 focus:ring-gray-900"
                      title="Points for this step"
                    />
                    <span className="text-xs text-gray-400 w-4">pt{step.points !== 1 ? "s" : ""}</span>
                    {q.logic_steps.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeStep(qi, si)}
                        className="text-gray-300 hover:text-red-500 text-lg leading-none"
                        title="Remove step"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => addStep(qi)}
                  className="text-xs text-gray-500 hover:text-gray-800 mt-1"
                >
                  + Add step
                </button>
              </div>
            </div>
          </div>
        );
      })}

      <button
        type="button"
        onClick={() => onChange([...questions, makeQuestion()])}
        className="w-full border border-dashed border-gray-300 rounded-lg py-2.5 text-sm text-gray-500 hover:border-gray-400 hover:text-gray-700 transition-colors"
      >
        + Add question
      </button>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NewExam() {
  const { register, handleSubmit, formState: { errors } } = useForm<Fields>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [questions, setQuestions] = useState<RubricQuestion[]>([makeQuestion()]);
  const [rubricError, setRubricError] = useState<string | null>(null);

  const { data: courses = [] } = useQuery<Course[]>({
    queryKey: ["courses"],
    queryFn: () => api.get("/courses/").then((r) => r.data),
  });

  function validateRubric(): string | null {
    for (let qi = 0; qi < questions.length; qi++) {
      const q = questions[qi];
      if (!q.question_text.trim()) return `Q${qi + 1}: question text is required`;
      if (q.logic_steps.length === 0) return `Q${qi + 1}: add at least one grading step`;
      for (let si = 0; si < q.logic_steps.length; si++) {
        if (!q.logic_steps[si].description.trim())
          return `Q${qi + 1} step ${si + 1}: description is required`;
      }
      const total = q.logic_steps.reduce((sum, s) => sum + (Number(s.points) || 0), 0);
      if (total <= 0) return `Q${qi + 1}: total points must be greater than 0`;
    }
    return null;
  }

  async function onSubmit(data: Fields) {
    setRubricError(null);
    const validationError = validateRubric();
    if (validationError) {
      setRubricError(validationError);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("title", data.title);
      form.append("course_id", data.course_id);
      form.append("is_math_subject", String(data.is_math_subject ?? false));
      form.append("rubric_json", serializeRubric(questions));
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
            <label className="block text-sm font-medium text-gray-700 mb-2">Rubric</label>
            <RubricBuilder questions={questions} onChange={setQuestions} />
            {rubricError && <p className="text-xs text-red-600 mt-2">{rubricError}</p>}
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
