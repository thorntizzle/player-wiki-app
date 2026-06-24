import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { FormEvent } from "react";

import { apiErrorMessage } from "../api/client";
import type {
  AccountSettingsUpdatePayload,
  AccountSettingsUpdateResponse,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { queryClient, useApiClient } from "../apiClientContext";
import { ApiErrorNotice, ToastNotice, useToastNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

export function AccountSettingsPage() {
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftThemeKey, setDraftThemeKey] = useState("");
  const [draftChatOrder, setDraftChatOrder] = useState("");
  const [themeErrorMessage, setThemeErrorMessage] = useState<string | null>(null);
  const [chatErrorMessage, setChatErrorMessage] = useState<string | null>(null);
  const { clearToast, showToast, toastMessage, toastTone } = useToastNotice();

  const settingsQuery = useQuery({
    queryKey: ["account-settings"],
    queryFn: () => apiClient.getAccountSettings(),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(settingsQuery.error)) {
      setAuthRequired(true);
    }
  }, [settingsQuery.error, setAuthRequired]);

  useEffect(() => {
    const preferences = settingsQuery.data?.preferences;
    if (!preferences) {
      return;
    }
    setDraftThemeKey(preferences.theme_key || "");
    setDraftChatOrder(preferences.session_chat_order || "");
  }, [
    settingsQuery.data?.preferences?.theme_key,
    settingsQuery.data?.preferences?.session_chat_order,
  ]);

  const applySavedSettings = (response: AccountSettingsUpdateResponse) => {
    setDraftThemeKey(response.preferences.theme_key || "");
    setDraftChatOrder(response.preferences.session_chat_order || "");
    if (response.preferences.theme_key) {
      document.documentElement.dataset.theme = response.preferences.theme_key;
    }
    void queryClient.invalidateQueries({ queryKey: ["me"] });
    void queryClient.invalidateQueries({ queryKey: ["account-settings"] });
  };

  const saveThemeSettings = useMutation({
    mutationFn: (payload: AccountSettingsUpdatePayload) => apiClient.patchAccountSettings(payload),
    onSuccess: (response) => {
      showToast("Theme saved.");
      setThemeErrorMessage(null);
      applySavedSettings(response);
    },
    onError: (error) => {
      clearToast();
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const saveChatSettings = useMutation({
    mutationFn: (payload: AccountSettingsUpdatePayload) => apiClient.patchAccountSettings(payload),
    onSuccess: (response) => {
      showToast("Chat order saved.");
      setChatErrorMessage(null);
      applySavedSettings(response);
    },
    onError: (error) => {
      clearToast();
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const error = getApiErrorMessage(settingsQuery.error);
  const themeSaveError = themeErrorMessage ?? (saveThemeSettings.error ? apiErrorMessage(saveThemeSettings.error) : null);
  const chatSaveError = chatErrorMessage ?? (saveChatSettings.error ? apiErrorMessage(saveChatSettings.error) : null);
  const preferences = settingsQuery.data?.preferences;
  const themePresets = settingsQuery.data?.theme_presets ?? [];
  const chatOrderChoices = settingsQuery.data?.session_chat_order_choices ?? [];
  const user = settingsQuery.data?.user;
  const selectedTheme = themePresets.find((theme) => theme.key === (preferences?.theme_key || draftThemeKey));
  const isThemeUnchanged = draftThemeKey === (preferences?.theme_key || "");
  const isChatOrderUnchanged = draftChatOrder === (preferences?.session_chat_order || "");

  const handleThemeSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isThemeUnchanged) {
      return;
    }
    clearToast();
    setThemeErrorMessage(null);
    saveThemeSettings.mutate({
      theme_key: draftThemeKey,
    });
  };

  const handleChatOrderSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isChatOrderUnchanged) {
      return;
    }
    clearToast();
    setChatErrorMessage(null);
    saveChatSettings.mutate({
      session_chat_order: draftChatOrder,
    });
  };

  return (
    <>
      <section className="hero compact account-hero">
        <p className="eyebrow">Account settings</p>
        <h1>{user?.display_name ?? "Account"}</h1>
        <p className="lede">Save interface preferences to your account and use them everywhere you are signed in.</p>
        <p className="meta">
          Current theme: {selectedTheme?.label ?? preferences?.theme_key ?? "Loading"}
          {user?.is_admin ? " | App admin" : ""}
        </p>
      </section>

      <ApiErrorNotice isLoading={settingsQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      <ToastNotice message={toastMessage} tone={toastTone} />

      {settingsQuery.data ? (
        <section className="page-layout account-layout">
          <article className="card account-panel">
            <section className="account-settings-group">
              <h2>Color theme</h2>
              <p className="meta">These presets restyle the shared app chrome, cards, forms, and reading surfaces.</p>
              <form className="stack-form" onSubmit={handleThemeSubmit}>
                <div className="theme-grid">
                  {themePresets.map((theme) => {
                    const inputId = `account-theme-${theme.key}`;
                    const checked = draftThemeKey === theme.key;
                    return (
                      <label className={checked ? "theme-option is-selected" : "theme-option"} htmlFor={inputId} key={theme.key}>
                        <input
                          className="theme-option__input"
                          id={inputId}
                          type="radio"
                          name="theme_key"
                          value={theme.key}
                          checked={checked}
                          onChange={() => setDraftThemeKey(theme.key)}
                        />
                        <span className="theme-option__header">
                          <span>
                            <strong>{theme.label}</strong>
                            {preferences?.theme_key === theme.key ? <span className="meta theme-option__status">Current</span> : null}
                          </span>
                          <span className="theme-option__swatches" aria-hidden="true">
                            {theme.preview_colors.map((color) => (
                              <span className="theme-option__swatch" style={{ background: color }} key={color} />
                            ))}
                          </span>
                        </span>
                        <span className="meta">{theme.description}</span>
                      </label>
                    );
                  })}
                </div>
                <button type="submit" className="button" disabled={saveThemeSettings.isPending || isThemeUnchanged}>
                  {saveThemeSettings.isPending ? "Saving..." : "Save theme"}
                </button>
                {isThemeUnchanged && !saveThemeSettings.isPending ? <p className="meta">Theme is already current.</p> : null}
                {themeSaveError ? <p className="status status-error">{themeSaveError}</p> : null}
              </form>
            </section>

            <section className="account-settings-group">
              <h2>Live session chat order</h2>
              <p className="meta">
                This changes the order of the live Session chat window for your account only. Stored session logs stay chronological.
              </p>
              <form className="stack-form" onSubmit={handleChatOrderSubmit}>
                <div className="theme-grid">
                  {chatOrderChoices.map((choice) => {
                    const inputId = `account-chat-order-${choice.value}`;
                    const checked = draftChatOrder === choice.value;
                    return (
                      <label className={checked ? "theme-option is-selected" : "theme-option"} htmlFor={inputId} key={choice.value}>
                        <input
                          className="theme-option__input"
                          id={inputId}
                          type="radio"
                          name="session_chat_order"
                          value={choice.value}
                          checked={checked}
                          onChange={() => setDraftChatOrder(choice.value)}
                        />
                        <span className="theme-option__header">
                          <span>
                            <strong>{choice.label}</strong>
                            {preferences?.session_chat_order === choice.value ? (
                              <span className="meta theme-option__status">Current</span>
                            ) : null}
                          </span>
                        </span>
                        <span className="meta">{choice.description}</span>
                      </label>
                    );
                  })}
                </div>
                <button
                  type="submit"
                  className="button"
                  disabled={saveChatSettings.isPending || isChatOrderUnchanged}
                >
                  {saveChatSettings.isPending ? "Saving..." : "Save chat order"}
                </button>
                {isChatOrderUnchanged && !saveChatSettings.isPending ? <p className="meta">Chat order is already current.</p> : null}
                {chatSaveError ? <p className="status status-error">{chatSaveError}</p> : null}
              </form>
            </section>
          </article>

          <aside className="card account-sidebar">
            <h2>Account</h2>
            <p>
              <strong>{user?.display_name}</strong>
            </p>
            <p className="meta">{user?.email}</p>
            {user?.is_admin ? <p className="meta-badge">App admin</p> : null}
            <p className="meta">
              Theme and live-session chat preferences are stored in the auth database and applied on every signed-in request.
            </p>
            <a className="ghost-button" href="/campaigns">
              Back to campaigns
            </a>
          </aside>
        </section>
      ) : null}
    </>
  );
}
