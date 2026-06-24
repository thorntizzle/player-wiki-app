import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import type { AdminInvitePayload } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { useAdminDashboardMutations, useAdminUserDetailMutations } from "../adminMutations";
import { AdminActivityFilters, AdminActivityList, AdminPagination } from "../components/AdminActivity";
import { ApiErrorNotice, ToastNotice, useToastNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

function adminSearch(search: string): string {
  return search.startsWith("?") ? search : search ? `?${search}` : "";
}

export function AdminDashboardPage() {
  const { apiClient, setAuthRequired } = useApiClient();
  useLocation();
  const currentSearch = window.location.search;
  const [inviteDraft, setInviteDraft] = useState<AdminInvitePayload>({
    email: "",
    display_name: "",
    user_type: "player",
    campaign_slug: "",
  });
  const [errorMessage, setErrorMessage] = useState("");
  const { showToast, toastMessage, toastTone } = useToastNotice();

  const dashboardQuery = useQuery({
    queryKey: ["admin-dashboard", currentSearch],
    queryFn: () => apiClient.getAdminDashboard(adminSearch(currentSearch)),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(dashboardQuery.error)) {
      setAuthRequired(true);
    }
  }, [dashboardQuery.error, setAuthRequired]);

  useEffect(() => {
    const defaults = dashboardQuery.data?.invite_form_defaults;
    if (!defaults) {
      return;
    }
    setInviteDraft((current) => ({
      ...current,
      user_type: current.user_type || defaults.user_type,
      campaign_slug: current.campaign_slug || defaults.campaign_slug,
    }));
  }, [dashboardQuery.data?.invite_form_defaults]);

  const { inviteMutation } = useAdminDashboardMutations({
    apiClient,
    setAuthRequired,
    setStatusMessage: showToast,
    setErrorMessage,
    setInviteDraft,
  });

  const queryError = getApiErrorMessage(dashboardQuery.error);
  const data = dashboardQuery.data;

  return (
    <>
      <section className="hero compact admin-hero">
        <p className="eyebrow">Admin</p>
        <h1>Admin dashboard</h1>
        <p className="lede">Use this screen for lighter operational work. The CLI remains the full-control path for bootstrap and recovery.</p>
      </section>

      <ApiErrorNotice isLoading={dashboardQuery.isLoading} message={queryError} onAuth={() => setAuthRequired(true)} />
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      <ToastNotice message={toastMessage} tone={toastTone} />

      {data ? (
        <>
          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Invite user</h2>
              <form
                className="stack-form admin-panel-form"
                onSubmit={(event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  inviteMutation.mutate(inviteDraft);
                }}
              >
                <label className="field">
                  <span>Email</span>
                  <input
                    id="admin-invite-email"
                    name="email"
                    type="email"
                    required
                    value={inviteDraft.email}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, email: value }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>Display name</span>
                  <input
                    id="admin-invite-display-name"
                    name="display_name"
                    type="text"
                    required
                    value={inviteDraft.display_name}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, display_name: value }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>User type</span>
                  <select
                    id="admin-invite-user-type"
                    name="user_type"
                    value={inviteDraft.user_type}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, user_type: value }));
                    }}
                  >
                    <option value="admin">Admin</option>
                    <option value="dm">DM</option>
                    <option value="player">Player</option>
                    <option value="standard">Standard user</option>
                  </select>
                </label>
                <label className="field">
                  <span>Campaign for DM or Player</span>
                  <select
                    id="admin-invite-campaign-slug"
                    name="campaign_slug"
                    value={inviteDraft.campaign_slug || ""}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setInviteDraft((current) => ({ ...current, campaign_slug: value }));
                    }}
                  >
                    {data.campaign_choices.length ? (
                      data.campaign_choices.map((campaign) => (
                        <option key={campaign.slug} value={campaign.slug}>
                          {campaign.title}
                        </option>
                      ))
                    ) : (
                      <option value="">No campaigns available</option>
                    )}
                  </select>
                </label>
                <p className="meta">Admin is app-wide. DM and Player invites also create an active membership in the selected campaign.</p>
                <div className="admin-form-actions">
                  <button type="submit" className="button" disabled={inviteMutation.isPending}>
                    {inviteMutation.isPending ? "Creating..." : "Create invite"}
                  </button>
                </div>
              </form>
            </article>

            <aside className="card admin-panel">
              <h2>Campaigns</h2>
              <ul className="plain-list">
                {data.campaign_choices.map((campaign) => (
                  <li key={campaign.slug}>
                    {campaign.title} <span className="meta">({campaign.slug})</span>
                  </li>
                ))}
              </ul>
            </aside>
          </section>

          <section className="section-list admin-user-section">
            <div className="section-heading">
              <h2>Users</h2>
              <p className="meta">{data.user_cards.length} total</p>
            </div>
            <div className="grid admin-user-grid">
              {data.user_cards.map((user) => (
                <article key={user.id} className="card admin-user-card">
                  <p className="card-kicker">
                    {user.status}
                    {user.is_admin ? " | Admin" : ""}
                  </p>
                  <h3>
                    <a href={user.href}>{user.display_name}</a>
                  </h3>
                  <p>{user.email}</p>
                  {user.membership_summary.length ? <p className="meta">{user.membership_summary.join(" | ")}</p> : null}
                  {user.assignment_summary.length ? <p className="meta">Assignments: {user.assignment_summary.join(", ")}</p> : null}
                </article>
              ))}
            </div>
          </section>

          <section className="section-list admin-activity-section">
            <div className="section-heading">
              <h2>Recent activity</h2>
              <p className="meta">{data.pagination.total_events} matching events</p>
            </div>
            <article className="card admin-panel admin-activity-panel">
              <AdminActivityFilters action="/app-next/admin" clearHref="/app-next/admin" data={data} />
              <AdminActivityList events={data.recent_audit_events} />
              <AdminPagination pagination={data.pagination} />
            </article>
          </section>
        </>
      ) : null}
    </>
  );
}

