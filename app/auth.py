import hashlib
import os
import secrets

from fastapi import Request, HTTPException
from sqlalchemy.orm import Session

from .models import CuentaAcceso

ROLES = ["administrador", "editor", "observador"]
PUEDEN_EDITAR = {"administrador", "editor"}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, _, _ = stored.partition("$")
    return secrets.compare_digest(hash_password(password, salt), stored)


def crear_cuentas_si_no_existen(db: Session) -> dict:
    """Crea las 3 cuentas de rol con contraseñas aleatorias si aún no existen. Devuelve las que creó."""
    creadas = {}
    for rol in ROLES:
        if db.get(CuentaAcceso, rol):
            continue
        password = secrets.token_urlsafe(9)
        db.add(CuentaAcceso(rol=rol, password_hash=hash_password(password)))
        creadas[rol] = password
    if creadas:
        db.commit()
    return creadas


def autenticar(db: Session, rol: str, password: str) -> bool:
    cuenta = db.get(CuentaAcceso, rol)
    if not cuenta:
        return False
    return verify_password(password, cuenta.password_hash)


def usuario_actual(request: Request) -> str | None:
    return request.session.get("rol")


def requerir_login(request: Request) -> str:
    rol = request.session.get("rol")
    if not rol:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return rol


def requerir_edicion(request: Request) -> str:
    rol = requerir_login(request)
    if rol not in PUEDEN_EDITAR:
        raise HTTPException(status_code=403, detail="Tu rol (observador) solo tiene permiso de lectura.")
    return rol
