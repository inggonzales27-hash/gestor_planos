"""
Importa el LOG de Documentos Contingencia.xlsx a la base de datos del gestor.
Uso:
    python -m app.migrate_excel "C:\\ruta\\LOG de Documentos Contingencia.xlsx"
"""
import sys
from datetime import date, datetime

import pandas as pd

from .database import Base, engine, SessionLocal
from .models import Plano, HistorialEstado, Usuario


def to_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    return None


def to_str(value):
    if pd.isna(value):
        return None
    return str(value).strip()


def migrar_usuarios(xls_path, db):
    df = pd.read_excel(xls_path, sheet_name="DATOS", usecols="A:I")
    df.columns = [
        "usuario", "entidad", "nombres", "apellidos", "dni",
        "cargo", "fecha_ingreso", "fecha_nacimiento", "correo",
    ]
    count = 0
    for _, row in df.iterrows():
        usuario = to_str(row["usuario"])
        if not usuario:
            continue
        if db.get(Usuario, usuario):
            continue
        db.add(Usuario(
            usuario=usuario,
            entidad=to_str(row["entidad"]),
            nombres=to_str(row["nombres"]),
            apellidos=to_str(row["apellidos"]),
            correo=to_str(row["correo"]),
            cargo=to_str(row["cargo"]),
        ))
        count += 1
    db.commit()
    print(f"Usuarios importados: {count}")


def migrar_planos(xls_path, db):
    df = pd.read_excel(xls_path, sheet_name="LOG_Planos")
    df.columns = [
        "codificacion_contrato", "ref", "edificio", "etapa", "tipo_documento",
        "esp", "tipo_archivo", "nivel", "ubicacion", "correlativo",
        "codigo_plano", "detalle", "revision_actual", "fecha_version",
        "formato_plano", "escala_plano", "revision_formal", "estado",
        "estatus_elaboracion", "estatus_envio", "codigo_nuevo",
        "codigo_origen_anterior",
    ]
    count = 0
    for _, row in df.iterrows():
        codigo = to_str(row["codigo_plano"])
        if not codigo:
            continue
        if db.query(Plano).filter_by(codigo=codigo).first():
            continue

        plano = Plano(
            codigo=codigo,
            edificio=to_str(row["edificio"]),
            etapa=to_str(row["etapa"]),
            tipo_documento=to_str(row["tipo_documento"]),
            especialidad=to_str(row["esp"]),
            tipo_archivo=to_str(row["tipo_archivo"]),
            nivel=to_str(row["nivel"]),
            ubicacion=to_str(row["ubicacion"]),
            correlativo=to_str(row["correlativo"]),
            detalle=to_str(row["detalle"]),
            revision_actual=to_str(row["revision_actual"]),
            fecha_version=to_date(row["fecha_version"]),
            formato_plano=to_str(row["formato_plano"]),
            escala_plano=to_str(row["escala_plano"]),
            revision_formal=to_str(row["revision_formal"]),
            estado=to_str(row["estado"]),
            estatus_elaboracion=to_str(row["estatus_elaboracion"]),
            estatus_envio=to_str(row["estatus_envio"]),
            codigo_nuevo=to_str(row["codigo_nuevo"]),
            codigo_origen_anterior=to_str(row["codigo_origen_anterior"]),
        )
        db.add(plano)
        db.flush()

        db.add(HistorialEstado(
            plano_id=plano.id,
            fecha=plano.fecha_version,
            tipo_proceso="ELABORACION",
            estado=plano.estatus_elaboracion or plano.estado,
            comentario="Estado inicial migrado desde LOG_Planos",
        ))
        if plano.estatus_envio:
            db.add(HistorialEstado(
                plano_id=plano.id,
                fecha=plano.fecha_version,
                tipo_proceso="ENVIO",
                estado=plano.estatus_envio,
                comentario="Estado inicial migrado desde LOG_Planos",
            ))
        count += 1

    db.commit()
    print(f"Planos importados: {count}")


def enriquecer_con_estatus_planos(xls_path, db):
    """Agrega links y eventos de historial desde la hoja EstatusPlanos, matcheando por código base."""
    df = pd.read_excel(xls_path, sheet_name="EstatusPlanos", header=1)
    df.columns = [
        "especialidad", "nivel", "num", "version_actual", "cod", "codigo_base",
        "version", "fecha_revision", "descripcion", "link_wip_acc",
        "responsable_elaborar", "estado_elaboracion", "fecha_estado",
        "fecha_entrega_proyectada", "comentario_elaborador", "estado_envio",
        "responsable_revisar", "link_wip_envio", "comentario_revisor",
        "codigo_aconex", "id_flujo_acc", "fecha_envio_cd", "fecha_envio_anin",
        "fecha_vencimiento", "fecha_respuesta", "link_aprobado",
    ]
    matched = 0
    for _, row in df.iterrows():
        codigo_base = to_str(row["codigo_base"])
        if not codigo_base:
            continue
        plano = db.query(Plano).filter_by(codigo=codigo_base).first()
        if not plano:
            continue

        link = to_str(row["link_aprobado"]) or to_str(row["link_wip_envio"]) or to_str(row["link_wip_acc"])
        if link and not plano.link_archivo:
            plano.link_archivo = link

        eventos = [
            ("ELABORACION", row["fecha_estado"], row["estado_elaboracion"], row["responsable_elaborar"], row["comentario_elaborador"], row["link_wip_acc"]),
            ("ENVIO", row["fecha_envio_cd"], "ENVIADO A CD", row["responsable_revisar"], row["comentario_revisor"], row["link_wip_envio"]),
            ("ENVIO", row["fecha_envio_anin"], "ENVIADO A ANIN", row["responsable_revisar"], None, row["link_wip_envio"]),
            ("ENVIO", row["fecha_respuesta"], row["estado_envio"], row["responsable_revisar"], None, row["link_aprobado"]),
        ]
        for tipo_proceso, fecha_raw, estado_raw, responsable_raw, comentario_raw, link_raw in eventos:
            fecha = to_date(fecha_raw)
            estado = to_str(estado_raw)
            if not fecha or not estado:
                continue
            db.add(HistorialEstado(
                plano_id=plano.id,
                fecha=fecha,
                tipo_proceso=tipo_proceso,
                estado=estado,
                responsable=to_str(responsable_raw),
                comentario=to_str(comentario_raw),
                link_archivo=to_str(link_raw),
            ))
        matched += 1

    db.commit()
    print(f"Planos enriquecidos desde EstatusPlanos: {matched}")


def main():
    if len(sys.argv) < 2:
        print("Uso: python -m app.migrate_excel <ruta al xlsx>")
        sys.exit(1)

    xls_path = sys.argv[1]
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        migrar_usuarios(xls_path, db)
        migrar_planos(xls_path, db)
        enriquecer_con_estatus_planos(xls_path, db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
