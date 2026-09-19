import os
import secrets
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .database import Base, engine, get_db, SessionLocal
from .models import Plano, HistorialEstado, Usuario
from .auth import autenticar, requerir_login, requerir_edicion, crear_cuentas_si_no_existen, usuario_actual

BASE_DIR = Path(__file__).resolve().parent
COOKIE_SECRET_PATH = BASE_DIR.parent / ".cookie_secret"

app = FastAPI(title="Gestor de Planos")
(BASE_DIR / "static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

cookie_secret = os.environ.get("SESSION_SECRET")
if not cookie_secret:
    if not COOKIE_SECRET_PATH.exists():
        COOKIE_SECRET_PATH.write_text(secrets.token_hex(32))
    cookie_secret = COOKIE_SECRET_PATH.read_text().strip()
app.add_middleware(SessionMiddleware, secret_key=cookie_secret)

Base.metadata.create_all(bind=engine)

_db_inicial = SessionLocal()
try:
    _cuentas_nuevas = crear_cuentas_si_no_existen(_db_inicial)
    if _cuentas_nuevas:
        print("=== Cuentas de acceso creadas (guarda estas contraseñas) ===")
        for rol, password in _cuentas_nuevas.items():
            print(f"  {rol}: {password}")
        print("=============================================================")
finally:
    _db_inicial.close()


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login_submit(request: Request, rol: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if autenticar(db, rol, password):
        request.session["rol"] = rol
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login?error=1", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    especialidad: str = "",
    nivel: str = "",
    estado: str = "",
    db: Session = Depends(get_db),
    rol: str = Depends(requerir_login),
):
    query = db.query(Plano)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Plano.codigo.ilike(like), Plano.detalle.ilike(like)))
    if especialidad:
        query = query.filter(Plano.especialidad == especialidad)
    if nivel:
        query = query.filter(Plano.nivel == nivel)
    if estado:
        query = query.filter(Plano.estatus_elaboracion == estado)

    resultados = query.order_by(Plano.codigo).limit(200).all()

    especialidades = [r[0] for r in db.query(Plano.especialidad).distinct().order_by(Plano.especialidad) if r[0]]
    niveles = [r[0] for r in db.query(Plano.nivel).distinct().order_by(Plano.nivel) if r[0]]
    estados = [r[0] for r in db.query(Plano.estatus_elaboracion).distinct().order_by(Plano.estatus_elaboracion) if r[0]]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "resultados": resultados,
            "total_planos": db.query(Plano).count(),
            "q": q,
            "especialidad": especialidad,
            "nivel": nivel,
            "estado": estado,
            "especialidades": especialidades,
            "niveles": niveles,
            "estados": estados,
            "rol": rol,
        },
    )


@app.get("/plano/{plano_id}", response_class=HTMLResponse)
def detalle_plano(request: Request, plano_id: int, db: Session = Depends(get_db), rol: str = Depends(requerir_login)):
    plano = db.get(Plano, plano_id)
    historial = (
        db.query(HistorialEstado)
        .filter_by(plano_id=plano_id)
        .order_by(HistorialEstado.fecha)
        .all()
    )
    usuarios = db.query(Usuario).order_by(Usuario.usuario).all()
    estados_elaboracion = [r[0] for r in db.query(Plano.estatus_elaboracion).distinct() if r[0]]
    estados_envio = [r[0] for r in db.query(Plano.estatus_envio).distinct() if r[0]]
    return templates.TemplateResponse(
        request,
        "plano_detail.html",
        {
            "plano": plano,
            "historial": historial,
            "usuarios": usuarios,
            "estados_elaboracion": estados_elaboracion,
            "estados_envio": estados_envio,
            "rol": rol,
        },
    )


@app.post("/plano/{plano_id}/historial")
def registrar_estado(
    plano_id: int,
    tipo_proceso: str = Form(...),
    estado: str = Form(...),
    responsable: str = Form(""),
    comentario: str = Form(""),
    link_archivo: str = Form(""),
    fecha: str = Form(""),
    db: Session = Depends(get_db),
    rol: str = Depends(requerir_edicion),
):
    plano = db.get(Plano, plano_id)
    if plano:
        fecha_evento = date.fromisoformat(fecha) if fecha else date.today()
        db.add(HistorialEstado(
            plano_id=plano.id,
            fecha=fecha_evento,
            tipo_proceso=tipo_proceso,
            estado=estado,
            responsable=responsable or None,
            comentario=comentario or None,
            link_archivo=link_archivo or None,
        ))
        if tipo_proceso == "ELABORACION":
            plano.estatus_elaboracion = estado
        else:
            plano.estatus_envio = estado
        if link_archivo:
            plano.link_archivo = link_archivo
        db.commit()
    return RedirectResponse(url=f"/plano/{plano_id}", status_code=303)
