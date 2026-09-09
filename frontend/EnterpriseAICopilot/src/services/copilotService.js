import { request } from "./httpClient";

// POST /api/v1/copilot/ask
// conversationId is null for a new conversation and retained for follow-up questions.
export function askCopilot({ question, conversationId = null, conversation = [] }) {
  return request("/api/v1/copilot/ask", {
    method: "POST",
    body: JSON.stringify({ question, conversationId, conversation }),
  });
}

export function fetchConversations() {
  return request("/api/v1/copilot/conversations");
}

export function extractConversationId(response) {
  return response?.conversationId || response?.ConversationId || response?.id || response?.conversation?.conversationId || response?.conversation?.ConversationId || response?.conversation?.id || response?.Conversation?.conversationId || response?.Conversation?.id || null;
}

export async function findConversationIdForQuestion(question) {
  const response = await fetchConversations();
  const items = Array.isArray(response) ? response : response?.items || response?.conversations || response?.data || [];
  const normalizedQuestion = String(question || '').trim().toLowerCase();
  const matches = items.filter((item) => [item?.title, item?.lastQuestion].some((value) => String(value || '').trim().toLowerCase() === normalizedQuestion));
  matches.sort((left, right) => new Date(right?.updatedAt || right?.createdAt || 0) - new Date(left?.updatedAt || left?.createdAt || 0));
  return extractConversationId(matches[0]);
}

export function fetchConversation(conversationId) {
  return request(`/api/v1/copilot/conversations/${encodeURIComponent(conversationId)}`);
}

export function deleteConversation(conversationId) {
  return request(`/api/v1/copilot/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });
}

export function getConversationMessages(conversation) {
  const messages = conversation?.turns || conversation?.messages || conversation?.items || conversation?.conversation || [];
  return Array.isArray(messages) ? messages : [];
}
