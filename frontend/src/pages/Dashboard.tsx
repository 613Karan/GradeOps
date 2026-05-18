import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Course } from "../api/types";
import Layout from "../components/Layout";
import { useAuth } from "../hooks/useAuth";

export default function Dashboard() {
  const { currentRole } = useAuth();
  const role = currentRole();

  const { data: courses = [], isLoading } = useQuery<Course[]>({
    queryKey: ["courses"],
    queryFn: () => api.get("/courses/").then((r) => r.data),
  });

  return (
    <Layout>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Courses</h1>
        {role === "instructor" && (
          <Link
            to="/courses/new"
            className="bg-gray-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800"
          >
            New course
          </Link>
        )}
      </div>

      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}

      {!isLoading && courses.length === 0 && (
        <div className="border border-dashed border-gray-300 rounded-lg p-12 text-center">
          <p className="text-gray-500 text-sm">No courses yet.</p>
          {role === "instructor" && (
            <Link to="/courses/new" className="mt-2 inline-block text-sm text-gray-900 font-medium hover:underline">
              Create your first course →
            </Link>
          )}
        </div>
      )}

      <div className="grid gap-3">
        {courses.map((course) => (
          <Link
            key={course.id}
            to={`/courses/${course.id}`}
            className="bg-white border border-gray-200 rounded-lg p-5 flex items-center justify-between hover:border-gray-300 hover:shadow-sm transition-all"
          >
            <div>
              <p className="font-medium text-gray-900">{course.name}</p>
              <p className="text-sm text-gray-500">{course.code}</p>
            </div>
            <span className="text-sm text-gray-400">View exams →</span>
          </Link>
        ))}
      </div>
    </Layout>
  );
}
