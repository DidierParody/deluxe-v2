from google import genai
from google.genai import types
from app.config import settings
from app.llm.base import LLMClient, LLMResponse, ToolCall
import json
from typing import List, Dict, Any

class GoogleClient(LLMClient):
    def __init__(self):
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.GOOGLE_MODEL

    def _remove_additional_properties(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively removes additionalProperties from JSON schema as Google doesn't support it."""
        if not isinstance(schema, dict):
            return schema
            
        new_schema = {}
        for k, v in schema.items():
            if k in ("additionalProperties", "additional_properties"):
                continue
            if isinstance(v, dict):
                new_schema[k] = self._remove_additional_properties(v)
            elif isinstance(v, list):
                new_schema[k] = [self._remove_additional_properties(item) if isinstance(item, dict) else item for item in v]
            else:
                new_schema[k] = v
        return new_schema

    def convert_tools(self, mcp_tools: List[Any]) -> List[Any]:
        google_tools = []
        for tool in mcp_tools:
            parameters = self._remove_additional_properties(tool.parameters)
            func_decl = types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=parameters
            )
            google_tools.append(func_decl)
        
        if not google_tools:
            return None
        return [types.Tool(function_declarations=google_tools)]

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Any]) -> LLMResponse:
        contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg["role"]
            
            if role == "system":
                system_instruction = msg["content"]
                continue
                
            if role == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])]))
                
            elif role == "assistant":
                if msg.get("tool_calls"):
                    parts = []
                    for tc in msg["tool_calls"]:
                        parts.append(types.Part.from_function_call(
                            name=tc.name,
                            args=tc.arguments
                        ))
                    contents.append(types.Content(role="model", parts=parts))
                elif msg.get("content"):
                    contents.append(types.Content(role="model", parts=[types.Part.from_text(text=msg["content"])]))
                    
            elif role == "tool":
                part = types.Part.from_function_response(
                    name=msg.get("name", "tool"),
                    response={"result": msg["content"]}
                )
                # Google expects tool responses as role="user"
                # If the previous message is also a tool response, we could merge parts,
                # but appending as consecutive user messages usually works or we can just append
                contents.append(types.Content(role="user", parts=[part]))

        google_tools = self.convert_tools(tools) if tools else None

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=google_tools,
                temperature=0.3,
                system_instruction=system_instruction
            )
        )

        if response.function_calls:
            # Handle multiple function calls
            tool_calls = []
            for fc in response.function_calls:
                tool_calls.append(ToolCall(
                    id=fc.name, # Google doesn't use call IDs like OpenAI, using name as ID
                    name=fc.name,
                    arguments=fc.args
                ))
            return LLMResponse(tool_calls=tool_calls)
        
        return LLMResponse(text=response.text)
