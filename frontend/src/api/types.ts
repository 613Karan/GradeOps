export interface Course {
  id: string;
  code: string;
  name: string;
  instructor_id: string;
  created_at: string;
}

export type ExamStatus =
  | "uploaded"
  | "splitting"
  | "split_done"
  | "ocr_running"
  | "ocr_done"
  | "grading"
  | "graded"
  | "review"
  | "completed"
  | "failed";

export interface RubricQuestion {
  question_id: string;
  question_text: string;
  max_marks: number;
}

export interface Exam {
  id: string;
  title: string;
  course_id: string;
  status: ExamStatus;
  file_path: string | null;
  page_count: number | null;
  rubric: { questions: RubricQuestion[] } | null;
  created_at: string;
}

export interface StepResult {
  step_id: string;
  description: string;
  max_points: number;
  awarded_points: number;
  verdict: "correct" | "partial" | "incorrect";
  justification: string;
}

export interface AnswerRegionRead {
  id: string;
  exam_id: string;
  student_identifier: string;
  question_id: string;
  crop_path: string | null;
  status: string;
  transcript_text: string | null;
  content_type: string;
  created_at: string;
}

export interface GradeRead {
  id: string;
  answer_region_id: string;
  ai_score: number;
  max_score: number;
  final_score: number | null;
  step_results: StepResult[] | null;
  overall_justification: string | null;
  override_reason: string | null;
  plagiarism_flagged: boolean;
}

export interface ReviewItem {
  answer_region: AnswerRegionRead;
  grade: GradeRead;
  crop_path: string | null;
  transcript_text: string | null;
  overall_justification: string | null;
  step_results: StepResult[];
}
