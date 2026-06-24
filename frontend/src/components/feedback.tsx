import { useCallback, useEffect, useState } from "react";

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
export type ToastTone = "neutral" | "success";

export function useToastNotice({
  defaultTone = "neutral",
  dismissMs = TOAST_DISMISS_MS,
}: {
  defaultTone?: ToastTone;
  dismissMs?: number;
} = {}) {
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [toastTone, setToastTone] = useState<ToastTone>(defaultTone);

  useEffect(() => {
    if (!toastMessage) {
      return undefined;
    }
    const timer = window.setTimeout(() => setToastMessage(null), dismissMs);
    return () => window.clearTimeout(timer);
  }, [dismissMs, toastMessage]);

  const showToast = useCallback(
    (message: string | null | undefined, tone: ToastTone = defaultTone) => {
      const nextMessage = message?.trim() || null;
      setToastTone(tone);
      setToastMessage(nextMessage);
    },
    [defaultTone],
  );

  const clearToast = useCallback(() => {
    setToastMessage(null);
  }, []);

  return {
    clearToast,
    setToastMessage,
    showToast,
    toastMessage,
    toastTone,
  };
}

export function ToastNotice({
  message,
  tone = "neutral",
}: {
  message: string | null;
  tone?: ToastTone;
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
