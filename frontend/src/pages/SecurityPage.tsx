import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  confirmPasswordReset,
  getAuthStatus,
  requestPasswordReset,
  revokeAllSessions,
} from "../api";

export default function SecurityPage() {
  const [authEmail, setAuthEmail] = useState<string | null>(null);
  const [requestEmail, setRequestEmail] = useState("admin@badger.local");
  const [resetCode, setResetCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("Ready");

  const loadAuthStatus = useCallback(async () => {
    try {
      const auth = await getAuthStatus();
      setAuthEmail(auth.authenticated_email);
    } catch {
      setAuthEmail(null);
    }
  }, []);

  useEffect(() => {
    loadAuthStatus();
  }, [loadAuthStatus]);

  const onRequestReset = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const response = await requestPasswordReset({ email: requestEmail });
      setGeneratedCode(response.reset_code);
      setStatusMessage(`Reset code generated. Expires in ${response.expires_in_minutes} minutes.`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not request reset code");
    }
  };

  const onConfirmReset = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await confirmPasswordReset({
        email: requestEmail,
        reset_code: resetCode,
        new_password: newPassword,
      });
      setStatusMessage("Password reset completed. Please sign in again from Settings.");
      setResetCode("");
      setNewPassword("");
      await loadAuthStatus();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not complete password reset");
    }
  };

  const onRevokeSessions = async () => {
    try {
      const response = await revokeAllSessions();
      setStatusMessage(`Revoked ${response.revoked_sessions} active sessions. Please sign in again.`);
      await loadAuthStatus();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not revoke sessions");
    }
  };

  return (
    <section className="page" data-testid="security-page">
      <div className="page-header">
        <div>
          <h2 className="page-title" data-testid="security-page-title">
            Security Controls
          </h2>
          <p className="muted" data-testid="security-page-subtitle">
            Password reset and session revocation management.
          </p>
        </div>
      </div>

      <section className="card" data-testid="security-session-panel">
        <h3 className="section-heading" data-testid="security-session-heading">
          Session Revocation
        </h3>
        <p className="muted" data-testid="security-authenticated-email">
          {authEmail ? `Authenticated as ${authEmail}` : "Not currently authenticated"}
        </p>
        <button
          className="button-secondary"
          onClick={onRevokeSessions}
          disabled={!authEmail}
          data-testid="security-revoke-all-sessions-button"
        >
          Revoke All Sessions
        </button>
      </section>

      <section className="card" data-testid="security-password-reset-request-panel">
        <h3 className="section-heading" data-testid="security-password-reset-request-heading">
          Request One-Time Reset Code
        </h3>
        <form className="settings-form" onSubmit={onRequestReset} data-testid="security-password-reset-request-form">
          <label className="field">
            <span data-testid="security-reset-email-label">Admin Email</span>
            <input
              type="email"
              value={requestEmail}
              onChange={(event) => setRequestEmail(event.target.value)}
              data-testid="security-reset-email-input"
            />
          </label>
          <button type="submit" className="button-primary" data-testid="security-reset-request-button">
            Generate Reset Code
          </button>
        </form>
        {generatedCode && (
          <p className="security-reset-code" data-testid="security-generated-reset-code">
            One-time reset code: <strong>{generatedCode}</strong>
          </p>
        )}
      </section>

      <section className="card" data-testid="security-password-reset-confirm-panel">
        <h3 className="section-heading" data-testid="security-password-reset-confirm-heading">
          Confirm Password Reset
        </h3>
        <form className="settings-form" onSubmit={onConfirmReset} data-testid="security-password-reset-confirm-form">
          <label className="field">
            <span data-testid="security-reset-code-label">Reset Code</span>
            <input
              value={resetCode}
              onChange={(event) => setResetCode(event.target.value)}
              data-testid="security-reset-code-input"
            />
          </label>
          <label className="field">
            <span data-testid="security-new-password-label">New Password</span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              minLength={10}
              data-testid="security-new-password-input"
            />
          </label>
          <button type="submit" className="button-primary" data-testid="security-reset-confirm-button">
            Reset Password
          </button>
        </form>
      </section>

      <p className="muted" data-testid="security-status-message">
        {statusMessage}
      </p>
    </section>
  );
}
