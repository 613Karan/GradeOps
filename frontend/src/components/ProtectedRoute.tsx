import { Navigate } from "react-router-dom";

function getRole(): string | null {
  const token = localStorage.getItem("token");
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split(".")[1])).role ?? null;
  } catch {
    return null;
  }
}

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!localStorage.getItem("token")) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function InstructorRoute({ children }: { children: React.ReactNode }) {
  if (!localStorage.getItem("token")) return <Navigate to="/login" replace />;
  if (getRole() !== "instructor") return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
