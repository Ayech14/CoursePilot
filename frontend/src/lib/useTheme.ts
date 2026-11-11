import { useEffect, useState } from "react";

import { followSystemTheme, saveTheme, storedTheme, type ThemeChoice } from "./theme";

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(storedTheme);
  useEffect(() => followSystemTheme(storedTheme), []);
  return [
    choice,
    (next) => {
      saveTheme(next);
      setChoice(next);
    },
  ];
}
