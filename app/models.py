from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class CuentaAcceso(Base):
    __tablename__ = "cuentas_acceso"

    rol = Column(String, primary_key=True)  # administrador, editor, observador
    password_hash = Column(String, nullable=False)


class Usuario(Base):
    __tablename__ = "usuarios"

    usuario = Column(String, primary_key=True)
    entidad = Column(String)
    nombres = Column(String)
    apellidos = Column(String)
    correo = Column(String)
    cargo = Column(String)
    especialidad = Column(String)
    rol = Column(String, default="lector")  # admin, coordinador, revisor, lector


class Plano(Base):
    __tablename__ = "planos"

    id = Column(Integer, primary_key=True)
    codigo = Column(String, unique=True, index=True, nullable=False)
    edificio = Column(String)
    etapa = Column(String)
    tipo_documento = Column(String)
    especialidad = Column(String, index=True)
    tipo_archivo = Column(String)
    nivel = Column(String, index=True)
    ubicacion = Column(String)
    correlativo = Column(String)
    detalle = Column(Text)
    revision_actual = Column(String)
    fecha_version = Column(Date)
    formato_plano = Column(String)
    escala_plano = Column(String)
    revision_formal = Column(String)
    estado = Column(String, index=True)
    estatus_elaboracion = Column(String, index=True)
    estatus_envio = Column(String, index=True)
    codigo_nuevo = Column(String)
    codigo_origen_anterior = Column(String)
    link_archivo = Column(String)

    historial = relationship(
        "HistorialEstado", back_populates="plano", order_by="HistorialEstado.fecha"
    )


class HistorialEstado(Base):
    __tablename__ = "historial_estados"

    id = Column(Integer, primary_key=True)
    plano_id = Column(Integer, ForeignKey("planos.id"), nullable=False)
    fecha = Column(Date)
    tipo_proceso = Column(String)  # ELABORACION, ENVIO, GENERAL
    estado = Column(String)
    responsable = Column(String)
    comentario = Column(Text)
    link_archivo = Column(String)
    creado_en = Column(DateTime, default=datetime.utcnow)

    plano = relationship("Plano", back_populates="historial")
