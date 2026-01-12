# Simple Notebook MCP Client (Aggregated Scopes)

This client demonstrates OAuth authentication with aggregated scope handling. Unlike the basic client that requests scopes individually as needed, this client:

1. **Discovers tool scope requirements** by calling `list_tools()` first
2. **Aggregates scopes** for multiple tools (`list_notes` and `add_note`)
3. **Requests a single token** with all required scopes upfront (e.g., "read write")
4. **Calls multiple tools** using the same token without additional OAuth flows

## Prerequisites

- Python 3.10+
- Running notebook MCP server (see `examples/servers/simple-notebook/README.md`)
- Running authorization server (see `examples/servers/simple-notebook/README.md`)

## Installation

```bash
cd examples/clients/simple-notebook-client-aggregated
uv sync
```

## Usage

### Run the Client

```bash
uv run mcp-simple-notebook-client-aggregated

# Or with custom server port
MCP_SERVER_PORT=8001 uv run mcp-simple-notebook-client-aggregated
```

## What It Does

This client demonstrates the aggregated scope OAuth authentication flow:

1. **Connects to the notebook server** - Initiates MCP session
2. **Calls `list_tools()` tool** - Discovers available tools and their scope requirements
   - Extracts `required_scopes` from each tool's `meta` field
   - Displays all tools and their scope requirements
3. **Aggregates scopes** - Collects scope requirements for `list_notes` and `add_note`
   - Creates a union of all required scopes (e.g., "read" + "write" = "read write")
   - Sets the aggregated scopes in the OAuth client metadata
4. **Calls `list_notes` tool** - Triggers OAuth flow with all aggregated scopes
   - Receives a token with all required scopes (e.g., "read write")
   - Calls `list_notes` successfully
5. **Calls `add_note` tool** - Uses the existing token with aggregated scopes
   - No new OAuth flow needed (all required scopes already granted)
   - Calls `add_note` successfully

## Example Output

```
📓 Simple Notebook MCP Client (Aggregated Scopes)
Connecting to: http://localhost:8001/mcp

📡 Opening StreamableHTTP transport connection with auth...
🤝 Initializing MCP session...
✨ Session initialization complete!

🔧 Step 1: Listing available tools and extracting scope requirements...
✅ list_tools succeeded!

📋 Found 4 tool(s):
  - list_notes
    Description: List all notes.
    Required scopes: read

  - read_note
    Description: Read a specific note by ID.
    Required scopes: read

  - add_note
    Description: Add a new note.
    Required scopes: write

  - edit_note
    Description: Edit an existing note.
    Required scopes: write

🔐 Step 2: Aggregating scopes for target tools: list_notes, add_note
   Aggregated scopes: read write

✅ Set OAuth client metadata scope to: read write

📋 Step 3: Calling list_notes tool...
🌐 Opening browser for authorization: http://localhost:9000/authorize?...
⏳ Waiting for authorization callback...
✅ list_notes succeeded!

📝 Found 2 note(s):
  - ID: note_abc123
    Title: My First Note
    Created: 2024-01-01T12:00:00+00:00

  - ID: note_def456
    Title: Another Note
    Created: 2024-01-01T13:00:00+00:00

✏️  Step 4: Calling add_note tool (requires 'write' scope from aggregated scopes)...
✅ add_note succeeded!

📄 New note created:
  ID: note_xyz789
  Title: My New Note (Aggregated)
  Content: This note was added using the aggregated scope client!
  Created: 2024-01-01T14:00:00+00:00
  Updated: 2024-01-01T14:00:00+00:00
```

## Key Differences from Basic Client

- **Single OAuth flow**: Requests all needed scopes upfront
- **Efficient**: No multiple authorization requests
- **Scope discovery**: Uses `list_tools()` to discover requirements dynamically
- **Scope aggregation**: Combines scopes from multiple tools automatically

## Notes

- The client uses port 3031 for the callback server (different from the basic client's port 3030)
- `list_notes` requires 'read' scope and `add_note` requires 'write' scope
- The aggregated scope includes both: "read write"
- Both tools work with a single token that has all aggregated scopes, eliminating the need for multiple OAuth flows
