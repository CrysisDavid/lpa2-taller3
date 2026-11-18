"""Módulo de utilidades para la aplicación."""

import re
from datetime import datetime


def validar_correo(correo):
    """Valida que un correo electrónico tenga un formato válido."""
    if not isinstance(correo, str):
        return False
    patron = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return bool(re.fullmatch(patron, correo.strip()))


def formatear_duracion(segundos):
    """Convierte una duración en segundos a formato mm:ss."""
    if segundos is None:
        return "00:00"
    segundos = int(segundos)
    minutos, segundos_restantes = divmod(max(segundos, 0), 60)
    return f"{minutos:02d}:{segundos_restantes:02d}"


def generar_slug(texto):
    """Genera un slug a partir de un texto."""
    if texto is None:
        return ""
    slug = texto.lower().strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def obtener_año_actual():
    """Obtiene el año actual."""
    return datetime.now().year


def validar_año(año):
    """Valida que un año sea válido (no futuro y no muy antiguo)."""
    año_actual = obtener_año_actual()
    return 1900 <= año <= año_actual

