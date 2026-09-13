export function toTurns(messages) {
  const turns = [];
  messages.forEach((message, index) => {
    const role = String(message?.role || message?.sender || "").toLowerCase();
    const question = message?.question || (role === "user" ? message?.content : "");
    if (question) {
      const status = String(message?.status || "").toLowerCase();
      turns.push({
        id: message?.id || message?.messageId || message?.queryId || `question-${index}`,
        question,
        status: status === "failed" ? "failed" : "completed",
        queryId: message?.queryId,
        report: message?.result || message?.report || { textSummary: "" },
        executionTimeMs: message?.executionTimeMs,
        errorMessage: message?.errorMessage || message?.message || "This question could not be completed.",
        askedAt: message?.createdAt,
      });
      return;
    }
    const latestTurn = turns.at(-1);
    if (!latestTurn) return;
    const result = message?.result || message?.report;
    latestTurn.status = String(message?.status || "").toLowerCase() === "failed" ? "failed" : "completed";
    latestTurn.queryId = message?.queryId;
    latestTurn.report = result || { textSummary: message?.content || message?.answer || "" };
    latestTurn.executionTimeMs = message?.executionTimeMs;
    latestTurn.errorMessage = message?.errorMessage || message?.message || "This question could not be completed.";
    latestTurn.askedAt = message?.createdAt || latestTurn.askedAt;
  });
  return turns;
}
