import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { ChangeEvent, FormEvent } from "react";

import { apiErrorMessage } from "../api/client";
import type {
  SessionMessage,
  SessionMessagePostPayload,
  SessionMessageRecipientPlayerChoice,
  SessionPayload,
} from "../api/types";
import { useApiClient } from "../apiClientContext";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { formatTimestamp } from "../timeFormatting";

function SessionPaneChat({
  payload,
}: {
  payload: SessionPayload | undefined;
}) {
  const messages: SessionMessage[] = payload?.messages ?? [];

  return (
    <article className="card session-chat-card" id="session-chat" data-session-chat-card>
      <div className="section-heading">
        <h2>Chat window</h2>
        <p className="meta">{payload?.active_session ? "Live feed" : "Waiting room"}</p>
      </div>
      <div className="chat-list">
        {messages.length ? (
          messages.map((message) => (
            <article key={message.id} className="chat-item">
              <p className="chat-meta">
                {message.author_display_name} - {formatTimestamp(message.created_at)}
              </p>
              <p>{message.body_text}</p>
            </article>
          ))
        ) : (
          <p className="status status-neutral">No messages yet.</p>
        )}
      </div>
    </article>
  );
}

function SessionPaneMessageComposer({
  payload,
  messageDraft,
  setMessageDraft,
  recipientScope,
  setRecipientScope,
  recipientPlayerId,
  setRecipientPlayerId,
  recipientPlayerChoices,
  sendError,
  onSend,
  isSending,
}: {
  payload: SessionPayload | undefined;
  messageDraft: string;
  setMessageDraft: (value: string) => void;
  recipientScope: "global" | "dm_only" | "player";
  setRecipientScope: (value: "global" | "dm_only" | "player") => void;
  recipientPlayerId: string;
  setRecipientPlayerId: (value: string) => void;
  recipientPlayerChoices: SessionMessageRecipientPlayerChoice[];
  sendError: string | null;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  isSending: boolean;
}) {
  return (
    <article className="card session-composer-card" id="session-chat-compose">
      <h2>Send message</h2>
      {payload?.permissions.can_post_messages ? (
        <form onSubmit={onSend} className="stack-form session-message-form">
          <label className="field">
            <span>Audience</span>
            <select
              value={recipientScope}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                setRecipientScope(event.currentTarget.value as "global" | "dm_only" | "player");
              }}
            >
              <option value="global">Global</option>
              <option value="dm_only">DM only</option>
              <option value="player">Specific player</option>
            </select>
          </label>
          <label className="field">
            <span>Player</span>
            <select
              value={recipientPlayerId}
              disabled={recipientScope !== "player" || !recipientPlayerChoices.length}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                setRecipientPlayerId(event.currentTarget.value);
              }}
            >
              {recipientPlayerChoices.length ? (
                recipientPlayerChoices.map((choice) => (
                  <option key={choice.user_id} value={String(choice.user_id)}>
                    {choice.label}
                  </option>
                ))
              ) : (
                <option value="">No players available</option>
              )}
            </select>
          </label>
          <label className="field">
            <span>Message</span>
            <textarea
              rows={5}
              value={messageDraft}
              placeholder="Type chat text"
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                setMessageDraft(event.currentTarget.value);
              }}
            />
          </label>
          <button type="submit" className="session-message-form__submit" disabled={isSending || payload?.active_session === null}>
            {isSending ? "Posting..." : "Post to chat"}
          </button>
          {sendError ? <p className="status status-error">{sendError}</p> : null}
        </form>
      ) : (
        <p className="status status-neutral">You do not have permission to post messages.</p>
      )}
    </article>
  );
}

export function SessionPane({
  campaignSlug,
  payload,
  refetch,
  setAuthRequired,
}: {
  campaignSlug: string;
  payload: SessionPayload | undefined;
  refetch: () => void;
  setAuthRequired: (required: boolean) => void;
}) {
  const { apiClient } = useApiClient();
  const [messageDraft, setMessageDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [recipientScope, setRecipientScope] = useState<"global" | "dm_only" | "player">("global");
  const [recipientPlayerId, setRecipientPlayerId] = useState("");
  const recipientPlayerChoices = payload?.session_message_recipient_player_choices ?? [];

  useEffect(() => {
    if (recipientScope !== "player") {
      setRecipientPlayerId("");
      return;
    }
    if (recipientPlayerChoices.length === 0) {
      setRecipientPlayerId("");
      return;
    }
    const validIds = new Set(recipientPlayerChoices.map((choice) => String(choice.user_id)));
    if (!validIds.has(recipientPlayerId)) {
      setRecipientPlayerId(String(recipientPlayerChoices[0].user_id));
    }
  }, [recipientScope, recipientPlayerChoices, recipientPlayerId]);

  const postMessage = useMutation({
    mutationFn: (payload: SessionMessagePostPayload) => apiClient.postSessionMessage(campaignSlug, payload),
    onSuccess: () => {
      setMessageDraft("");
      setSendError(null);
      refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSendError(apiErrorMessage(error));
    },
  });

  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = messageDraft.trim();
    if (!body) {
      setSendError("Type a message first.");
      return;
    }
    if (!payload?.permissions.can_post_messages) {
      setSendError("You do not have permission to post messages.");
      return;
    }
    if (!payload?.active_session) {
      setSendError("No active session.");
      return;
    }
    if (recipientScope === "player" && !recipientPlayerChoices.length) {
      setSendError("No player recipients available.");
      return;
    }
    if (recipientScope === "player" && !recipientPlayerId) {
      setSendError("Choose a player recipient.");
      return;
    }

    const messagePayload: SessionMessagePostPayload = {
      body,
      recipient_scope: recipientScope,
    };
    if (recipientScope === "player") {
      messagePayload.recipient_user_id = Number(recipientPlayerId);
    }
    postMessage.mutate(messagePayload);
  };

  return (
    <div className="page-layout session-layout session-layout--single">
      <section className="session-column">
        <SessionPaneChat
          payload={payload}
        />
        <SessionPaneMessageComposer
          payload={payload}
          messageDraft={messageDraft}
          setMessageDraft={setMessageDraft}
          recipientScope={recipientScope}
          setRecipientScope={setRecipientScope}
          recipientPlayerId={recipientPlayerId}
          setRecipientPlayerId={setRecipientPlayerId}
          recipientPlayerChoices={recipientPlayerChoices}
          sendError={sendError}
          onSend={sendMessage}
          isSending={postMessage.isPending}
        />
      </section>

    </div>
  );
}
