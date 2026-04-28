# Despliegue (Deploy)

El proyecto queda preparado para Render con la configuracion en `render.yaml`.

## Arquitectura propuesta en Render

- Un servicio `web` para FastAPI y los webhooks de Telegram.
- Dos servicios `cron` para ejecutar tareas periodicas:
  - `finalizar_eventos_expirados` cada 5 minutos
  - `liberar_mesas_expiradas` cada 10 minutos

Esta separacion evita depender de un scheduler embebido dentro del proceso web en produccion.

## Comandos de Render

- Build del web: `pip install -r requirements.txt`
- Start del web: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Cron 1: `python -m app.run_job finalizar_eventos_expirados`
- Cron 2: `python -m app.run_job liberar_mesas_expiradas`

## Variables de entorno del servicio web

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN_CS`
- `TELEGRAM_BOT_TOKEN_AM`
- `WEBHOOK_BASE_URL`
- `GOOGLE_API_KEY`
- `GROQ_API_KEY`
- `ENABLE_BACKGROUND_SCHEDULER=false`

## Variables de entorno de los cron jobs

- `DATABASE_URL`

## Nota importante

Configura `WEBHOOK_BASE_URL` con la URL publica real del servicio web en Render, por ejemplo `https://tu-servicio.onrender.com`, para que Telegram apunte a:

- `/webhook/deluxecs`
- `/webhook/deluxeam`
