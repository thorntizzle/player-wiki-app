import { createContext, useContext } from "react";
import { QueryClient } from "@tanstack/react-query";

import { CampaignApiClient } from "./api/client";
import type { UserProfile } from "./api/types";

export type FrontendMode = "flask" | "gen2";

export interface ApiClientContextValue {
  apiClient: CampaignApiClient;
  apiToken: string;
  setApiToken: (token: string) => void;
  authRequired: boolean;
  setAuthRequired: (required: boolean) => void;
  preferredFrontendMode: FrontendMode;
  user: UserProfile | null;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2500,
      refetchOnWindowFocus: false,
    },
  },
});

export const ApiClientContext = createContext<ApiClientContextValue | null>(null);

export function useApiClient(): ApiClientContextValue {
  const context = useContext(ApiClientContext);
  if (context === null) {
    throw new Error("CampaignApiClient context is missing.");
  }
  return context;
}
