import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import { TodayPage } from "./pages/Today";

// Today is in the main bundle (first paint); every other page loads on demand.
const SleepPage = lazy(() => import("./pages/Sleep").then((m) => ({ default: m.SleepPage })));
const HeartPage = lazy(() => import("./pages/Heart").then((m) => ({ default: m.HeartPage })));
const ActivityPage = lazy(() => import("./pages/Activity").then((m) => ({ default: m.ActivityPage })));
const WorkoutPage = lazy(() => import("./pages/Workout").then((m) => ({ default: m.WorkoutPage })));
const TrendsPage = lazy(() => import("./pages/Trends").then((m) => ({ default: m.TrendsPage })));
const RecordsPage = lazy(() => import("./pages/Records").then((m) => ({ default: m.RecordsPage })));
const SettingsPage = lazy(() => import("./pages/Settings").then((m) => ({ default: m.SettingsPage })));

export function AppRoutes() {
  return (
    <Suspense fallback={<div className="card h-64 animate-pulse" />}>
      <Routes>
        <Route path="/" element={<TodayPage />} />
        <Route path="/sleep" element={<SleepPage />} />
        <Route path="/heart" element={<HeartPage />} />
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="/activity/workout" element={<WorkoutPage />} />
        <Route path="/trends" element={<TrendsPage />} />
        <Route path="/records" element={<RecordsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<TodayPage />} />
      </Routes>
    </Suspense>
  );
}
