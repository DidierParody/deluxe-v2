"""
Registro global de instancias de bots.
Se usa para evitar imports circulares entre main.py y los handlers.
main.py escribe aquí al iniciar, los handlers leen de aquí.
"""
from telegram.ext import Application

bot_cs_app: Application = None
bot_am_app: Application = None
