import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import Layout from "../components/Layout";
import { useState } from "react";

interface Fields {
  code: string;
  name: string;
}

export default function NewCourse() {
  const { register, handleSubmit } = useForm<Fields>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(data: Fields) {
    setLoading(true);
    setError(null);
    try {
      await api.post("/courses/", data);
      navigate("/dashboard");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Failed to create course");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <div className="max-w-lg">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">New course</h1>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 bg-white border border-gray-200 rounded-lg p-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Course code</label>
            <input
              {...register("code", { required: true })}
              placeholder="CS101"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Course name</label>
            <input
              {...register("name", { required: true })}
              placeholder="Introduction to Computer Science"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 focus:border-transparent"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
            >
              {loading ? "Creating…" : "Create course"}
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
