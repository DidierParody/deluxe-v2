from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class LLMResponse:
    text: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None

class LLMClient(ABC):
    """Abstract interface for LLM clients."""
    
    @abstractmethod
    async def chat(self, messages: List[Dict[str, Any]], tools: List[Any]) -> LLMResponse:
        """
        Sends messages to the LLM with the provided tools.
        Returns an LLMResponse.
        """
        pass
    
    @abstractmethod
    def convert_tools(self, mcp_tools: List[Any]) -> List[Any]:
        """
        Converts FastMCP tools to the specific format required by the provider.
        """
        pass
