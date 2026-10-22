import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedLayout } from "./components/Layout";
import { Spinner } from "./components/ui";
import AuthPage from "./pages/AuthPage";
import DashboardPage from "./pages/DashboardPage";

// Heavy pages (MediaPipe, charts) are split into separate chunks.
const DataCollectionPage = lazy(() => import("./pages/DataCollectionPage"));
const LiveSessionPage = lazy(() => import("./pages/LiveSessionPage"));
const NutritionPage = lazy(() => import("./pages/NutritionPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ProgressPage = lazy(() => import("./pages/ProgressPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const WorkoutPlanPage = lazy(() => import("./pages/WorkoutPlanPage"));

const page = (el: React.ReactNode) => <Suspense fallback={<Spinner />}>{el}</Suspense>;

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route element={<ProtectedLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="/profile" element={page(<ProfilePage />)} />
        <Route path="/plan" element={page(<WorkoutPlanPage />)} />
        <Route path="/session" element={page(<LiveSessionPage />)} />
        <Route path="/progress" element={page(<ProgressPage />)} />
        <Route path="/nutrition" element={page(<NutritionPage />)} />
        <Route path="/settings" element={page(<SettingsPage />)} />
        <Route path="/data-collection" element={page(<DataCollectionPage />)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
