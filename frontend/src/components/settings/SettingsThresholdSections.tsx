import { Dispatch, SetStateAction } from "react";
import { SettingsPayload } from "../../types";

interface SettingsThresholdSectionsProps {
  form: SettingsPayload;
  setForm: Dispatch<SetStateAction<SettingsPayload>>;
}

export const SettingsThresholdSections = ({ form, setForm }: SettingsThresholdSectionsProps) => {
  return (
    <>
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
          <span data-testid="threshold-critical-count-warning-label">Critical Integration Count Warning</span>
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
          <span data-testid="threshold-critical-count-critical-label">Critical Integration Count Critical</span>
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

        <label className="field">
          <span data-testid="settings-webhook-retries-label">Max Retries (1-3)</span>
          <input
            type="number"
            min={1}
            max={3}
            value={form.webhook_max_retries}
            onChange={(event) =>
              setForm((current) => ({ ...current, webhook_max_retries: Number(event.target.value) }))
            }
            data-testid="settings-webhook-retries-input"
          />
        </label>

        <label className="field">
          <span data-testid="settings-webhook-backoff-label">Initial Backoff Seconds (0.5-2.0)</span>
          <input
            type="number"
            min={0.5}
            max={2}
            step={0.1}
            value={form.webhook_initial_backoff_seconds}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                webhook_initial_backoff_seconds: Number(event.target.value),
              }))
            }
            data-testid="settings-webhook-backoff-input"
          />
        </label>

        <label className="field">
          <span data-testid="settings-webhook-timeout-label">Timeout Seconds (2-6)</span>
          <input
            type="number"
            min={2}
            max={6}
            value={form.webhook_timeout_seconds}
            onChange={(event) =>
              setForm((current) => ({ ...current, webhook_timeout_seconds: Number(event.target.value) }))
            }
            data-testid="settings-webhook-timeout-input"
          />
        </label>
      </section>
    </>
  );
};
