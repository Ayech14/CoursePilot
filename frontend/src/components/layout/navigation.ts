import {
  CalendarClock,
  CalendarDays,
  ChartColumn,
  GraduationCap,
  LayoutDashboard,
  ListChecks,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Set while the page is unbuilt. The sidebar and the page both show this honestly. */
  plannedMilestone?: number;
  plannedDescription?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  {
    to: "/courses",
    label: "Courses",
    icon: GraduationCap,
    plannedMilestone: 2,
    plannedDescription: "Create courses, assign colors and follow progress per course.",
  },
  {
    to: "/tasks",
    label: "Tasks",
    icon: ListChecks,
    plannedMilestone: 2,
    plannedDescription: "Track assignments, projects, exams, readings and their remaining effort.",
  },
  {
    to: "/availability",
    label: "Availability",
    icon: CalendarClock,
    plannedMilestone: 2,
    plannedDescription: "Set your weekly study hours, session length, breaks and unavailable time.",
  },
  {
    to: "/schedule",
    label: "Schedule",
    icon: CalendarDays,
    plannedMilestone: 3,
    plannedDescription: "Generate a study schedule, then preview and adjust it.",
  },
  {
    to: "/analytics",
    label: "Analytics",
    icon: ChartColumn,
    plannedMilestone: 5,
    plannedDescription: "See study hours, workload and estimated versus actual time.",
  },
  { to: "/settings", label: "Settings", icon: Settings },
];
