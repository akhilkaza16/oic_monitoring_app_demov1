import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import {
  acknowledgeAlert,
  getAlerts,
  getExecutiveSummary,
  getLatencyLogs,
  getTrendSnapshots,
  runMockCollectorCycle,
} from "../api";
import { AlertEvent, ExecutiveSummary, LatencyLog, TrendSnapshot } from "../types";
import { LatencyPanel } from "../components/LatencyPanel";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";

function severityClass(severity: AlertEvent["severity"]): string {
  if (severity === "critical") return "status-critical";
  if (severity === "warning") return "status-warning";
  return "status-unknown";
}

export default function ExecutiveDashboardPage() {
  const [summary, setSummary] = useState<ExecutiveSummary | null>(null);
  const [latencyLogs, setLatencyLogs] = useState<LatencyLog[]>([]);
  const [trends, setTrends] = useState<TrendSnapshot[]>([]);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isAcknowledging, setIsAcknowledging] = useState<number | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("-");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [summaryData, latencyData, trendData, alertData] = await Promise.all([
        getExecutiveSummary(),
        getLatencyLogs(undefined, 8),
        getTrendSnapshots(30),
        getAlerts(12),
      ]);
      setSummary(summaryData);
      setLatencyLogs(latencyData.reverse());
      setTrends(trendData);
      setAlerts(alertData);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed loading dashboard");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  const triggerCollector = async () => {
    setIsRefreshing(true);
    try {
      await runMockCollectorCycle();
      await load();
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Could not trigger collector");
    } finally {
      setIsRefreshing(false);
    }
  };

  const onAcknowledgeAlert = async (alertId: number) => {
    setIsAcknowledging(alertId);
    try {
      await acknowledgeAlert(alertId);
      await load();
    } catch (ackError) {
      setError(
        ackError instanceof Error
          ? ackError.message
          : "Could not acknowledge alert. Sign in from Settings if needed."
      );
    } finally {
      setIsAcknowledging(null);
    }
  };

  const maxTrendScore = Math.max(...trends.map((entry) => entry.health_score), 1);

  if (isLoading) {
    return (
      <section className="page" data-testid="executive-loading-state">
        <div className="card">Loading executive overview...</div>
      </section>
    );
  }

  return (
    <section className="page" data-testid="executive-dashboard-page">
      <div className="page-header">
        <div>
          <h2 className="page-title" data-testid="executive-page-title">
            Executive Overview
          </h2>
          <p className="muted" data-testid="auto-refresh-indicator">
            Auto-refresh every 30 seconds · Last updated {lastUpdated}
          </p>
        </div>
        <button
          className="button-primary"
          onClick={triggerCollector}
          disabled={isRefreshing}
          data-testid="manual-collector-run-button"
        >
          <ArrowClockwise size={18} className={isRefreshing ? "spin" : ""} />
          {isRefreshing ? "Refreshing" : "Trigger Mock Cycle"}
        </button>
      </div>

      {error && (
        <p className="error-banner" data-testid="executive-error-message">
          {error}
        </p>
      )}

      {summary && (
        <>
          <div className="metrics-grid" data-testid="executive-metrics-grid">
            <MetricCard
              label="Health Score"
              value={`${summary.health_score}%`}
              helper="Weighted status score"
              testId="health-score"
            />
            <MetricCard
              label="Total Integrations"
              value={summary.total_integrations}
              helper="Active monitored integrations"
              testId="total-integrations"
            />
            <MetricCard
              label="Critical Incidents"
              value={summary.critical_incidents}
              helper="From top failing integrations"
              testId="critical-incidents"
            />
            <MetricCard
              label="Healthy / Warning / Critical / Unknown"
              value={`${summary.healthy_count} / ${summary.warning_count} / ${summary.critical_count} / ${summary.unknown_count}`}
              helper="Current state distribution"
              testId="status-distribution"
            />
          </div>

          <div className="page-grid" data-testid="executive-lower-grid">
            <section className="card" data-testid="top-failing-integrations-panel">
              <h3 className="section-heading" data-testid="top-failing-integrations-heading">
                Top Failing Integrations
              </h3>
              <div className="stack">
                {summary.top_failing_integrations.map((item) => (
                  <article
                    key={item.integration_id}
                    className="integration-row"
                    data-testid={`top-failing-${item.integration_id}`}
                  >
                    <div>
                      <p className="integration-name" data-testid={`top-failing-name-${item.integration_id}`}>
                        {item.name}
                      </p>
                      <p className="muted" data-testid={`top-failing-meta-${item.integration_id}`}>
                        {item.integration_id} · {item.project} · {item.business_domain}
                      </p>
                    </div>
                    <div className="integration-side">
                      <StatusBadge
                        status={item.status}
                        testId={`top-failing-status-${item.integration_id}`}
                      />
                      <p data-testid={`top-failing-errors-${item.integration_id}`}>
                        {item.failed_instances + item.connection_errors + item.timeouts + item.aborted_runs} issues
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <LatencyPanel logs={latencyLogs} title="API Latency (Recent)" testId="dashboard-latency-panel" />
          </div>

          <div className="page-grid" data-testid="trend-alert-grid">
            <section className="card" data-testid="health-trend-panel">
              <h3 className="section-heading" data-testid="health-trend-heading">
                Health Trend (Last 30 Days)
              </h3>
              <div className="trend-bars" data-testid="health-trend-bars">
                {trends.map((point, index) => (
                  <div className="trend-bar-wrap" key={point.snapshot_date} data-testid={`trend-point-${index}`}>
                    <div
                      className="trend-bar"
                      style={{ height: `${Math.max(8, (point.health_score / maxTrendScore) * 100)}%` }}
                    />
                    <p className="trend-score" data-testid={`trend-score-${index}`}>
                      {point.health_score.toFixed(1)}
                    </p>
                    <p className="trend-date" data-testid={`trend-date-${index}`}>
                      {point.snapshot_date.slice(5)}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            <section className="card" data-testid="alerts-panel">
              <h3 className="section-heading" data-testid="alerts-heading">
                Active Alerts + Email Simulation Log
              </h3>
              <div className="stack" data-testid="alerts-list">
                {alerts.length === 0 && (
                  <p className="muted" data-testid="alerts-empty-message">
                    No active alerts.
                  </p>
                )}
                {alerts.map((alert) => (
                  <article key={alert.id} className="alert-item" data-testid={`alert-item-${alert.id}`}>
                    <div className="alert-top-row">
                      <span
                        className={`status-badge ${severityClass(alert.severity)}`}
                        data-testid={`alert-severity-${alert.id}`}
                      >
                        {alert.severity}
                      </span>
                      <button
                        className="button-secondary"
                        onClick={() => onAcknowledgeAlert(alert.id)}
                        disabled={isAcknowledging === alert.id}
                        data-testid={`alert-acknowledge-button-${alert.id}`}
                      >
                        {isAcknowledging === alert.id ? "Acknowledging" : "Acknowledge"}
                      </button>
                    </div>
                    <p className="integration-name" data-testid={`alert-title-${alert.id}`}>
                      {alert.title} · {alert.integration_id}
                    </p>
                    <p className="muted" data-testid={`alert-message-${alert.id}`}>
                      {alert.message}
                    </p>
                    <p className="muted" data-testid={`alert-email-log-${alert.id}`}>
                      Email simulated to {alert.simulated_email_to} at {new Date(alert.created_at).toLocaleString()}
                    </p>
                  </article>
                ))}
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
