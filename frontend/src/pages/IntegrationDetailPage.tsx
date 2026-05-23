import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getIntegrationDetail, getLatencyLogs, runMockCollectorCycle } from "../api";
import { ErrorRecommendations } from "../components/ErrorRecommendations";
import { LatencyPanel } from "../components/LatencyPanel";
import { StatusBadge } from "../components/StatusBadge";
import { IntegrationDetailResponse, LatencyLog } from "../types";

export default function IntegrationDetailPage() {
  const { integrationId } = useParams<{ integrationId: string }>();
  const [detail, setDetail] = useState<IntegrationDetailResponse | null>(null);
  const [latency, setLatency] = useState<LatencyLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [runningCollector, setRunningCollector] = useState(false);

  const load = useCallback(async () => {
    if (!integrationId) return;
    try {
      setError(null);
      const [detailData, latencyData] = await Promise.all([
        getIntegrationDetail(integrationId),
        getLatencyLogs(`/api/integrations/${integrationId}`, 12),
      ]);
      setDetail(detailData);
      setLatency(latencyData.reverse());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load integration detail");
    }
  }, [integrationId]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  const triggerCycle = async () => {
    setRunningCollector(true);
    try {
      await runMockCollectorCycle();
      await load();
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Could not run collector cycle");
    } finally {
      setRunningCollector(false);
    }
  };

  if (!integrationId) {
    return (
      <section className="page" data-testid="integration-detail-missing-id">
        <div className="card">Integration ID is missing.</div>
      </section>
    );
  }

  if (!detail && !error) {
    return (
      <section className="page" data-testid="integration-detail-loading">
        <div className="card">Loading integration details...</div>
      </section>
    );
  }

  return (
    <section className="page" data-testid="integration-detail-page">
      {error && (
        <p className="error-banner" data-testid="integration-detail-error-message">
          {error}
        </p>
      )}

      {detail && (
        <>
          <div className="page-header">
            <div>
              <h2 className="page-title" data-testid="integration-detail-title">
                {detail.integration.name}
              </h2>
              <p className="muted" data-testid="integration-detail-meta">
                {detail.integration.integration_id} · {detail.integration.project} · {detail.integration.business_domain}
              </p>
            </div>
            <button
              className="button-primary"
              onClick={triggerCycle}
              disabled={runningCollector}
              data-testid="integration-detail-run-collector-button"
            >
              {runningCollector ? "Running" : "Run Collector Cycle"}
            </button>
          </div>

          <div className="detail-grid" data-testid="integration-detail-grid">
            <div className="stack">
              <section className="card" data-testid="integration-detail-overview-panel">
                <h3 className="section-heading" data-testid="integration-overview-heading">
                  Integration Overview
                </h3>
                <div className="key-value-grid">
                  <p data-testid="integration-owner-label">Owner</p>
                  <p data-testid="integration-owner-value">{detail.integration.owner}</p>
                  <p data-testid="integration-endpoint-label">Endpoint</p>
                  <p data-testid="integration-endpoint-value">{detail.endpoint_url}</p>
                  <p data-testid="integration-last-run-label">Last Run</p>
                  <p data-testid="integration-last-run-value">
                    {new Date(detail.integration.last_run_at).toLocaleString()}
                  </p>
                  <p data-testid="integration-success-label">Success Rate</p>
                  <p data-testid="integration-success-value">{detail.integration.success_rate.toFixed(2)}%</p>
                </div>
              </section>

              <section className="card" data-testid="integration-run-history-panel">
                <h3 className="section-heading" data-testid="integration-run-history-heading">
                  Recent Run History
                </h3>
                <div className="table-wrap">
                  <table className="data-table" data-testid="integration-run-history-table">
                    <thead>
                      <tr>
                        <th data-testid="run-history-th-time">Time</th>
                        <th data-testid="run-history-th-status">Status</th>
                        <th data-testid="run-history-th-duration">Duration</th>
                        <th data-testid="run-history-th-error">Error Type</th>
                        <th data-testid="run-history-th-message">Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.recent_runs.map((run, index) => (
                        <tr key={`${run.event_time}-${index}`} data-testid={`run-history-row-${index}`}>
                          <td data-testid={`run-history-time-${index}`}>
                            {new Date(run.event_time).toLocaleString()}
                          </td>
                          <td>
                            <StatusBadge status={run.run_status} testId={`run-history-status-${index}`} />
                          </td>
                          <td data-testid={`run-history-duration-${index}`}>{run.duration_ms} ms</td>
                          <td data-testid={`run-history-error-${index}`}>{run.error_type ?? "-"}</td>
                          <td data-testid={`run-history-message-${index}`}>{run.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>

            <div className="stack">
              <section className="card" data-testid="integration-status-panel">
                <h3 className="section-heading" data-testid="integration-status-heading">
                  Current Status
                </h3>
                <div className="stack">
                  <StatusBadge status={detail.integration.status} testId="integration-status-value" />
                  <p data-testid="integration-failed-instances-value">
                    Failed instances: {detail.integration.failed_instances}
                  </p>
                  <p data-testid="integration-connection-errors-value">
                    Connection errors: {detail.integration.connection_errors}
                  </p>
                  <p data-testid="integration-timeouts-value">Timeouts: {detail.integration.timeouts}</p>
                  <p data-testid="integration-aborted-runs-value">
                    Aborted runs: {detail.integration.aborted_runs}
                  </p>
                  <p data-testid="integration-scheduled-missed-value">
                    Scheduled runs missed: {detail.integration.scheduled_runs_missed}
                  </p>
                </div>
              </section>

              <ErrorRecommendations items={detail.recommendations} />
              <LatencyPanel logs={latency} title="Detail Endpoint Latency" testId="detail-latency-panel" />
            </div>
          </div>
        </>
      )}
    </section>
  );
}
