import type { Dispatch, SetStateAction } from "react";
import { useMutation } from "@tanstack/react-query";

import { apiErrorMessage, type CampaignApiClient } from "./api/client";
import type {
  AdminAssignment,
  AdminInvitePayload,
  AdminMembership,
  AdminUserDetailResponse,
} from "./api/types";
import { queryClient } from "./apiClientContext";
import { isAuthRequiredFromError as isAuthError } from "./sessionRouteState";

type StatusReporter = (message: string) => void;

interface UseAdminDashboardMutationsOptions {
  apiClient: CampaignApiClient;
  setAuthRequired: (required: boolean) => void;
  setStatusMessage: StatusReporter;
  setErrorMessage: Dispatch<SetStateAction<string>>;
  setInviteDraft: Dispatch<SetStateAction<AdminInvitePayload>>;
}

export function useAdminDashboardMutations({
  apiClient,
  setAuthRequired,
  setStatusMessage,
  setErrorMessage,
  setInviteDraft,
}: UseAdminDashboardMutationsOptions) {
  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage("");
    setErrorMessage(apiErrorMessage(error));
  };

  const inviteMutation = useMutation({
    mutationFn: (payload: AdminInvitePayload) => apiClient.inviteAdminUser(payload),
    onSuccess: (response) => {
      setErrorMessage("");
      setStatusMessage(response.message || "Invite created.");
      setInviteDraft((current) => ({
        ...current,
        email: "",
        display_name: "",
      }));
      queryClient.setQueryData(["admin-user", response.managed_user.id, ""], response);
      void queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
    },
    onError: handleMutationError,
  });

  return {
    inviteMutation,
  };
}

interface UseAdminUserDetailMutationsOptions {
  apiClient: CampaignApiClient;
  userId: number;
  currentSearch: string;
  membershipDraft: { campaign_slug: string; role: string; status: string };
  assignmentDraft: { character_ref: string };
  deleteConfirm: string;
  setAuthRequired: (required: boolean) => void;
  setStatusMessage: StatusReporter;
  setErrorMessage: Dispatch<SetStateAction<string>>;
}

export function useAdminUserDetailMutations({
  apiClient,
  userId,
  currentSearch,
  membershipDraft,
  assignmentDraft,
  deleteConfirm,
  setAuthRequired,
  setStatusMessage,
  setErrorMessage,
}: UseAdminUserDetailMutationsOptions) {
  const handleDetailSuccess = (response: AdminUserDetailResponse) => {
    setErrorMessage("");
    setStatusMessage(response.message || "Admin user saved.");
    queryClient.setQueryData(["admin-user", response.managed_user.id, currentSearch], response);
    void queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["me"] });
  };

  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage("");
    setErrorMessage(apiErrorMessage(error));
  };

  const setMembership = useMutation({
    mutationFn: () => apiClient.setAdminUserMembership(userId, membershipDraft),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const removeMembership = useMutation({
    mutationFn: (membership: AdminMembership) =>
      apiClient.removeAdminUserMembership(userId, { campaign_slug: membership.campaign_slug }),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const assignCharacter = useMutation({
    mutationFn: () => apiClient.assignAdminUserCharacter(userId, assignmentDraft),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const removeAssignment = useMutation({
    mutationFn: (assignment: AdminAssignment) =>
      apiClient.removeAdminUserCharacterAssignment(userId, {
        campaign_slug: assignment.campaign_slug,
        character_slug: assignment.character_slug,
      }),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const issueInvite = useMutation({
    mutationFn: () => apiClient.issueAdminUserInvite(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const issuePasswordReset = useMutation({
    mutationFn: () => apiClient.issueAdminUserPasswordReset(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const disableUser = useMutation({
    mutationFn: () => apiClient.disableAdminUser(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const enableUser = useMutation({
    mutationFn: () => apiClient.enableAdminUser(userId),
    onSuccess: handleDetailSuccess,
    onError: handleMutationError,
  });

  const deleteUser = useMutation({
    mutationFn: () => apiClient.deleteAdminUser(userId, { confirm_email: deleteConfirm }),
    onSuccess: (response) => {
      setErrorMessage("");
      setStatusMessage(response.message || "User deleted.");
      void queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
      window.location.assign("/app-next/admin");
    },
    onError: handleMutationError,
  });

  return {
    assignCharacter,
    deleteUser,
    disableUser,
    enableUser,
    issueInvite,
    issuePasswordReset,
    removeAssignment,
    removeMembership,
    setMembership,
  };
}
