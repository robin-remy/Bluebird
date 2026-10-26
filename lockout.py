"""
Lockout continuo para una cuenta de X con navegador REAL (Playwright).
Debe ejecutarse SIEMPRE con xvfb (headless=False), porque el Chromium
headless recibe una pagina vacia de x.com.
"""

import asyncio
import os
import random
import time
from datetime import datetime, timezone

from playwright.async_api import async_playwright
from twikit import Client
import pyotp

# ---------------------------- CONFIG ----------------------------
OBJETIVO = os.environ.get("OBJETIVO", "elizabethotaval")
CONTRASENA_FALSA = os.environ.get("CONTRASENA_FALSA", "noEsLaClave_2026!")
INTENTOS_POR_RAFAGA = int(os.environ.get("INTENTOS_POR_RAFAGA", "10"))
PAUSA_ENTRE_INTENTOS = float(os.environ.get("PAUSA_ENTRE_INTENTOS", "3"))

MAX_JOB_MINUTOS = float(os.environ.get("MAX_JOB_MINUTOS", "340"))
INTERVALO_MINUTOS = float(os.environ.get("INTERVALO_MINUTOS", "50"))
JITTER_SEGUNDOS = 60

X_USER = os.environ.get("X_USER") or None
X_PASS = os.environ.get("X_PASS") or None
X_TOTP = os.environ.get("X_TOTP") or None
HACER_REPORTE = bool(X_USER and X_PASS)

LOGIN_URL = "https://x.com/i/flow/login"
# ----------------------------------------------------------------

REPORT_ENDPOINTS = [
    ("https://x.com/i/api/1.1/users/report_spam.json",
     lambda uid: {"params": {"user_id": uid, "perform_block": "false"}}),
    ("https://api.x.com/1.1/users/report_spam.json",
     lambda uid: {"params": {"user_id": uid, "perform_block": "false"}}),
    ("https://x.com/i/api/1.1/users/report.json",
     lambda uid: {"json": {"user_id": str(uid), "source": "profile", "reason": "spam"}}),
]


def log(msg):
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}", flush=True)


async def guardar_debug(page, etiqueta):
    os.makedirs("debug", exist_ok=True)
    try:
        await page.screenshot(path=f"debug/{etiqueta}.png", full_page=True)
    except Exception:
        pass
    try:
        with open(f"debug/{etiqueta}.html", "w", encoding="utf-8") as f:
            f.write(await page.content())
    except Exception:
        pass
    log(f"    [debug] {etiqueta} | url={page.url}")


async def primer_visible(page, selector):
    loc = page.locator(selector)
    n = await loc.count()
    for i in range(n):
        el = loc.nth(i)
        try:
            if await el.is_visible():
                return el
        except Exception:
            continue
    return None


async def pulsar_texto(page, textos, timeout=8000):
    """Pulsa el primer boton visible cuyo texto coincida (sin importar mayusculas)."""
    for t in textos:
        try:
            loc = page.get_by_text(t, exact=False)
            n = await loc.count()
            for i in range(n):
                el = loc.nth(i)
                try:
                    if await el.is_visible():
                        await el.click(timeout=timeout)
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


