"""Tool-level scope checking utilities for MCP servers."""

from enum import Enum
from typing import Any

from pydantic import AnyHttpUrl

from mcp.server.auth.middleware.auth_context import auth_context_var, get_access_token


class AuthorizationResult(str, Enum):
    """Authorization check result."""

    OK = "ok"
    MISSING_AUTH = "missing_auth"
    INSUFFICIENT_SCOPE = "insufficient_scope"


def check_tool_authorization(required_scopes: list[str] | None) -> tuple[AuthorizationResult, str | None]:
    """
    Check if the current request is authorized to call a tool with the given required scopes.

    Args:
        required_scopes: List of OAuth scopes required to call the tool. If None or empty,
            no authorization is required.

    Returns:
        Tuple of (authorization_result, missing_scope). missing_scope is only set when
        authorization_result is INSUFFICIENT_SCOPE.
    """
    # No scopes required, authorization passes
    if not required_scopes:
        return AuthorizationResult.OK, None

    # Get access token from context
    access_token = get_access_token()
    if access_token is None:
        return AuthorizationResult.MISSING_AUTH, None

    # Check if token has all required scopes
    token_scopes = set(access_token.scopes)
    for required_scope in required_scopes:
        if required_scope not in token_scopes:
            return AuthorizationResult.INSUFFICIENT_SCOPE, required_scope

    return AuthorizationResult.OK, None


def build_www_authenticate_header(
    error: str,
    error_description: str,
    required_scopes: list[str] | None = None,
    resource_metadata_url: AnyHttpUrl | None = None,
) -> str:
    """
    Build a WWW-Authenticate header value with scope parameter.

    Args:
        error: Error code (e.g., "invalid_token", "insufficient_scope")
        error_description: Human-readable error description
        required_scopes: Optional list of required scopes to include in scope parameter
        resource_metadata_url: Optional protected resource metadata URL

    Returns:
        WWW-Authenticate header value (e.g., 'Bearer error="...", scope="...", ...')
    """
    www_auth_parts = [f'error="{error}"', f'error_description="{error_description}"']

    # Add scope parameter if required scopes are provided
    if required_scopes:
        scope_value = " ".join(required_scopes)
        www_auth_parts.append(f'scope="{scope_value}"')

    # Add resource_metadata if available
    if resource_metadata_url:
        www_auth_parts.append(f'resource_metadata="{resource_metadata_url}"')

    return f"Bearer {', '.join(www_auth_parts)}"
