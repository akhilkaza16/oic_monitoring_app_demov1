interface Props {
  label: string;
  value: string | number;
  helper: string;
  testId: string;
}

export const MetricCard = ({ label, value, helper, testId }: Props) => {
  return (
    <article className="card metric-card" data-testid={`${testId}-card`}>
      <p className="metric-label" data-testid={`${testId}-label`}>
        {label}
      </p>
      <p className="metric-value" data-testid={`${testId}-value`}>
        {value}
      </p>
      <p className="metric-helper" data-testid={`${testId}-helper`}>
        {helper}
      </p>
    </article>
  );
};
