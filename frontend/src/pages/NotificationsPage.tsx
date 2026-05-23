import { useCallback, useEffect, useState } from "react";
import { getWebhookDeliveryLogs } from "../api";
import { WebhookDeliveryLogItem } from "../types";

type FilterType = "all" | "success" | "failed";

export default function NotificationsPage() {
  const [filter, setFilter] = useState<FilterType>("all");
  const [items, setItems] = useState<WebhookDeliveryLogItem[]>([]);
  const [summary, setSummary] = useState({ success: 0, failed: 0, total: 0 });
  const [statusMessage, setStatusMessage] = useState("Loading webhook delivery logs...");

  const load = useCallback(async () => {
    try {
      const response = await getWebhookDeliveryLogs(filter, 80);
      setItems(response.items);
      setSummary(response.summary);
      setStatusMessage(`Auto-refresh every 30 seconds · Last updated ${new Date().toLocaleTimeString()}`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not load webhook delivery logs");
    }
  }, [filter]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <section className="page" data-testid="notifications-page">
      <div className="page-header">
        <div>
          <h2 className="page-title" data-testid="notifications-page-title">
            Webhook Delivery Monitoring
          </h2>
          <p className="muted" data-testid="notifications-status-message">
            {statusMessage}
          </p>
        </div>
      </div>

      <section className="metrics-grid" data-testid="notifications-summary-grid">
        <article className="card" data-testid="notifications-total-card">
          <p className="metric-label">Total Deliveries</p>
          <p className="metric-value" data-testid="notifications-total-value">
            {summary.total}
          </p>
        </article>
        <article className="card" data-testid="notifications-success-card">
          <p className="metric-label">Success</p>
          <p className="metric-value" data-testid="notifications-success-value">
            {summary.success}
          </p>
        </article>
        <article className="card" data-testid="notifications-failed-card">
          <p className="metric-label">Failed</p>
          <p className="metric-value" data-testid="notifications-failed-value">
            {summary.failed}
          </p>
        </article>
      </section>

      <section className="card" data-testid="notifications-filter-panel">
        <label className="field">
          <span data-testid="notifications-filter-label">Filter Deliveries</span>
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as FilterType)}
            data-testid="notifications-filter-select"
          >
            <option value="all">All</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
          </select>
        </label>
      </section>

      <section className="card" data-testid="notifications-log-table-panel">
        <div className="table-wrap">
          <table className="data-table" data-testid="notifications-log-table">
            <thead>
              <tr>
                <th data-testid="notifications-th-time">Time</th>
                <th data-testid="notifications-th-event">Event</th>
                <th data-testid="notifications-th-severity">Severity</th>
                <th data-testid="notifications-th-status">Status</th>
                <th data-testid="notifications-th-attempts">Attempts</th>
                <th data-testid="notifications-th-http">HTTP</th>
                <th data-testid="notifications-th-error">Error</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} data-testid={`notifications-row-${item.id}`}>
                  <td data-testid={`notifications-time-${item.id}`}>
                    {new Date(item.created_at).toLocaleString()}
                  </td>
                  <td data-testid={`notifications-event-${item.id}`}>{item.event_type}</td>
                  <td data-testid={`notifications-severity-${item.id}`}>{item.severity}</td>
                  <td data-testid={`notifications-status-${item.id}`}>{item.status}</td>
                  <td data-testid={`notifications-attempts-${item.id}`}>{item.attempts}</td>
                  <td data-testid={`notifications-http-${item.id}`}>{item.http_status ?? "-"}</td>
                  <td data-testid={`notifications-error-${item.id}`}>{item.error_message ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
