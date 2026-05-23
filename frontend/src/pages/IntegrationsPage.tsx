import { useCallback, useEffect, useState } from "react";
import { FunnelSimple, MagnifyingGlass } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { getFilterOptions, getIntegrations } from "../api";
import { FilterOptions, IntegrationSummary } from "../types";
import { StatusBadge } from "../components/StatusBadge";

const PAGE_SIZE = 40;

export default function IntegrationsPage() {
  const [items, setItems] = useState<IntegrationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [project, setProject] = useState("");
  const [businessDomain, setBusinessDomain] = useState("");
  const [search, setSearch] = useState("");
  const [options, setOptions] = useState<FilterOptions>({ projects: [], business_domains: [] });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const response = await getIntegrations({
        status,
        project,
        business_domain: businessDomain,
        search,
        limit: PAGE_SIZE,
        offset,
      });
      setItems(response.items);
      setTotal(response.total);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load integrations");
    }
  }, [status, project, businessDomain, search, offset]);

  useEffect(() => {
    getFilterOptions()
      .then(setOptions)
      .catch(() => setOptions({ projects: [], business_domains: [] }));
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section className="page" data-testid="integrations-page">
      <div className="page-header">
        <div>
          <h2 className="page-title" data-testid="integrations-page-title">
            Integration List
          </h2>
          <p className="muted" data-testid="integrations-page-subtitle">
            170 mock integrations across projects and business domains · auto-refresh every 30 seconds
          </p>
        </div>
      </div>

      <section className="card" data-testid="integrations-filter-panel">
        <div className="filter-grid">
          <label className="field">
            <span data-testid="status-filter-label">
              <FunnelSimple size={16} /> Status
            </span>
            <select
              value={status}
              onChange={(event) => {
                setOffset(0);
                setStatus(event.target.value);
              }}
              data-testid="integrations-status-filter"
            >
              <option value="">All</option>
              <option value="healthy">Healthy</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>

          <label className="field">
            <span data-testid="project-filter-label">Project</span>
            <select
              value={project}
              onChange={(event) => {
                setOffset(0);
                setProject(event.target.value);
              }}
              data-testid="integrations-project-filter"
            >
              <option value="">All</option>
              {options.projects.map((entry) => (
                <option value={entry} key={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span data-testid="domain-filter-label">Business Domain</span>
            <select
              value={businessDomain}
              onChange={(event) => {
                setOffset(0);
                setBusinessDomain(event.target.value);
              }}
              data-testid="integrations-domain-filter"
            >
              <option value="">All</option>
              {options.business_domains.map((entry) => (
                <option value={entry} key={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span data-testid="search-filter-label">
              <MagnifyingGlass size={16} /> Search
            </span>
            <input
              value={search}
              onChange={(event) => {
                setOffset(0);
                setSearch(event.target.value);
              }}
              placeholder="Name or integration ID"
              data-testid="integrations-search-input"
            />
          </label>
        </div>
      </section>

      {error && (
        <p className="error-banner" data-testid="integrations-error-message">
          {error}
        </p>
      )}

      <section className="card" data-testid="integrations-table-panel">
        <div className="table-wrap">
          <table className="data-table" data-testid="integrations-table">
            <thead>
              <tr>
                <th data-testid="integrations-th-id">Integration</th>
                <th data-testid="integrations-th-project">Project</th>
                <th data-testid="integrations-th-domain">Domain</th>
                <th data-testid="integrations-th-status">Status</th>
                <th data-testid="integrations-th-failed">Failed</th>
                <th data-testid="integrations-th-timeouts">Timeouts</th>
                <th data-testid="integrations-th-success">Success Rate</th>
                <th data-testid="integrations-th-run">Last Run</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.integration_id} data-testid={`integration-row-${item.integration_id}`}>
                  <td>
                    <Link
                      to={`/integrations/${item.integration_id}`}
                      className="table-link"
                      data-testid={`integration-detail-link-${item.integration_id}`}
                    >
                      <span data-testid={`integration-name-${item.integration_id}`}>{item.name}</span>
                      <small data-testid={`integration-id-${item.integration_id}`}>{item.integration_id}</small>
                    </Link>
                  </td>
                  <td data-testid={`integration-project-${item.integration_id}`}>{item.project}</td>
                  <td data-testid={`integration-domain-${item.integration_id}`}>{item.business_domain}</td>
                  <td>
                    <StatusBadge status={item.status} testId={`integration-status-${item.integration_id}`} />
                  </td>
                  <td data-testid={`integration-failed-${item.integration_id}`}>{item.failed_instances}</td>
                  <td data-testid={`integration-timeouts-${item.integration_id}`}>{item.timeouts}</td>
                  <td data-testid={`integration-success-rate-${item.integration_id}`}>
                    {item.success_rate.toFixed(2)}%
                  </td>
                  <td data-testid={`integration-last-run-${item.integration_id}`}>
                    {new Date(item.last_run_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="table-footer" data-testid="integrations-pagination-footer">
          <p data-testid="integrations-pagination-status">
            Page {currentPage} of {totalPages} · Total {total} integrations
          </p>
          <div className="actions-inline">
            <button
              className="button-secondary"
              onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
              disabled={offset === 0}
              data-testid="integrations-prev-page-button"
            >
              Previous
            </button>
            <button
              className="button-primary"
              onClick={() => setOffset((current) => (current + PAGE_SIZE < total ? current + PAGE_SIZE : current))}
              disabled={offset + PAGE_SIZE >= total}
              data-testid="integrations-next-page-button"
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </section>
  );
}
