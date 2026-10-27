import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

import { api } from "./client";
import type {
  DietPlan, Exercise, FoodList, MealGuidance, ModelStatus, Notices, Plan, ProfileInput, ProgressHistory, ProgressSummary,
  SessionCompleteResponse, TodayWorkout, User, WorkoutSession,
} from "./types";

const get = <T,>(url: string, params?: object) => api.get<T>(url, { params }).then((r) => r.data);
const isNotFound = (e: unknown) => axios.isAxiosError(e) && e.response?.status === 404;

export const useMe = (enabled = true) => useQuery({ queryKey: ["me"], queryFn: () => get<User>("/api/users/me"), enabled });

export const useNotices = () =>
  useQuery({ queryKey: ["notices"], queryFn: () => get<Notices>("/api/meta/notices"), staleTime: Infinity });

export const useExercises = () =>
  useQuery({ queryKey: ["exercises"], queryFn: () => get<Exercise[]>("/api/workouts/exercises"), staleTime: Infinity });

/** Resolves to null (not an error) when the user has no plan yet. */
export const useActivePlan = () =>
  useQuery({
    queryKey: ["plan", "active"],
    queryFn: () => get<Plan>("/api/workouts/active").catch((e) => (isNotFound(e) ? null : Promise.reject(e))),
  });

export const useToday = () =>
  useQuery({
    queryKey: ["plan", "today"],
    queryFn: () => get<TodayWorkout>("/api/workouts/today").catch((e) => (isNotFound(e) ? null : Promise.reject(e))),
  });

export const usePlan = (planId: number | null) =>
  useQuery({ queryKey: ["plan", planId], queryFn: () => get<Plan>(`/api/workouts/${planId}`), enabled: planId != null });

export const useProgressSummary = () =>
  useQuery({ queryKey: ["progress", "summary"], queryFn: () => get<ProgressSummary>("/api/progress/summary") });

export const useProgressHistory = (limit = 50) =>
  useQuery({ queryKey: ["progress", "history", limit], queryFn: () => get<ProgressHistory>("/api/progress/history", { limit }) });

export const useModelStatus = () =>
  useQuery({ queryKey: ["models"], queryFn: () => get<ModelStatus>("/api/inference/status"), staleTime: 60_000 });

export interface FoodFilters {
  diet?: string;
  exclude_allergens?: string[];
  meal_category?: string;
  max_calories?: number;
  min_protein_g?: number;
  q?: string;
}

export const useFoods = (filters: FoodFilters) =>
  useQuery({
    queryKey: ["foods", filters],
    queryFn: () =>
      api
        .get<FoodList>("/api/nutrition/foods", { params: { ...filters, limit: 100 }, paramsSerializer: { indexes: null } })
        .then((r) => r.data),
    placeholderData: (prev) => prev,
  });

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (profile: ProfileInput) => api.put<User>("/api/users/me", profile).then((r) => r.data),
    onSuccess: (user) => qc.setQueryData(["me"], user),
  });
}

export function useGeneratePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Plan>("/api/workouts/generate").then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plan"] }),
  });
}

export function useAcknowledgeSafety() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/api/users/me/safety-acknowledgement"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export const useStartSession = () =>
  useMutation({
    mutationFn: (body: { plan_id?: number; day_index?: number }) =>
      api.post<WorkoutSession>("/api/sessions/start", body).then((r) => r.data),
  });

export interface CompletePayload {
  perceived_difficulty: number;
  ended_early: boolean;
  exercises: { exercise_slug: string; difficulty_rating?: number; manual_repetitions?: number }[];
}

export function useCompleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, body }: { sessionId: number; body: CompletePayload }) =>
      api.post<SessionCompleteResponse>(`/api/sessions/${sessionId}/complete`, body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plan"] });
      qc.invalidateQueries({ queryKey: ["progress"] });
    },
  });
}

export function useMealGuidance() {
  return useMutation({
    mutationFn: () => api.post<MealGuidance>("/api/nutrition/meal-guidance", {}).then((r) => r.data),
  });
}

export function useDietPlan() {
  return useMutation({
    mutationFn: (body: { days: number }) =>
      api.post<DietPlan>("/api/nutrition/diet-plan", body).then((r) => r.data),
  });
}

export function useSaveProgressRecord() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { date: string; weight_kg: number | null; notes: string }) => api.post("/api/progress/records", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["progress"] }),
  });
}

export const useDeleteData = () =>
  useMutation({
    mutationFn: (keepAccount: boolean) =>
      api.delete<{ account_deleted: boolean; deleted: Record<string, number> }>("/api/users/me/data", {
        params: { keep_account: keepAccount },
      }).then((r) => r.data),
  });