export function AdminUserDetailPage() {
  const { apiClient, setAuthRequired } = useApiClient();
  const params = useParams({ from: "/admin/users/$userId" });
  useLocation();
  const currentSearch = window.location.search;
  const userId = Number(params.userId);
  const [membershipDraft, setMembershipDraft] = useState({ campaign_slug: "", role: "player", status: "active" });
  const [assignmentDraft, setAssignmentDraft] = useState({ character_ref: "" });
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const { showToast, toastMessage, toastTone } = useToastNotice();

  const userQuery = useQuery({
    queryKey: ["admin-user", userId, currentSearch],
    queryFn: () => apiClient.getAdminUser(userId, adminSearch(currentSearch)),
    enabled: Number.isFinite(userId),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(userQuery.error)) {
      setAuthRequired(true);
    }
  }, [userQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!userQuery.data) {
      return;
    }
    setMembershipDraft(userQuery.data.membership_form_defaults);
    setAssignmentDraft(userQuery.data.assignment_form_defaults);
  }, [userQuery.data?.membership_form_defaults, userQuery.data?.assignment_form_defaults]);

  const {
    assignCharacter,
    deleteUser,
    disableUser,
    enableUser,
    issueInvite,
    issuePasswordReset,
    removeAssignment,
    removeMembership,
    setMembership,
  } = useAdminUserDetailMutations({
    apiClient,
    userId,
    currentSearch,
    membershipDraft,
    assignmentDraft,
    deleteConfirm,
    setAuthRequired,
    setStatusMessage: showToast,
    setErrorMessage,
  });

  const data = userQuery.data;
  const queryError = getApiErrorMessage(userQuery.error);
  const mutationPending =
    setMembership.isPending
    || removeMembership.isPending
    || assignCharacter.isPending
    || removeAssignment.isPending
    || issueInvite.isPending
    || issuePasswordReset.isPending
    || disableUser.isPending
    || enableUser.isPending
    || deleteUser.isPending;

  return (
    <>
      <section className="hero compact admin-hero">
        <p className="eyebrow">Admin user detail</p>
        <h1>{data?.managed_user.display_name || "Admin user"}</h1>
        {data ? (
          <>
            <p className="lede">{data.managed_user.email}</p>
            <p className="meta">
              Status: {data.managed_user.status}
              {data.managed_user.is_admin ? " | App admin" : ""}
            </p>
            <div className="hero-actions">
              <a className="ghost-button" href={data.links.gen2_admin_url}>
                Back to admin dashboard
              </a>
            </div>
          </>
        ) : null}
      </section>

      <ApiErrorNotice isLoading={userQuery.isLoading} message={queryError} onAuth={() => setAuthRequired(true)} />
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      <ToastNotice message={toastMessage} tone={toastTone} />

      {data ? (
        <>
          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Campaign membership</h2>
              <form
                className="stack-form admin-panel-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  setMembership.mutate();
                }}
              >
                <label className="field">
                  <span>Campaign</span>
                  <select
                    id="admin-membership-campaign-slug"
                    name="campaign_slug"
                    required
                    value={membershipDraft.campaign_slug}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setMembershipDraft((current) => ({ ...current, campaign_slug: value }));
                    }}
                  >
                    {data.campaign_choices.map((campaign) => (
                      <option key={campaign.slug} value={campaign.slug}>
                        {campaign.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Role</span>
                  <select
                    id="admin-membership-role"
                    name="role"
                    required
                    value={membershipDraft.role}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setMembershipDraft((current) => ({ ...current, role: value }));
                    }}
                  >
                    <option value="dm">DM</option>
                    <option value="player">Player</option>
                    <option value="observer">Observer</option>
                  </select>
                </label>
                <label className="field">
                  <span>Status</span>
                  <select
                    id="admin-membership-status"
                    name="status"
                    required
                    value={membershipDraft.status}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setMembershipDraft((current) => ({ ...current, status: value }));
                    }}
                  >
                    <option value="active">Active</option>
                    <option value="invited">Invited</option>
                    <option value="removed">Removed</option>
                  </select>
                </label>
                <div className="admin-form-actions">
                  <button type="submit" className="button" disabled={mutationPending || !membershipDraft.campaign_slug}>
                    {setMembership.isPending ? "Saving..." : "Save membership"}
                  </button>
                </div>
              </form>
            </article>

            <article className="card admin-panel">
              <h2>Character assignment</h2>
              <p className="meta">Assignments require an active player membership in the same campaign.</p>
              <form
                className="stack-form admin-panel-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  assignCharacter.mutate();
                }}
              >
                <label className="field">
                  <span>Character</span>
                  <select
                    id="admin-assignment-character-ref"
                    name="character_ref"
                    required
                    value={assignmentDraft.character_ref}
                    onChange={(event) => {
                      setAssignmentDraft({ character_ref: event.currentTarget.value });
                    }}
                  >
                    {data.character_choices.map((character) => (
                      <option key={character.value} value={character.value}>
                        {character.label}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="admin-form-actions">
                  <button type="submit" className="button" disabled={mutationPending || !assignmentDraft.character_ref}>
                    {assignCharacter.isPending ? "Assigning..." : "Assign character"}
                  </button>
                </div>
              </form>
            </article>
          </section>

          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Current memberships</h2>
              {data.memberships.length ? (
                <ul className="plain-list admin-item-list">
                  {data.memberships.map((membership) => (
                    <li key={membership.id} className="admin-item-row">
                      <div>
                        <strong>{membership.campaign_title}</strong>
                        <span className="meta"> {membership.role} | {membership.status}</span>
                      </div>
                      <div className="admin-item-actions">
                        <a className="ghost-button" href={`${data.links.gen2_user_url}?edit_membership_campaign_slug=${encodeURIComponent(membership.campaign_slug)}`}>
                          Edit
                        </a>
                        {membership.status !== "removed" ? (
                          <button type="button" className="button" disabled={mutationPending} onClick={() => removeMembership.mutate(membership)}>
                            Remove
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No campaign memberships yet.</p>
              )}
            </article>

            <article className="card admin-panel">
              <h2>Current assignments</h2>
              {data.assignments.length ? (
                <ul className="plain-list admin-item-list">
                  {data.assignments.map((assignment) => (
                    <li key={assignment.id} className="admin-item-row">
                      <div>
                        <strong>{assignment.campaign_title}</strong>
                        <span className="meta"> {assignment.character_slug} | {assignment.assignment_type}</span>
                      </div>
                      <div className="admin-item-actions">
                        <a
                          className="ghost-button"
                          href={`${data.links.gen2_user_url}?edit_assignment_campaign_slug=${encodeURIComponent(assignment.campaign_slug)}&edit_assignment_character_slug=${encodeURIComponent(assignment.character_slug)}`}
                        >
                          Edit
                        </a>
                        <button type="button" className="button" disabled={mutationPending} onClick={() => removeAssignment.mutate(assignment)}>
                          Clear
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No character assignments yet.</p>
              )}
            </article>
          </section>

          <section className="page-layout admin-layout">
            <article className="card admin-panel">
              <h2>Account actions</h2>
              <div className="admin-action-stack">
                {data.managed_user.status === "invited" ? (
                  <button type="button" className="button" disabled={mutationPending} onClick={() => issueInvite.mutate()}>
                    {issueInvite.isPending ? "Generating..." : "Generate invite link"}
                  </button>
                ) : null}
                {data.managed_user.status === "active" ? (
                  <button type="button" className="button" disabled={mutationPending} onClick={() => issuePasswordReset.mutate()}>
                    {issuePasswordReset.isPending ? "Generating..." : "Generate password reset link"}
                  </button>
                ) : null}
                {data.can_manage_account && data.managed_user.status === "disabled" ? (
                  <button type="button" className="button" disabled={mutationPending} onClick={() => enableUser.mutate()}>
                    {enableUser.isPending ? "Saving..." : "Re-enable user"}
                  </button>
                ) : null}
                {data.can_manage_account && data.managed_user.status !== "disabled" ? (
                  <button type="button" className="button" disabled={mutationPending} onClick={() => disableUser.mutate()}>
                    {disableUser.isPending ? "Saving..." : "Disable user"}
                  </button>
                ) : null}
                {data.can_manage_account ? (
                  <>
                    <label className="field">
                      <span>Confirm delete by email</span>
                      <input
                        id="admin-delete-confirm-email"
                        name="confirm_email"
                        type="text"
                        value={deleteConfirm}
                        onChange={(event) => setDeleteConfirm(event.currentTarget.value)}
                        placeholder={data.managed_user.email}
                      />
                    </label>
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={mutationPending || deleteConfirm.trim().toLowerCase() !== data.managed_user.email.toLowerCase()}
                      onClick={() => deleteUser.mutate()}
                    >
                      {deleteUser.isPending ? "Deleting..." : "Delete user"}
                    </button>
                  </>
                ) : (
                  <p className="meta">
                    Use a different admin account or the CLI if you ever need to change the account you are currently using.
                  </p>
                )}
              </div>
            </article>

            <article className="card admin-panel">
              <h2>Recent activity for this user</h2>
              <p className="meta">{data.pagination.total_events} matching events</p>
              <AdminActivityFilters action={data.links.gen2_user_url || `/app-next/admin/users/${userId}`} clearHref={data.links.gen2_user_url || `/app-next/admin/users/${userId}`} data={data} />
              <AdminActivityList events={data.recent_audit_events} />
              <AdminPagination pagination={data.pagination} />
            </article>
          </section>
        </>
      ) : null}
    </>
  );
}
