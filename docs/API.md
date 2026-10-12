# Shared assistant API

GET /api/copilot/info reports the app origin and stable data-space identity. GET /api/copilot/launcher.js provides the shared launcher; GET /api/copilot/panel.js and /api/copilot/proxy relay the configured global Faustus service. Tokens remain on the server.

The context includes the selected capture, day or current native session, search/filter state and complete pending form fields. Timeline sessions are revalidated through current /api/sessions data and cached search hits through /api/frames/{id}; removed records provide no active ID. Turn completion refreshes visible data while preserving the pending search query and form drafts.

The existing12 MCP tools remain available through mcp_server.py and the native /api/agent/tools and /api/agent/call contracts. Faustus keeps conversations and agent execution. Recording, OCR, exclusions, retention, private mode and configured backends retain their native settings; no duplicate agent loop is introduced.
