# Simple Notebook MCP Client Example

A demonstration client for the Notebook MCP Server that shows how to use OAuth authentication with scope-based authorization.

## Features

- OAuth 2.0 authentication with PKCE
- Demonstrates calling `list_notes` then `read_note` tools
- Automatic scope handling via OAuth flow

## Installation

```bash
cd examples/clients/simple-notebook-client
uv sync --reinstall
```

## Usage

### Prerequisites

1. Start the Authorization Server:
   ```bash
   cd examples/servers/simple-notebook
   uv run mcp-simple-notebook-as --port=9000
   ```

2. Start the Notebook Resource Server:
   ```bash
   cd examples/servers/simple-notebook
   uv run mcp-simple-notebook-rs --port=8001 --auth-server=http://localhost:9000 --transport=streamable-http
   ```

### Run the Client

```bash
uv run mcp-simple-notebook-client

# Or with custom server port
MCP_SERVER_PORT=8001 uv run mcp-simple-notebook-client
```

## What It Does

This client demonstrates the OAuth authentication flow with scope-based authorization:

1. **Connects to the notebook server** - Initiates OAuth flow if needed
2. **Calls `list_notes` tool** - This tool requires 'read' scope
   - If no token exists, triggers OAuth flow with 'read' scope
   - Receives a token with 'read' scope
   - Calls `list_notes` successfully
3. **Calls `add_note` tool** - This tool requires 'write' scope
   - If token only has 'read' scope, triggers OAuth flow with 'write' scope
   - Receives a new token with 'write' scope (or 'read write' if both requested)
   - Calls `add_note` successfully

## Example Output

```
📓 Simple Notebook MCP Client
Connecting to: http://localhost:8001/mcp

📡 Opening StreamableHTTP transport connection with auth...
🌐 Opening browser for authorization: http://localhost:9000/authorize?...
⏳ Waiting for authorization callback...
🤝 Initializing MCP session...
✨ Session initialization complete!

📋 Step 1: Calling list_notes tool...
✅ list_notes succeeded!

📝 Found 2 note(s):
  - ID: note_abc123
    Title: My First Note
    Created: 2024-01-01T12:00:00+00:00

  - ID: note_def456
    Title: Another Note
    Created: 2024-01-01T13:00:00+00:00

✏️  Step 2: Calling add_note tool (requires 'write' scope)...
✅ add_note succeeded!

📄 New note created:
  ID: note_xyz789
  Title: My New Note
  Content: This note was added by the client example!
  Created: 2024-01-01T14:00:00+00:00
  Updated: 2024-01-01T14:00:00+00:00
```

## OAuth Flow

When you run the client:

1. **First connection** - The client will open your browser for OAuth authentication
2. **Login** - Use the demo credentials (pre-filled in the form):
   - Username: `demo_user`
   - Password: `demo_password`
3. **Authorization** - After successful login, the browser will redirect and close
4. **Token received** - The client receives a token with 'read' scope
5. **Tool calls** - The client uses this token to call `list_notes` and `read_note`

The `list_notes` tool requires the 'read' scope, while `add_note` requires the 'write' scope. If the client only has a 'read' token, calling `add_note` will trigger another OAuth flow to obtain a token with 'write' scope.

## Configuration

- `MCP_SERVER_PORT` - Server port (default: 8001)

## Notes

- The client uses a callback server on `http://localhost:3030` to receive OAuth redirects
- Tokens are stored in memory and will be lost when the client exits
- The demo uses hardcoded credentials for demonstration purposes only
