import { useApiClient } from "../apiClientContext";

export function AuthNotice() {
  const { authRequired, setApiToken } = useApiClient();
  const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;

  if (!authRequired) {
    return null;
  }

  return (
    <section className="card auth-notice">
      <div className="section-heading">
        <div>
          <h2>Authentication required</h2>
          <p className="status status-error">
            Your cookie or API token did not authenticate this request. Sign in to restore session.
          </p>
        </div>
      </div>
      <div className="hero-actions">
        <a className="button-link" href={signInHref}>
          Sign in
        </a>
        <button type="button" className="ghost-button" onClick={() => setApiToken("")}>
          Continue without token
        </button>
      </div>
    </section>
  );
}
