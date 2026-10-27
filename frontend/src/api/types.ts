export const EXERCISES = ["squat", "lunge", "push_up", "biceps_curl", "shoulder_press"] as const;
export type ExerciseSlug = (typeof EXERCISES)[number];

export const GOALS = ["general_fitness", "weight_management", "muscle_gain", "endurance", "mobility"] as const;
export const EXPERIENCE = ["beginner", "intermediate", "advanced"] as const;
export const EQUIPMENT = ["dumbbells", "resistance_band"] as const;
export const HEALTH_FLAGS = ["injury", "chronic_condition", "pregnancy", "eating_disorder_history", "special_diet"] as const;
export const DIETS = ["vegetarian", "vegan", "gluten_free"] as const;
export const ALLERGENS = ["milk", "egg", "fish", "shellfish", "tree_nuts", "peanuts", "wheat", "soy", "sesame"] as const;
export const MEAL_CATEGORIES = ["breakfast", "lunch", "dinner", "snack"] as const;
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export interface Profile {
  display_name: string | null;
  age: number | null;
  sex: "female" | "male" | "unspecified";
  height_cm: number | null;
  weight_kg: number | null;
  goal: (typeof GOALS)[number];
  experience: (typeof EXPERIENCE)[number];
  equipment: string[];
  days_per_week: number;
  preferred_days: number[];
  session_minutes: number;
  exclusions: string[];
  dietary_preferences: string[];
  allergies: string[];
  health_flags: string[];
  safety_acknowledged_at: string | null;
  updated_at: string;
}

export type ProfileInput = Omit<Profile, "safety_acknowledged_at" | "updated_at">;

export interface User {
  id: number;
  email: string;
  is_guest: boolean;
  created_at: string;
  profile: Profile | null;
}

export interface Exercise {
  id: number;
  slug: ExerciseSlug;
  name: string;
  difficulty: string;
  muscle_group: string;
  equipment: string[];
  instructions: string[];
  form_cues: string[];
  substitutions: string[];
  safety_note: string;
}

export interface PlannedExercise {
  id: number;
  day_index: number;
  order_index: number;
  sets: number;
  repetitions: number;
  rest_seconds: number;
  practice_mode: boolean;
  notes: string;
  exercise: Exercise;
}

export interface PlanDay {
  day_index: number;
  weekday: number;
  weekday_name: string;
  exercises: PlannedExercise[];
}

export interface Plan {
  id: number;
  goal: string;
  template: string;
  start_date: string;
  status: string;
  version: number;
  parent_plan_id: number | null;
  generated_reason: string;
  warnings: string[];
  days_per_week: number;
  schedule: number[];
  created_at: string;
  days: PlanDay[];
}

export interface TodayWorkout {
  date: string;
  plan_id: number;
  is_training_day: boolean;
  day: PlanDay | null;
  next_training_date: string | null;
  completed_today: boolean;
}

export interface FormFeedback {
  error_type: string;
  message: string;
  confidence: number | null;
  occurrences: number;
  source: string;
}

export interface ExerciseResult {
  id: number;
  exercise_slug: ExerciseSlug;
  exercise_name: string;
  planned_sets: number;
  planned_repetitions: number;
  repetitions: number;
  partial_repetitions: number;
  completion_rate: number;
  form_score: number | null;
  error_count: number;
  difficulty_rating: number | null;
  source: "live" | "manual" | "none";
  feedback: FormFeedback[];
}

export interface WorkoutSession {
  id: number;
  plan_id: number | null;
  day_index: number | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  completion_rate: number | null;
  form_score: number | null;
  session_score: number | null;
  perceived_difficulty: number | null;
  ended_early: boolean;
  score_breakdown: Record<string, unknown>;
  inference_stats: Record<string, number | null>;
  results: ExerciseResult[];
}

export interface AdaptationDecision {
  exercise_slug: string | null;
  action: string;
  reason: string;
  changes: Record<string, { from: unknown; to: unknown }>;
}

