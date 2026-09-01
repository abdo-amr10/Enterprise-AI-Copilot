

import { IconCheck, IconSparkles } from "./icons";
import ExportMenu from "./ExportMenu";
import "../styles/summary-card.css";

function humanizeKey(key) {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value) {
  if (typeof value === "number") return value.toLocaleString();
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

// `data` is whatever `report.data` the backend sent back for this
// question — its shape isn't fixed, so this decides how to present it:
// a single row with one field renders as a big headline number (like a
// KPI), anything with more rows/columns renders as a real table, and if
// there's no tabular data at all we just show the plain-language answer.
export default function SummaryCard({ question, textSummary, data, status = "Completed", queryId, askedAt }) {
  const rows = Array.isArray(data) ? data : [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  const isSingleMetric = rows.length === 1 && columns.length === 1;
  const hasResult = Boolean(textSummary && textSummary.trim()) || rows.length > 0;

  return (
    <article className="summary-card" aria-label="Copilot answer summary">
      <header className="summary-card-header">
        <span className="summary-card-ai">
          <IconSparkles aria-hidden="true" /> Copilot
        </span>
        <span className="summary-card-status">
          <IconCheck aria-hidden="true" /> {status}
        </span>
      </header>

      <div className="summary-card-body">
        {isSingleMetric ? (
          <>
            <p className="summary-card-label">{humanizeKey(columns[0])}</p>
            <strong className="summary-card-value">{formatValue(rows[0][columns[0]])}</strong>
          </>
        ) : null}

        {textSummary ? <p className="summary-card-description">{textSummary}</p> : null}

        {!isSingleMetric && rows.length > 0 ? (
          <div className="summary-card-table-wrap">
            <table className="summary-card-table">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col}>{humanizeKey(col)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    {columns.map((col) => (
                      <td key={col}>{formatValue(row[col])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      <footer className="summary-card-footer">
        <span>
          {queryId ? `Query ID: ${queryId}` : "Based on the information available to you."}
          {askedAt ? ` · ${askedAt}` : ""}
        </span>
        {hasResult ? <ExportMenu payload={{ question, textSummary, data: rows, queryId, status }} /> : null}
      </footer>
    </article>
  );
}
