import { FormEvent, useEffect, useState } from "react";
import { getSettings, updateSettings } from "../api";
import { SettingsPayload } from "../types";

const DEFAULT_FORM: SettingsPayload = {
  oic_base_url: "",
  auth_mode: "OAuth2",
  polling_seconds: 30,
  notification_email: "",
};

export default function SettingsPage() {
  const [form, setForm] = useState<SettingsPayload>(DEFAULT_FORM);
  const [status, setStatus] = useState<string>("Loading...");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    getSettings()
      .then((payload) => {
        setForm(payload);
        setStatus("Settings loaded");
      })
      .catch(() => setStatus("Could not load settings"));
  }, []);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    try {
      await updateSettings(form);
      setStatus("Settings saved successfully");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="page" data-testid="settings-page">
      <div className="page-header">
        <div>
          <h2 className="page-title" data-testid="settings-page-title">
            Settings (Future OIC Configuration)
          </h2>
          <p className="muted" data-testid="settings-page-subtitle">
            OIC connectivity remains abstracted; these values are placeholders for future real connector wiring.
          </p>
        </div>
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
    </section>
  );
}
