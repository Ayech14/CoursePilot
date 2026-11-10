import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Repeating a 4xx cannot succeed. Only network and server failures are worth one retry.
        retry: (failures, error) =>
          failures < 1 && error instanceof ApiError && (error.status === 0 || error.status >= 500),
        refetchOnWindowFocus: false,
      },
    },
  });
}
