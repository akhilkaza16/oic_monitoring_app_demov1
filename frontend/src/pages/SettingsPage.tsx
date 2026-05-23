import { FormEvent, useEffect, useState } from "react";
import {
  clearStoredAdminToken,
  getAuditLogs,
  getAuthStatus,
  getSettings,
  getStoredAdminToken,
  loginAdmin,
  registerAdmin,
  setStoredAdminToken,
  updateSettings,
} from "../api";
import { AuditLogEntry, SettingsPayload } from "../types";

const DEFAULT_FORM: SettingsPayload = {
  oic_base_url: "",
  auth_mode: "OAuth2",
  polling_seconds: 30,
  notification_email: "",
};

export default function SettingsPage() {
  const [authToken, setAuthToken] = useState<string | null>(getStoredAdminToken());
  const [hasAdmin, setHasAdmin] = useState(false);
  const [authenticatedEmail, setAuthenticatedEmail] = useState<string | null>(null);
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [form, setForm] = useState<SettingsPayload>(DEFAULT_FORM);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [status, setStatus] = useState<string>("Awaiting action");
  const [isSaving, setIsSaving] = useState(false);
  const [loadingAuthState, setLoadingAuthState] = useState(true);

  const loadAuthStatus = async (tokenValue?: string | null) => {
    try {
      const response = await getAuthStatus(tokenValue ?? authToken);
      setHasAdmin(response.has_admin);
      setAuthenticatedEmail(response.authenticated_email);

      if (!response.authenticated_email && (tokenValue ?? authToken)) {
        clearStoredAdminToken();
        setAuthToken(null);
      }
    } catch {
      setStatus("Could not check auth status");
    } finally {
      setLoadingAuthState(false);
    }
  };

  useEffect(() => {
    loadAuthStatus(authToken);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!authToken || !authenticatedEmail) {
      return;
    }

    Promise.all([getSettings(authToken), getAuditLogs(authToken, 80)])
      .then(([settingsPayload, logsPayload]) => {
        setForm(settingsPayload);
        setAuditLogs(logsPayload);
        setStatus("Settings and audit logs loaded");
      })
      .catch((error) => {
        setStatus(error instanceof Error ? error.message : "Could not load secure settings data");
      });
  }, [authToken, authenticatedEmail]);

  const onRegisterAdmin = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("Creating first admin...");
    try {
      const response = await registerAdmin({ email: registerEmail, password: registerPassword });
      setStoredAdminToken(response.token);
      setAuthToken(response.token);
      await loadAuthStatus(response.token);
      setStatus("First admin created and signed in");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not create admin");
    }
  };

  const onLoginAdmin = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("Signing in...");
    try {
      const response = await loginAdmin({ email: loginEmail, password: loginPassword });
      setStoredAdminToken(response.token);
      setAuthToken(response.token);
      await loadAuthStatus(response.token);
      setStatus("Signed in successfully");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not login");
    }
  };

  const onLogout = async () => {
    clearStoredAdminToken();
    setAuthToken(null);
    setAuthenticatedEmail(null);
    setAuditLogs([]);
    setStatus("Signed out");
    await loadAuthStatus(null);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!authToken) {
      setStatus("Sign in required");
      return;
    }
    setIsSaving(true);
    try {
      await updateSettings(form, authToken);
      const latestLogs = await getAuditLogs(authToken, 80);
      setAuditLogs(latestLogs);
      setStatus("Settings saved successfully");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  if (loadingAuthState) {
    return (
      <section className="page" data-testid="settings-auth-loading-page">
        <div className="card">Loading settings authentication status...</div>
      </section>
    );
  }

  if (!hasAdmin) {
    return (
      <section className="page" data-testid="settings-first-admin-page">
        <div className="page-header">
          <div>
            <h2 className="page-title" data-testid="settings-first-admin-title">
              Create First Admin Account
            </h2>
            <p className="muted" data-testid="settings-first-admin-subtitle">
              First-run security setup: create local admin credentials before accessing settings.
            </p>
          </div>
        </div>

        <form className="card auth-card" onSubmit={onRegisterAdmin} data-testid="settings-register-form">
          <label className="field">
            <span data-testid="settings-register-email-label">Admin Email</span>
            <input
              type="email"
              value={registerEmail}
              onChange={(event) => setRegisterEmail(event.target.value)}
              data-testid="settings-register-email-input"
            />
          </label>
          <label className="field">
            <span data-testid="settings-register-password-label">Password</span>
            <input
              type="password"
              value={registerPassword}
              onChange={(event) => setRegisterPassword(event.target.value)}
              minLength={8}
              data-testid="settings-register-password-input"
            />
          </label>
          <button type="submit" className="button-primary" data-testid="settings-register-submit-button">
            Create Admin
          </button>
          <p className="muted" data-testid="settings-register-status-message">
            {status}
          </p>
        </form>
      </section>
    );
  }

  if (!authenticatedEmail || !authToken) {
    return (
      <section className="page" data-testid="settings-login-page">
        <div className="page-header">
          <div>
            <h2 className="page-title" data-testid="settings-login-title">
              Admin Login Required
            </h2>
            <p className="muted" data-testid="settings-login-subtitle">
              Settings are protected. Sign in with your local admin account.
            </p>
          </div>
        </div>

        <form className="card auth-card" onSubmit={onLoginAdmin} data-testid="settings-login-form">
          <label className="field">
            <span data-testid="settings-login-email-label">Email</span>
            <input
              type="email"
              value={loginEmail}
              onChange={(event) => setLoginEmail(event.target.value)}
              data-testid="settings-login-email-input"
            />
          </label>
          <label className="field">
            <span data-testid="settings-login-password-label">Password</span>
            <input
              type="password"
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
              minLength={8}
              data-testid="settings-login-password-input"
            />
          </label>
          <button type="submit" className="button-primary" data-testid="settings-login-submit-button">
            Sign In
          </button>
          <p className="muted" data-testid="settings-login-status-message">
            {status}
          </p>
        </form>
      </section>
    );
  }

  return (
    <section className="page" data-testid="settings-page">
      <div className="page-header">
        <div>
          <h2 className="page-title" data-testid="settings-page-title">
            Settings (Future OIC Configuration)
          </h2>
          <p className="muted" data-testid="settings-page-subtitle">
            Signed in as {authenticatedEmail}. Audit logs track settings changes, login attempts, and collector triggers.
          </p>
        </div>
        <button className="button-secondary" onClick={onLogout} data-testid="settings-logout-button">
          Sign Out
        </button>
      </div>

      <form className="card settings-form" onSubmit={onSubmit} data-testid="settings-form">
        <label className="field">
          <span data-testid="settings-oic-url-label">OIC Base URL</span>
          <input
            value={form.oic_base_url}
            onChange={(event) => setForm((current) => ({ ...current, oic_base_url: event.target.value }))}
            placeholder="https://future-oic-host.example.com"
            data-testid="settings-oic-url-input"
          />
        </label>

        <label className="field">
          <span data-testid="settings-auth-mode-label">Auth Mode</span>
          <select
            value={form.auth_mode}
            onChange={(event) => setForm((current) => ({ ...current, auth_mode: event.target.value }))}
            data-testid="settings-auth-mode-select"
          >
            <option value="OAuth2">OAuth2</option>
            <option value="Basic">Basic</option>
            <option value="API-Key">API Key</option>
          </select>
        </label>

        <label className="field">
          <span data-testid="settings-polling-label">Polling Seconds</span>
          <input
            type="number"
            min={10}
            max={600}
            value={form.polling_seconds}
            onChange={(event) =>
              setForm((current) => ({ ...current, polling_seconds: Number(event.target.value) }))
            }
            data-testid="settings-polling-input"
          />
        </label>

        <label className="field">
          <span data-testid="settings-email-label">Notification Email</span>
          <input
            type="email"
            value={form.notification_email}
            onChange={(event) =>
              setForm((current) => ({ ...current, notification_email: event.target.value }))
            }
            data-testid="settings-email-input"
          />
        </label>

        <div className="actions-inline">
          <button
            type="submit"
            className="button-primary"
            disabled={isSaving}
            data-testid="settings-save-button"
          >
            {isSaving ? "Saving" : "Save Settings"}
          </button>
          <p className="muted" data-testid="settings-status-message">
            {status}
          </p>
        </div>
      </form>

      <section className="card" data-testid="settings-audit-log-panel">
        <h3 className="section-heading" data-testid="settings-audit-log-heading">
          Audit Logs
        </h3>
        <div className="table-wrap">
          <table className="data-table" data-testid="settings-audit-log-table">
            <thead>
              <tr>
                <th data-testid="audit-th-time">Time</th>
                <th data-testid="audit-th-actor">Actor</th>
                <th data-testid="audit-th-action">Action</th>
                <th data-testid="audit-th-target">Target</th>
                <th data-testid="audit-th-details">Details</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((entry) => (
                <tr key={entry.id} data-testid={`audit-row-${entry.id}`}>
                  <td data-testid={`audit-time-${entry.id}`}>
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td data-testid={`audit-actor-${entry.id}`}>{entry.actor_email ?? "system"}</td>
                  <td data-testid={`audit-action-${entry.id}`}>{entry.action_type}</td>
                  <td data-testid={`audit-target-${entry.id}`}>{entry.target}</td>
                  <td data-testid={`audit-details-${entry.id}`}>{entry.details}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
