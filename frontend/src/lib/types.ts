/** Mirrors the Pydantic models in backend/models/. Keep in sync. */

export type TopicState = "new" | "weak" | "mastered";

export type Verdict = "correct" | "partial" | "wrong" | "dont_know" | "unclear";

export interface User {
  user_id: number;
  name: string;
  email: string;
}

export interface DocumentSummary {
  document_id: number;
  filename: string;
  status: "pending" | "processing" | "ready" | "failed";
  created_at: string | null;
  total_topics: number;
  covered_topics: number;
  session_count: number;
}

export interface DocumentStatus {
  document_id: number;
  filename: string;
  status: string;
  error: string | null;
  created_at: string | null;
  processed_at: string | null;
  chunk_count: number;
  question_count: number;
}

export interface NewChatResponse {
  document_id: number;
  filename: string;
  status: string;
  /** True when an identical PDF was already ingested - no re-processing. */
  already_seen: boolean;
  covered_topic_count: number | null;
  total_topic_count: number | null;
}

export interface TopicInfo {
  topic: string;
  parent: string | null;
  question_count: number;
  /** False when no questions were generated - the topic cannot be quizzed. */
  quizzable: boolean;
  covered: boolean;
  times_asked: number;
  correct_count: number;
  /** null (not 0) when never attempted. The two are different states. */
  accuracy: number | null;
  state: TopicState;
}

/** An unfinished session on this document, so the picker can offer to
 *  resume it instead of silently starting a new one on top. */
export interface ActiveSessionInfo {
  session_id: number;
  current_topic: string;
  questions_asked: number;
  total_questions: number;
  started_at: string | null;
}

export interface DocumentTopicsResponse {
  document_id: number;
  filename: string;
  status: string;
  total_topics: number;
  covered_topics: number;
  topics: TopicInfo[];
  active_session: ActiveSessionInfo | null;
}

export interface QuestionOut {
  question_id: number;
  question_text: string;
  topic: string;
  difficulty: number;
  turn_index: number;
}

export interface StartSessionResponse {
  session_id: number;
  document_id: number;
  filename: string;
  selected_topics: string[];
  total_questions: number;
  current_topic: string;
  question: QuestionOut;
}

export interface AnswerResponse {
  verdict: Verdict;
  matched_points: string[];
  missed_points: string[];
  confidence: number;
  coach_reply: string;
  score: number;
  level: number;
  current_topic: string;
  questions_asked: number;
  correct_count: number;
  topic_changed: boolean;
  session_complete: boolean;
  next_question: QuestionOut | null;
}

export interface SkipResponse {
  coach_reply: string;
  skipped: boolean;
  current_topic: string;
  next_question: QuestionOut | null;
}

export interface TurnOut {
  turn_index: number;
  topic: string;
  question_text: string;
  ideal_answer: string;
  transcript: string | null;
  verdict: Verdict | null;
  missed_points: string[];
  coach_reply: string | null;
  level_at_ask: number;
  asked_at: string | null;
}

export interface SessionReplayResponse {
  session_id: number;
  document_id: number;
  filename: string;
  status: string;
  selected_topics: string[];
  questions_asked: number;
  correct_count: number;
  started_at: string | null;
  ended_at: string | null;
  turns: TurnOut[];
}

export interface SessionListItem {
  session_id: number;
  status: string;
  questions_asked: number;
  correct_count: number;
  started_at: string | null;
  ended_at: string | null;
  selected_topics: string[];
}

export interface TopicResult {
  topic: string;
  parent: string | null;
  asked: number;
  correct: number;
  partial: number;
  missed: number;
  accuracy: number;
  /** All null when the topic was never attempted in an earlier session. */
  previous_accuracy: number | null;
  previous_correct: number | null;
  previous_asked: number | null;
  improved: boolean | null;
}

export interface SummaryResponse {
  session_id: number;
  filename: string;
  status: string;
  questions_asked: number;
  correct_count: number;
  overall_accuracy: number;
  duration_seconds: number | null;
  topic_results: TopicResult[];
  weak_topics: string[];
  narrative: string | null;
  remaining_topics: string[];
  /** Median grading latency across answered turns. */
  avg_response_ms: number | null;
  avg_stt_ms: number | null;
  /** True when this session revisited a previously attempted topic. */
  has_comparison: boolean;
}
