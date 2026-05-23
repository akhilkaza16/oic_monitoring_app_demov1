import { Recommendation } from "../types";

interface Props {
  items: Recommendation[];
}

export const ErrorRecommendations = ({ items }: Props) => {
  return (
    <section className="card" data-testid="recommendations-panel">
      <h3 className="section-heading" data-testid="recommendations-heading">
        Error Recommendations (Top 3)
      </h3>
      <div className="stack" data-testid="recommendations-list">
        {items.map((item) => (
          <article
            key={item.priority}
            className="recommendation-item"
            data-testid={`recommendation-priority-${item.priority}`}
          >
            <p className="recommendation-title" data-testid={`recommendation-title-${item.priority}`}>
              Priority {item.priority}: {item.title}
            </p>
            <p className="muted" data-testid={`recommendation-rationale-${item.priority}`}>
              {item.rationale}
            </p>
            <p className="recommendation-action" data-testid={`recommendation-action-${item.priority}`}>
              Action: {item.action}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
};
