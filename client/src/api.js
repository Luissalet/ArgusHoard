// Thin fetch wrapper: JSON in/out, `{ error }` bodies become exceptions.
async function request(method, path, { params, body } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const response = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!response.ok) throw new Error((data && data.error) || `Error ${response.status}`);
  return data;
}

export const api = {
  status: () => request("GET", "/api/status"),
  settings: () => request("GET", "/api/settings"),
  updateSettings: (patch) => request("PUT", "/api/settings", { body: patch }),
  pause: () => request("POST", "/api/pause"),
  resume: () => request("POST", "/api/resume"),
  setPrivate: (value) => request("POST", "/api/private", { body: { private: value } }),
  exclusions: () => request("GET", "/api/exclusions"),
  addExclusion: (kind, pattern) => request("POST", "/api/exclusions", { body: { kind, pattern } }),
  toggleExclusion: (id, enabled) => request("PATCH", `/api/exclusions/${id}`, { body: { enabled } }),
  removeExclusion: (id) => request("DELETE", `/api/exclusions/${id}`),
  testExclusion: (app, title) => request("POST", "/api/exclusions/test", { body: { app, title } }),
  timeline: (params) => request("GET", "/api/timeline", { params }),
  sessions: (params) => request("GET", "/api/sessions", { params }),
  frame: (id) => request("GET", `/api/frames/${id}`),
  search: (params) => request("GET", "/api/search", { params }),
  apps: (params) => request("GET", "/api/apps", { params }),
  days: () => request("GET", "/api/days"),
  deleteRange: (from, to) => request("DELETE", "/api/frames", { params: { from, to } }),
  imageUrl: (id) => `/api/frames/${id}/image`,
  thumbUrl: (id) => `/api/frames/${id}/thumb`,
};
