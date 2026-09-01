import * as XLSX from "xlsx";

// Turns whatever `report.data` the backend returned into rows a
// spreadsheet/table can render. Falls back to a single Question/Answer
// row when the backend didn't return tabular data (a plain narrative
// answer), so export always has something sensible to produce.
function toRows({ question, textSummary, data }) {
  if (Array.isArray(data) && data.length > 0) return data;
  return [{ Question: question, Answer: textSummary }];
}

export function exportToExcel(payload) {
  const rows = toRows(payload);
  const sheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, "Copilot answer");
  XLSX.writeFile(workbook, `copilot-${payload.queryId || Date.now()}.xlsx`);
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char])
  );
}

function buildResultHtml({ question, textSummary, data, queryId, status }) {
  const hasTable = Array.isArray(data) && data.length > 0;
  const columns = hasTable ? Object.keys(data[0]) : [];

  const tableHtml = hasTable
    ? `<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;margin-top:16px">
        <thead><tr>${columns
          .map((col) => `<th style="background:#00174b;color:#fff;text-align:left;padding:8px">${escapeHtml(col)}</th>`)
          .join("")}</tr></thead>
        <tbody>${data
          .map(
            (row) =>
              `<tr>${columns.map((col) => `<td style="padding:8px;border:1px solid #dbe1ee">${escapeHtml(row[col])}</td>`).join("")}</tr>`
          )
          .join("")}</tbody>
      </table>`
    : "";

  return `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>Copilot answer</title>
    <style>
      body{font-family:Arial,sans-serif;color:#131b2e;padding:28px;max-width:760px;margin:0 auto}
      h1{font-size:19px;margin:0 0 6px}
      .meta{color:#6f778e;font-size:12px;margin:0 0 20px}
      .summary{font-size:14px;line-height:1.7}
    </style></head>
    <body>
      <h1>${escapeHtml(question)}</h1>
      <p class="meta">Query ID: ${escapeHtml(queryId || "-")} · Status: ${escapeHtml(status || "-")}</p>
      <p class="summary">${escapeHtml(textSummary)}</p>
      ${tableHtml}
    </body></html>`;
}

export function exportToWord(payload) {
  const html = buildResultHtml(payload);
  const blob = new Blob(["\ufeff", html], { type: "application/msword" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `copilot-${payload.queryId || Date.now()}.doc`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function printResult(payload) {
  const html = buildResultHtml(payload);
  const printWindow = window.open("", "_blank", "width=900,height=700");
  if (!printWindow) return;
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  printWindow.onload = () => printWindow.print();
}
