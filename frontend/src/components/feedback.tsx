export interface ApiMessageEnvelope {
  status: number;
  message: string;
}

export function ApiErrorNotice({
  isLoading,
  message,
  onAuth,
}: {
  isLoading: boolean;
  message: ApiMessageEnvelope | null;
  onAuth: () => void;
}) {
  if (isLoading) {
    return <p className="status status-neutral">Loading ...</p>;
  }
  if (!message) {
    return null;
  }
  if (message.status === 401) {
    return (
      <p className="status status-error">
        {message.message}
        <button type="button" className="link-like-button" onClick={onAuth}>
          Open sign-in
        </button>
      </p>
    );
  }
  return <p className="status status-error">{message.message}</p>;
}

export const TOAST_DISMISS_MS = 3600;

export function ToastNotice({
  message,
  tone = "neutral",
}: {
  message: string | null;
  tone?: "neutral" | "success";
}) {
  if (!message) {
    return null;
  }

  return (
    <div className={`toast-notice toast-notice--${tone}`} role="status" aria-live="polite">
      <p>{message}</p>
    </div>
  );
}
