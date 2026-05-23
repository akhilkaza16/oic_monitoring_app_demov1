import { AuditLogEntry } from "../../types";

interface SettingsAuditLogsTableProps {
  auditLogs: AuditLogEntry[];
}

export const SettingsAuditLogsTable = ({ auditLogs }: SettingsAuditLogsTableProps) => {
  return (
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
                <td data-testid={`audit-time-${entry.id}`}>{new Date(entry.created_at).toLocaleString()}</td>
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
  );
};
