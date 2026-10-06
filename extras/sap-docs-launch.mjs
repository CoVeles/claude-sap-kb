// Starts a local marianfoo/mcp-sap-docs checkout as a stdio MCP server.
// The server resolves its index relative to the working directory, and MCP client configs
// have no cwd field — so switch into the checkout first, then load the server.
//
//   claude mcp add -s user sap-docs -e SAP_DOCS_ROOT=/path/to/mcp-sap-docs -- node /path/to/sap-docs-launch.mjs
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.env.SAP_DOCS_ROOT;
if (!root) {
  console.error('SAP_DOCS_ROOT is not set — point it at your mcp-sap-docs checkout.');
  process.exit(1);
}
const server = join(root, 'dist', 'src', 'server.js');
if (!existsSync(server)) {
  console.error(`No built server at ${server} — run "bash setup.sh" in the checkout first.`);
  process.exit(1);
}
process.chdir(root);
process.env.MCP_VARIANT ??= 'sap-docs';
await import(pathToFileURL(server).href);
