import { IntegrationStatus } from "../types";

interface Props {
  status: IntegrationStatus;
  testId: string;
}

const LABELS: Record<IntegrationStatus, string> = {
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  unknown: "Unknown",
};

export const StatusBadge = ({ status, testId }: Props) => {
  return (
    <span className={`status-badge status-${status}`} data-testid={testId}>
      {LABELS[status]}
    </span>
  );
};
