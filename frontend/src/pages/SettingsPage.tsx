import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  getAuditLogs,
  getAuthStatus,
  getSettings,
  loginAdmin,
  logoutAdmin,
  registerAdmin,
  updateSettings,
} from "../api";
import { AuditLogEntry, SettingsPayload } from "../types";

const DEFAULT_FORM: SettingsPayload = {
  oic_base_url: "",
  auth_mode: "OAuth2",
  polling_seconds: 30,
  notification_email: "",
  threshold_issue_score_warning: 12,
  threshold_issue_score_critical: 18,
  threshold_missed_schedules_warning: 3,
  threshold_missed_schedules_critical: 5,
  threshold_critical_integrations_warning: 20,
  threshold_critical_integrations_critical: 35,
  webhook_enabled: false,
  webhook_url: "",
  webhook_bearer_token: "",
};

export default function SettingsPage() {
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

  const loadAuthStatus = useCallback(
    async () => {
      try {
        const response = await getAuthStatus();
        setHasAdmin(response.has_admin);
        setAuthenticatedEmail(response.authenticated_email);

        if (!response.has_admin) {
          setStatus("Create your first admin account to unlock settings");
        } else if (!response.authenticated_email) {
          setStatus("Please sign in to access settings");
        }

      } catch {
        setStatus("Could not check auth status");
      } finally {
        setLoadingAuthState(false);
      }
    },
    []
  );

  useEffect(() => {
    loadAuthStatus();
  }, [loadAuthStatus]);

  useEffect(() => {
    if (!authenticatedEmail) {
      return;
    }

    Promise.all([getSettings(), getAuditLogs(80)])
      .then(([settingsPayload, logsPayload]) => {
        setForm(settingsPayload);
        setAuditLogs(logsPayload);
        setStatus("Settings and audit logs loaded");
      })
      .catch((error) => {
        setStatus(error instanceof Error ? error.message : "Could not load secure settings data");
      });
  }, [authenticatedEmail, getAuditLogs, getSettings]);

  const onRegisterAdmin = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("Creating first admin...");
    try {
      await registerAdmin({ email: registerEmail, password: registerPassword });
      await loadAuthStatus();
      setStatus("First admin created and signed in");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not create admin");
    }
  };

  const onLoginAdmin = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("Signing in...");
    try {
      await loginAdmin({ email: loginEmail, password: loginPassword });
      await loadAuthStatus();
      setStatus("Signed in successfully");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not login");
    }
  };

  const onLogout = async () => {
    await logoutAdmin();
    setAuthenticatedEmail(null);
    setAuditLogs([]);
    setStatus("Signed out. Please sign in to continue");
    await loadAuthStatus();
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!authenticatedEmail) {
      setStatus("Sign in required");
      return;
    }
    if (form.threshold_issue_score_warning > form.threshold_issue_score_critical) {
      setStatus("Issue score warning threshold must be less than or equal to critical threshold");
      return;
    }
    if (form.threshold_missed_schedules_warning > form.threshold_missed_schedules_critical) {
      setStatus("Missed schedule warning threshold must be less than or equal to critical threshold");
      return;
    }
    if (form.threshold_critical_integrations_warning > form.threshold_critical_integrations_critical) {
      setStatus("Critical integration count warning must be less than or equal to critical threshold");
      return;
    }
    if (form.webhook_enabled && (!form.webhook_url.trim() || !form.webhook_bearer_token.trim())) {
      setStatus("Webhook URL and webhook bearer token are required when webhook is enabled");
      return;
    }
    setIsSaving(true);
    try {
      await updateSettings(form);
      const latestLogs = await getAuditLogs(80);
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

  if (!authenticatedEmail) {
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

        <section className="threshold-grid" data-testid="settings-threshold-grid">
          <h3 className="section-heading" data-testid="settings-threshold-heading">
            Alert Threshold Configuration (Warning / Critical)
          </h3>

          <label className="field">
            <span data-testid="threshold-issue-warning-label">Issue Score Warning</span>
            <input
              type="number"
              min={1}
              max={200}
              value={form.threshold_issue_score_warning}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  threshold_issue_score_warning: Number(event.target.value),
                }))
              }
              data-testid="threshold-issue-warning-input"
            />
          </label>

          <label className="field">
            <span data-testid="threshold-issue-critical-label">Issue Score Critical</span>
            <input
              type="number"
              min={1}
              max={250}
              value={form.threshold_issue_score_critical}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  threshold_issue_score_critical: Number(event.target.value),
                }))
              }
              data-testid="threshold-issue-critical-input"
            />
          </label>

          <label className="field">
            <span data-testid="threshold-missed-warning-label">Missed Schedules Warning</span>
            <input
              type="number"
              min={1}
              max={30}
              value={form.threshold_missed_schedules_warning}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  threshold_missed_schedules_warning: Number(event.target.value),
                }))
              }
              data-testid="threshold-missed-warning-input"
            />
          </label>

          <label className="field">
            <span data-testid="threshold-missed-critical-label">Missed Schedules Critical</span>
            <input
              type="number"
              min={1}
              max={60}
              value={form.threshold_missed_schedules_critical}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  threshold_missed_schedules_critical: Number(event.target.value),
                }))
              }
              data-testid="threshold-missed-critical-input"
            />
          </label>

          <label className="field">
            <span data-testid="threshold-critical-count-warning-label">
              Critical Integration Count Warning
            </span>
            <input
              type="number"
              min={1}
              max={170}
              value={form.threshold_critical_integrations_warning}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  threshold_critical_integrations_warning: Number(event.target.value),
                }))
              }
              data-testid="threshold-critical-count-warning-input"
            />
          </label>

          <label className="field">
            <span data-testid="threshold-critical-count-critical-label">
              Critical Integration Count Critical
            </span>
            <input
              type="number"
              min={1}
              max={170}
              value={form.threshold_critical_integrations_critical}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  threshold_critical_integrations_critical: Number(event.target.value),
                }))
              }
              data-testid="threshold-critical-count-critical-input"
            />
          </label>
        </section>

        <section className="threshold-grid" data-testid="settings-webhook-grid">
          <h3 className="section-heading" data-testid="settings-webhook-heading">
            Webhook Notification Adapter
          </h3>

          <label className="field">
            <span data-testid="settings-webhook-enabled-label">Enable Webhook Notifications</span>
            <select
              value={form.webhook_enabled ? "true" : "false"}
              onChange={(event) =>
                setForm((current) => ({ ...current, webhook_enabled: event.target.value === "true" }))
              }
              data-testid="settings-webhook-enabled-select"
            >
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
          </label>

          <label className="field">
            <span data-testid="settings-webhook-url-label">Webhook URL</span>
            <input
              value={form.webhook_url}
              onChange={(event) => setForm((current) => ({ ...current, webhook_url: event.target.value }))}
              placeholder="https://example.com/webhook"
              data-testid="settings-webhook-url-input"
            />
          </label>

          <label className="field">
            <span data-testid="settings-webhook-token-label">Webhook Bearer Token</span>
            <input
              type="password"
              value={form.webhook_bearer_token}
              onChange={(event) =>
                setForm((current) => ({ ...current, webhook_bearer_token: event.target.value }))
              }
              data-testid="settings-webhook-token-input"
            />
          </label>
        </section>

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
