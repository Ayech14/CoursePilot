import { Link, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { NAV_ITEMS } from "./components/layout/navigation";
import { AvailabilityPage } from "./features/availability/AvailabilityPage";
import { LoginPage } from "./features/auth/LoginPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { AnonymousOnly, RequireAuth } from "./features/auth/routeGuards";
import { CourseDetailPage } from "./features/courses/CourseDetailPage";
import { CoursesPage } from "./features/courses/CoursesPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { PlannedPage } from "./features/placeholder/PlannedPage";
import { SchedulePage } from "./features/schedule/SchedulePage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { TasksPage } from "./features/tasks/TasksPage";

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
          {NAV_ITEMS.filter((item) => item.plannedMilestone).map((item) => (
            <Route key={item.to} path={item.to} element={<PlannedPage item={item} />} />
          ))}
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
