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
import { SettingsAuditLogsTable } from "../components/settings/SettingsAuditLogsTable";
import { AdminLoginPanel, FirstAdminSetupPanel } from "../components/settings/SettingsAuthPanel";
import { SettingsThresholdSections } from "../components/settings/SettingsThresholdSections";

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
  webhook_max_retries: 3,
  webhook_initial_backoff_seconds: 0.5,
  webhook_timeout_seconds: 3,
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
  const [isLoadingSettings, setIsLoadingSettings] = useState(false);

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

    setIsLoadingSettings(true);

    Promise.all([getSettings(), getAuditLogs(80)])
      .then(([settingsPayload, logsPayload]) => {
        setForm(settingsPayload);
        setAuditLogs(logsPayload);
        setStatus("Settings and audit logs loaded");
      })
      .catch((error) => {
        setStatus(error instanceof Error ? error.message : "Could not load secure settings data");
      })
      .finally(() => {
        setIsLoadingSettings(false);
      });
  }, [authenticatedEmail]);

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
    if (isLoadingSettings) {
      setStatus("Please wait for settings to finish loading before saving");
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
    if (form.webhook_max_retries < 1 || form.webhook_max_retries > 3) {
      setStatus("Webhook max retries must be between 1 and 3");
      return;
    }
    if (form.webhook_initial_backoff_seconds < 0.5 || form.webhook_initial_backoff_seconds > 2) {
      setStatus("Webhook initial backoff must be between 0.5 and 2.0 seconds");
      return;
    }
    if (form.webhook_timeout_seconds < 2 || form.webhook_timeout_seconds > 6) {
      setStatus("Webhook timeout must be between 2 and 6 seconds");
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

        <FirstAdminSetupPanel
          registerEmail={registerEmail}
          registerPassword={registerPassword}
          status={status}
          onRegisterEmailChange={setRegisterEmail}
          onRegisterPasswordChange={setRegisterPassword}
          onSubmit={onRegisterAdmin}
        />
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

        <AdminLoginPanel
          loginEmail={loginEmail}
          loginPassword={loginPassword}
          status={status}
          onLoginEmailChange={setLoginEmail}
          onLoginPasswordChange={setLoginPassword}
          onSubmit={onLoginAdmin}
        />
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

        <SettingsThresholdSections form={form} setForm={setForm} />

        <div className="actions-inline">
          <button
            type="submit"
            className="button-primary"
            disabled={isSaving || isLoadingSettings}
            data-testid="settings-save-button"
          >
            {isSaving ? "Saving" : "Save Settings"}
          </button>
          <p className="muted" data-testid="settings-status-message">
            {status}
          </p>
        </div>
      </form>

      <SettingsAuditLogsTable auditLogs={auditLogs} />
    </section>
  );
}