async def un_intento(page, usuario, password, totp=None, etiqueta="intento"):
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_selector("input", timeout=30000, state="visible")
    except Exception:
        pass

    # --- Paso 1: usuario ---
    campo = await primer_visible(page, 'input[autocomplete="username"]') \
        or await primer_visible(page, "input")
    if campo is None:
        await guardar_debug(page, etiqueta + "_sin_usuario")
        raise RuntimeError("no encontre campo de usuario")
    await campo.fill(usuario, timeout=8000)
    await page.wait_for_timeout(500)
    if not await pulsar_texto(page, ["Continue", "Continuar", "Next", "Siguiente"]):
        await campo.press("Enter")
    await page.wait_for_timeout(4000)

    # --- Paso 2: password ---
    campo_pw = await primer_visible(page, 'input[type="password"]') \
        or await primer_visible(page, 'input[name="password"]')
    if campo_pw is None:
        await guardar_debug(page, etiqueta + "_sin_password")
        raise RuntimeError("no encontre campo de password")
    await campo_pw.fill(password, timeout=8000)
    await page.wait_for_timeout(500)
    if not await pulsar_texto(page, ["Log in", "Iniciar sesion", "Continuar", "Continue"]):
        await campo_pw.press("Enter")
    await page.wait_for_timeout(4500)

    # --- Paso 3: 2FA opcional ---
    if totp:
        el = await primer_visible(page, 'input[autocomplete="one-time-code"]')
        if el is not None:
            try:
                await el.fill(pyotp.TOTP(totp).now())
                await pulsar_texto(page, ["Next", "Continue", "Continuar", "Log in"])
                await page.wait_for_timeout(3500)
            except Exception:
                pass


async def rafaga(usuario, intentos):
    os.makedirs("debug", exist_ok=True)
    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=False)
        for i in range(1, intentos + 1):
            contexto = await navegador.new_context(locale="en-US")
            pagina = await contexto.new_page()
            try:
                await un_intento(pagina, usuario, CONTRASENA_FALSA, etiqueta=f"err_{i}")
                log(f"  intento {i}/{intentos}: enviado")
                if i == 1:
                    await guardar_debug(pagina, "primero_ok")
            except Exception as e:
                log(f"  intento {i}/{intentos}: error {type(e).__name__}: {e}")
            finally:
                await contexto.close()
            await asyncio.sleep(PAUSA_ENTRE_INTENTOS)
        await navegador.close()


async def cookies_de_login(usuario, password, totp=None):
    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=False)
        contexto = await navegador.new_context(locale="en-US")
        pagina = await contexto.new_page()
        await un_intento(pagina, usuario, password, totp, etiqueta="login_report")
        galletas = await contexto.cookies()
        await navegador.close()
    return {c["name"]: c["value"] for c in galletas}


async def reportar(objetivo):
    log("Autenticando en el navegador para poder reportar...")
    galletas = await cookies_de_login(X_USER, X_PASS, X_TOTP)
    cliente = Client("en-US")
    cliente.set_cookies(galletas)
    u = await cliente.get_user_by_screen_name(objetivo)
    log(f"  id de @{objetivo} = {u.id}")
    for url, build in REPORT_ENDPOINTS:
        try:
            r = await cliente.http.post(url, **build(u.id))
            log(f"  {url} -> HTTP {r.status_code}")
            if r.status_code in (200, 201, 204):
                return
        except Exception as e:
            log(f"  {url} -> {type(e).__name__}")


async def main():
    objetivo = OBJETIVO.strip().lstrip("@")
    log(f"=== INICIO | @{objetivo} | job max {MAX_JOB_MINUTOS:.0f} min ===")

    if HACER_REPORTE:
        try:
            await reportar(objetivo)
        except Exception as e:
            log(f"  reporte fallo: {type(e).__name__}: {e}")

    inicio = time.monotonic()
    ciclo = 0
    while (time.monotonic() - inicio) / 60 < MAX_JOB_MINUTOS:
        ciclo += 1
        log(f"--- Rafaga #{ciclo} ---")
        try:
            await rafaga(objetivo, INTENTOS_POR_RAFAGA)
        except Exception as e:
            log(f"  error en rafaga: {type(e).__name__}: {e}")

        restante = MAX_JOB_MINUTOS - (time.monotonic() - inicio) / 60
        if restante <= 2:
            break
        dormir = (min(INTERVALO_MINUTOS, restante - 1) * 60) + random.uniform(0, JITTER_SEGUNDOS)
        log(f"  durmiendo {dormir/60:.1f} min...")
        await asyncio.sleep(dormir)

    log(f"=== FIN | {ciclo} rafagas ===")


if __name__ == "__main__":
    asyncio.run(main())
