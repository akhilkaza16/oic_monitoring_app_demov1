import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import { getExecutiveSummary, getLatencyLogs, runMockCollectorCycle } from "../api";
import { ExecutiveSummary, LatencyLog } from "../types";
import { LatencyPanel } from "../components/LatencyPanel";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";

export default function ExecutiveDashboardPage() {
  const [summary, setSummary] = useState<ExecutiveSummary | null>(null);
  const [latencyLogs, setLatencyLogs] = useState<LatencyLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string>("-");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [summaryData, latencyData] = await Promise.all([
        getExecutiveSummary(),
        getLatencyLogs(undefined, 8),
      ]);
      setSummary(summaryData);
      setLatencyLogs(latencyData.reverse());
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
    } finally {
      setIsRefreshing(false);
    }
  };

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
        </>
      )}
    </section>
  );
}
