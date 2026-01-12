# Notebook MCP Server with Scope-based OAuth Authentication

This example demonstrates scope-based OAuth 2.0 authentication with the Model Context Protocol using **separate Authorization Server (AS) and Resource Server (RS)** to comply with the RFC 9728 specification.

The server implements a simple notebook with 4 tools that require different OAuth scopes:
- **Read scope** (`read`): `list_notes`, `read_note`
- **Write scope** (`write`): `add_note`, `edit_note`

## Authentication Flow

This example demonstrates the complete OAuth flow with scope-based authorization:

1. **Client tries to access a tool without token** → Server returns `401 Unauthorized` with `WWW-Authenticate` header containing the required scope:
   ```
   WWW-Authenticate: Bearer error="invalid_token", error_description="Authentication required", scope="read"
   ```

2. **Client initiates OAuth flow** → Client requests a token with the scope from the header (`read`)

3. **Client retries the tool** → Client calls the tool again with the Bearer token and succeeds

4. **Client tries to access a tool with different scope** → If the client tries to call a tool requiring a different scope (e.g., `add_note` with only a `read` token), the server returns `403 Forbidden` with the required scope:
   ```
   WWW-Authenticate: Bearer error="insufficient_scope", error_description="Required scope: write", scope="write"
   ```

5. **Client initiates another OAuth flow** → Client requests a new token with the different scope (`write`)

6. **Client retries the tool** → Client calls the tool again with the new Bearer token and succeeds

## Running the Servers

### Step 1: Start Authorization Server

```bash
# Navigate to the simple-notebook directory
cd examples/servers/simple-notebook

# Start Authorization Server on port 9000
uv run mcp-simple-notebook-as --port=9000
```

**What it provides:**
- OAuth 2.0 flows (registration, authorization, token exchange)
- Support for multiple scopes: `read` and `write`
- Simple credential-based authentication (no external provider needed)
- Token introspection endpoint for Resource Servers (`/introspect`)

---

### Step 2: Start Resource Server (MCP Server)

```bash
# In another terminal, navigate to the simple-notebook directory
cd examples/servers/simple-notebook

# Start Resource Server on port 8001, connected to Authorization Server
uv run mcp-simple-notebook-rs --port=8001 --auth-server=http://localhost:9000 --transport=streamable-http

# With RFC 8707 strict resource validation (recommended for production)
uv run mcp-simple-notebook-rs --port=8001 --auth-server=http://localhost:9000 --transport=streamable-http --oauth-strict
```

---

### Step 3: Test with Client

You can test the server using the existing `simple-auth-client` example:

```bash
cd examples/clients/simple-auth-client
# Start client with streamable HTTP
MCP_SERVER_PORT=8001 MCP_TRANSPORT_TYPE=streamable-http uv run mcp-simple-auth-client
```

## Tools

The server provides 4 tools:

### Read Scope Tools

#### `list_notes`
Lists all notes. Returns a list of note IDs, titles, and timestamps.

**Required scope:** `read`

**Example:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "list_notes",
    "arguments": {}
  }
}
```

#### `read_note`
Reads a specific note by ID.

**Required scope:** `read`

**Parameters:**
- `note_id` (string): The ID of the note to read

**Example:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "read_note",
    "arguments": {
      "note_id": "note_abc123"
    }
  }
}
```

### Write Scope Tools

#### `add_note`
Creates a new note.

**Required scope:** `write`

**Parameters:**
- `title` (string): The title of the note
- `content` (string): The content of the note

**Example:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "add_note",
    "arguments": {
      "title": "My First Note",
      "content": "This is the content of my note."
    }
  }
}
```

#### `edit_note`
Edits an existing note.

**Required scope:** `write`

**Parameters:**
- `note_id` (string): The ID of the note to edit
- `title` (string, optional): New title for the note
- `content` (string, optional): New content for the note

**Example:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "edit_note",
    "arguments": {
      "note_id": "note_abc123",
      "title": "Updated Title",
      "content": "Updated content"
    }
  }
}
```

## How It Works

### RFC 9728 Discovery

**Client → Resource Server:**
```bash
curl http://localhost:8001/.well-known/oauth-protected-resource
```

```json
{
  "resource": "http://localhost:8001",
  "authorization_servers": ["http://localhost:9000"]
}
```

**Client → Authorization Server:**
```bash
curl http://localhost:9000/.well-known/oauth-authorization-server
```

```json
{
  "issuer": "http://localhost:9000",
  "authorization_endpoint": "http://localhost:9000/authorize",
  "token_endpoint": "http://localhost:9000/token",
  "scopes_supported": ["read", "write"]
}
```

### Scope-based Authorization

When a client tries to call a tool:

1. **No token provided:**
   - Server returns `401 Unauthorized`
   - `WWW-Authenticate` header includes the required scope(s)
   - Example: `WWW-Authenticate: Bearer error="invalid_token", scope="read"`

2. **Token with insufficient scope:**
   - Server returns `403 Forbidden`
   - `WWW-Authenticate` header includes the missing required scope
   - Example: `WWW-Authenticate: Bearer error="insufficient_scope", scope="write"`

3. **Token with sufficient scope:**
   - Tool execution proceeds normally
   - Returns tool result

### Token Scopes

Tokens can be issued with one or both scopes:
- `read` - Allows reading notes (list_notes, read_note)
- `write` - Allows writing notes (add_note, edit_note)
- `read write` - Allows both reading and writing

The client will automatically request the appropriate scope based on the `WWW-Authenticate` header when it receives a 401 or 403 response.

## Manual Testing

### Test Discovery

```bash
# Test Resource Server discovery endpoint
curl -v http://localhost:8001/.well-known/oauth-protected-resource

# Test Authorization Server metadata
curl -v http://localhost:9000/.well-known/oauth-authorization-server
```

### Test Token Introspection

```bash
# After getting a token through OAuth flow:
curl -X POST http://localhost:9000/introspect \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=your_access_token"
```

Response:
```json
{
  "active": true,
  "client_id": "...",
  "scope": "read",
  "exp": 1234567890,
  "iat": 1234567890,
  "token_type": "Bearer",
  "aud": "http://localhost:8001",
  "sub": "demo_user"
}
```

## Demo Credentials

The authorization server uses simple hardcoded credentials for demonstration:

- **Username:** `demo_user`
- **Password:** `demo_password`

These are pre-filled in the login form for convenience during testing.

## Notes

- Notes are stored in-memory and will be lost when the server restarts
- This is a simplified example for demonstration purposes only
- Production implementations should use persistent storage and proper authentication
