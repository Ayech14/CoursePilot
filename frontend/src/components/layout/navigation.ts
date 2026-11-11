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
    label: "Your week",
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
  },
  { to: "/settings", label: "Settings", icon: Settings },
];
