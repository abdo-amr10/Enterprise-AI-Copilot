const value = (name, fallback = "") => import.meta.env[name] ?? fallback;
export const env = {
  apiBaseUrl: value("VITE_API_BASE_URL"),
  useMockApi: value("VITE_USE_MOCK_API", "true") !== "false",
};
