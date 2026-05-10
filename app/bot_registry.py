"""
Global registry for bot instances and the compiled LangGraph graph.
main.py writes here at startup; handlers read from here to avoid circular imports.
"""
from telegram.ext import Application

bot_cs_app: Application = None
bot_am_app: Application = None
graph = None   # compiled LangGraph — set by main.py lifespan after Redis is ready
