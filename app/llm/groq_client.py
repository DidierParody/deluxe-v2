from groq import AsyncGroq
from app.config import settings
from app.llm.base import LLMClient, LLMResponse, ToolCall
import json
from typing import List, Dict, Any

class GroqClient(LLMClient):
    def __init__(self):
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model = settings.GROQ_MODEL

    def convert_tools(self, mcp_tools: List[Any]) -> List[Dict[str, Any]]:
        """
        Convert FastMCP tools to OpenAI/Groq function calling format.
        """
        if not mcp_tools:
            return None
            
        groq_tools = []
        for tool in mcp_tools:
            groq_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return groq_tools

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Any]) -> LLMResponse:
        groq_tools = self.convert_tools(tools) if tools else None
        
        groq_messages = []
        for msg in messages:
            if msg["role"] == "system":
                groq_messages.append({"role": "system", "content": msg["content"]})
            elif msg["role"] == "user":
                groq_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                m = {"role": "assistant"}
                if msg.get("content"):
                    m["content"] = msg["content"]
                if msg.get("tool_calls"):
                    m["tool_calls"] = []
                    for tc in msg["tool_calls"]:
                        m["tool_calls"].append({
                            "id": tc.id or f"call_{tc.name}",
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        })
                groq_messages.append(m)
            elif msg["role"] == "tool":
                groq_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", f"call_{msg.get('name')}"),
                    "name": msg.get("name"),
                    "content": msg["content"]
                })

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=groq_messages,
            tools=groq_tools,
            tool_choice="auto" if groq_tools else "none",
            temperature=0.3
        )

        message = response.choices[0].message
        
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                ))
            return LLMResponse(tool_calls=tool_calls)
            
        return LLMResponse(text=message.content)
