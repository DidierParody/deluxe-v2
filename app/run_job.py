import asyncio
import sys

from app.db.pool import close_pool, init_pool
from app.scheduler.jobs import finalizar_eventos_expirados, liberar_mesas_expiradas


JOBS = {
    "finalizar_eventos_expirados": finalizar_eventos_expirados,
    "liberar_mesas_expiradas": liberar_mesas_expiradas,
}


async def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        available = ", ".join(sorted(JOBS))
        print(f"Uso: python -m app.run_job <job>. Disponibles: {available}")
        return 1

    await init_pool()
    try:
        await JOBS[sys.argv[1]]()
        return 0
    finally:
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
