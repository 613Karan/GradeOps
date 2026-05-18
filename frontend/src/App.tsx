import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ProtectedRoute, { InstructorRoute } from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import NewCourse from "./pages/NewCourse";
import NewExam from "./pages/NewExam";
import ExamStatus from "./pages/ExamStatus";
import ReviewQueue from "./pages/ReviewQueue";
import ExamResults from "./pages/ExamResults";
import SplitReview from "./pages/SplitReview";
import CourseExams from "./pages/CourseExams";

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/courses/new" element={<InstructorRoute><NewCourse /></InstructorRoute>} />
          <Route path="/courses/:id" element={<ProtectedRoute><CourseExams /></ProtectedRoute>} />
          <Route path="/exams/new" element={<InstructorRoute><NewExam /></InstructorRoute>} />
          <Route path="/exams/:id" element={<ProtectedRoute><ExamStatus /></ProtectedRoute>} />
          <Route path="/exams/:id/splits" element={<ProtectedRoute><SplitReview /></ProtectedRoute>} />
          <Route path="/review/:examId" element={<ProtectedRoute><ReviewQueue /></ProtectedRoute>} />
          <Route path="/exams/:id/results" element={<ProtectedRoute><ExamResults /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
