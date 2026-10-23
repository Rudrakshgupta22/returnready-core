# ReturnReady - Friction Log

**Specific Task Attempted:** 
Setting up the FastMCP Python server to run over Streamable HTTP and comply strictly with the `2025-11-25` Model Context Protocol specification for the backend orchestrator.

**Steps Taken:** 
1. Executed standard installation via `pip install mcp[cli]`.
2. Attempted to initialize the `FastMCP` class based on early hackathon documentation.
3. Attempted to connect the FastAPI client utilizing the standard `/sse` transport endpoint.

**Expected vs. Actual Result:** 
* **Expected:** The server successfully boots and accepts Streamable HTTP connections conforming to the `2025-11-25` spec.
* **Actual:** Encountered breaking class changes (fatal import errors) because the latest `mcp[cli]` pulled version 2.x, which renamed/restructured core classes (e.g., `FastMCP` to `MCPServer`). Additionally, the v1.x vs v2.x transport defaults mismatched, resulting in persistent 404 errors during the protocol handshake.

**Severity Rating:** 
High (Development Blocker / Core architecture failure).

**Workaround Used:** 
Strictly pinned the dependency to `"mcp[cli]<2"` in both `pyproject.toml` and `requirements.txt`. We then manually configured the FastMCP initialization to explicitly map the transport route to `/sse` and enforced the `2025-11-25` protocol version string in the FastAPI client handshake.

**Actionable Suggestion:** 
Provide a clear, prominent migration guide or version-compatibility matrix on the main MCP SDK documentation page. When a major version bump (v1 to v2) introduces breaking class name changes, adding terminal warnings for users attempting to import legacy classes would drastically reduce debugging time.
