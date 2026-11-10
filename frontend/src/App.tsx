import { lazy, Suspense } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { LoadingBlock } from "./components/ui/States";
import { AvailabilityPage } from "./features/availability/AvailabilityPage";
import { LoginPage } from "./features/auth/LoginPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { AnonymousOnly, RequireAuth } from "./features/auth/routeGuards";
import { CourseDetailPage } from "./features/courses/CourseDetailPage";
import { CoursesPage } from "./features/courses/CoursesPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { SchedulePage } from "./features/schedule/SchedulePage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { TasksPage } from "./features/tasks/TasksPage";

// Charts are the heaviest code in the app, so only people who open this page download them.
const AnalyticsPage = lazy(() =>
  import("./features/analytics/AnalyticsPage").then((module) => ({ default: module.AnalyticsPage })),
);

function NotFoundPage() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-2 text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link to="/" className="text-sm font-medium text-brand hover:underline">
        Back to CoursePilot
      </Link>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AnonymousOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/courses/:courseId" element={<CourseDetailPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/availability" element={<AvailabilityPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route
            path="/analytics"
            element={
              <Suspense fallback={<LoadingBlock />}>
                <AnalyticsPage />
              </Suspense>
            }
          />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
