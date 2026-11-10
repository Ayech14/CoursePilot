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
  },
  {
    to: "/tasks",
    label: "Tasks",
    icon: ListChecks,
  },
  {
    to: "/availability",
    label: "Availability",
    icon: CalendarClock,
  },
  {
    to: "/schedule",
    label: "Schedule",
    icon: CalendarDays,
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
