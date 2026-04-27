from fastmcp import FastMCP
from typing import List, Any
import inspect

class CustomMCP(FastMCP):
    async def get_role_tools(self, role: str) -> List[Any]:
        """
        Filters tools based on role.
        Admin tools have names starting with 'admin_' or are specifically marked.
        For simplicity, we'll prefix admin tools with 'admin_'.
        """
        all_tools = await self.list_tools()
        if role == "admin":
            return all_tools
            
        # User only gets non-admin tools
        return [t for t in all_tools if not t.name.startswith("admin_")]

# Create the singleton MCP server instance
mcp = CustomMCP("deluxe")

# Import the tools to register them
import app.mcp.user_tools
import app.mcp.admin_tools
