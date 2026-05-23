import { LatencyLog } from "../types";

interface Props {
  logs: LatencyLog[];
  title: string;
  testId: string;
}

export const LatencyPanel = ({ logs, title, testId }: Props) => {
  const maxLatency = Math.max(...logs.map((item) => item.latency_ms), 1);

  return (
    <section className="card" data-testid={testId}>
      <h3 className="section-heading" data-testid={`${testId}-heading`}>
        {title}
      </h3>
      <div className="stack" data-testid={`${testId}-rows`}>
        {logs.length === 0 && (
          <p className="muted" data-testid={`${testId}-empty`}>
            Latency data will appear after API calls are made.
          </p>
        )}
        {logs.map((log, index) => (
          <div className="latency-row" key={`${log.endpoint}-${index}`} data-testid={`${testId}-row-${index}`}>
            <div className="latency-headline">
              <span data-testid={`${testId}-row-${index}-endpoint`}>{log.endpoint}</span>
              <span data-testid={`${testId}-row-${index}-value`}>{log.latency_ms.toFixed(1)} ms</span>
            </div>
            <div className="latency-track">
              <div
                className="latency-fill"
                style={{ width: `${Math.max(6, (log.latency_ms / maxLatency) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
