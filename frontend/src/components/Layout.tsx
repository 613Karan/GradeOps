import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function Layout({ children }: { children: React.ReactNode }) {
  const { logout, currentRole } = useAuth();
  const navigate = useNavigate();
  const role = currentRole();

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/dashboard" className="font-semibold text-gray-900 tracking-tight">
            GradeOps
          </Link>
          <div className="flex items-center gap-6 text-sm">
            {role === "instructor" && (
              <>
                <Link to="/courses/new" className="text-gray-600 hover:text-gray-900">
                  New course
                </Link>
                <Link to="/exams/new" className="text-gray-600 hover:text-gray-900">
                  Upload exam
                </Link>
              </>
            )}
            <span className="text-gray-400">{role}</span>
            <button
              onClick={() => { logout(); navigate("/login"); }}
              className="text-gray-600 hover:text-gray-900"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>
      <main className="max-w-5xl mx-auto px-4 py-8">{children}</main>
    </div>
  );
}
