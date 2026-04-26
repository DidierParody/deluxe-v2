# Helper function if needed in the future, 
# but conversion is now handled inside each client (GoogleClient and GroqClient)
# via the LLMClient interface.
# This file is kept as a placeholder or for shared MCP utilities.

def get_tools_for_role(mcp_server, role: str) -> list:
    """
    Returns the list of tools available for the given role from the FastMCP server.
    User gets only user tools. Admin gets all tools.
    """
    all_tools = mcp_server._tools.values() # FastMCP internal dict
    
    if role == "admin":
        return list(all_tools)
        
    # If customer, filter only customer tools.
    # We can identify them by a prefix, or maintain a list of names.
    # Let's say user tools don't have 'admin_' prefix and admin tools do, 
    # or we maintain a static list.
    
    # We'll use a static list or naming convention in server.py
    # For now, let the server handle it by asking the server object directly.
    return mcp_server.get_role_tools(role)