export interface SessionCompleteResponse {
  session: WorkoutSession;
  adaptation_applied: boolean;
  new_plan_id: number | null;
  decisions: AdaptationDecision[];
  guidance: string[];
}

export interface ExerciseLiveTotals {
  exercise: ExerciseSlug;
  repetitions: number;
  partial_repetitions: number;
  rep_attempts: number;
  good_reps: number;
  form_score: number | null;
  error_counts: Record<string, number>;
  sets_recorded: number;
}

export interface ProgressSummary {
  sessions_completed: number;
  total_repetitions: number;
  average_completion_rate: number | null;
  average_form_score: number | null;
  average_session_score: number | null;
  consistency_score: number;
  consistency_window_days: number;
  missed_sessions_last_7_days: number;
  last_session_at: string | null;
  latest_feedback: string[];
  session_series: {
    session_id: number;
    date: string;
    completion_rate: number | null;
    form_score: number | null;
    session_score: number | null;
    repetitions: number;
    duration_seconds: number | null;
  }[];
  exercise_series: Record<string, { session_id: number; date: string; repetitions: number; form_score: number | null; completion_rate: number }[]>;
  error_frequency: Record<string, number>;
  weight_series: { date: string; weight_kg: number }[];
}

export interface AdaptationEvent {
  id: number;
  session_id: number | null;
  old_plan_id: number | null;
  new_plan_id: number | null;
  reason: string;
  details: { actions?: string[]; decisions?: AdaptationDecision[]; guidance?: string[]; session_score?: number };
  created_at: string;
}

export interface ProgressHistory {
  sessions: WorkoutSession[];
  adaptations: AdaptationEvent[];
}

export interface FoodItem {
  id: number;
  name: string;
  serving_size: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  allergens: string[];
  tags: string[];
  meal_category: string;
}

export interface FoodList {
  total: number;
  items: FoodItem[];
  disclaimer: string;
}

export interface MealGuidance {
  id: number;
  date: string;
  goal: string;
  calorie_min: number | null;
  calorie_max: number | null;
  calorie_explanation: string;
  protein_guidance: string;
  meal_tips: string[];
  applied_filters: { diet: string | null; exclude_allergens: string[] };
  suggested_foods: Record<string, FoodItem[]>;
  professional_referral: boolean;
  disclaimer: string;
}

export interface ModelDescription {
  available: boolean;
  status: string;
  model_type: string | null;
  labels: string[];
  sequence_length: number | null;
}

export interface ModelStatus {
  exercise_classifier: ModelDescription;
  form_classifiers: Record<string, ModelDescription>;
}

export interface Notices {
  safety: string;
  privacy: string;
  nutrition: string;
}

/** Message returned by the live inference WebSocket for every frame. */
export interface LiveAnalysis {
  type: "analysis";
  expected_exercise: ExerciseSlug;
  exercise: string;
  confidence: number | null;
  recognition_source: "model" | "user_selected";
  repetition_count: number;
  partial_repetitions: number;
  phase: string;
  angle: number | null;
  form_status: "not_started" | "good" | "minor_error" | "major_error" | "uncertain";
  form_source: string;
  active_errors: string[];
  feedback: string;
  visible: boolean;
  /** False until the counter has learned this user's range of motion. */
  calibrated: boolean;
  form_score: number | null;
  processing_ms: number;
  timestamp_ms: number | null;
}

export interface LiveSetSummary {
  type: "summary";
  set_summary: {
    exercise: ExerciseSlug;
    repetitions: number;
    partial_repetitions: number;
    rep_attempts: number;
    good_reps: number;
    form_score: number | null;
    error_counts: Record<string, number>;
    frames: number;
    avg_processing_ms: number | null;
    low_visibility_ratio: number | null;
  };
  session_exercise_totals: ExerciseLiveTotals | null;
}

export const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
