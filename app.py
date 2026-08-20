#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestion de Compraventa de Vehiculos
-----------------------------------
Aplicacion web LOCAL de un solo usuario. Solo usa la libreria estandar de
Python (sin dependencias externas) y guarda los datos en un archivo SQLite
llamado 'vehiculos.db' junto a este script.

Para arrancar:  python app.py
Luego abre en el navegador:  http://localhost:8000
"""

import http.server
import socketserver
import socket
import sqlite3
import json
import os
import webbrowser
import threading
import re
import io
import csv
import base64
import zipfile
import hashlib
import secrets
import mimetypes
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# En la nube se define DATA_DIR (disco persistente) y PORT como variables de
# entorno. En local, por defecto, todo se guarda junto al programa.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
DB_PATH = os.path.join(DATA_DIR, "vehiculos.db")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
DOCS_DIR = os.path.join(DATA_DIR, "documentos_adjuntos")
PORT = int(os.environ.get("PORT", "8000"))

# Tipos de documento del modulo de gestion documental (orden fijo)
DOC_TIPOS = [
    "Factura proforma", "Factura de compra", "Pago al proveedor",
    "Hoja de transporte", "Albarán de entrega", "Ficha técnica",
    "Permiso de circulación", "Facturas de reparación/mantenimiento",
    "Garantía comercial", "Factura de venta", "Justificante de cobro",
]

# --------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            nif       TEXT,
            telefono  TEXT,
            email     TEXT,
            direccion TEXT,
            notas     TEXT,
            creado    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS vehiculos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            matricula   TEXT,
            bastidor    TEXT,
            marca       TEXT,
            modelo      TEXT,
            anio        INTEGER,
            km          INTEGER,
            color       TEXT,
            combustible TEXT,
            estado      TEXT DEFAULT 'pendiente',
            ubicacion   TEXT,
            itv_pasada  TEXT,
            itv_expira  TEXT,
            ref_web     TEXT,
            foto        TEXT,
            notas       TEXT,
            creado      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS transportistas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            nif       TEXT,
            telefono  TEXT,
            email     TEXT,
            direccion TEXT,
            notas     TEXT,
            creado    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS listas (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo  TEXT NOT NULL,
            valor TEXT NOT NULL,
            padre TEXT DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_listas ON listas(tipo, valor, padre);

        CREATE TABLE IF NOT EXISTS contadores (
            clave TEXT PRIMARY KEY,
            valor INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS cobros (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id     INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
            fecha        TEXT,
            medio        TEXT,
            importe      REAL DEFAULT 0,
            veh_cambio_id INTEGER REFERENCES vehiculos(id) ON DELETE SET NULL,
            notas        TEXT,
            creado       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS compras (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id    INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            proveedor_id   INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            numero_factura TEXT,
            regimen        TEXT,
            fecha          TEXT,
            precio         REAL DEFAULT 0,
            gastos         REAL DEFAULT 0,
            forma_pago     TEXT,
            notas          TEXT,
            creado         TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS ventas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id    INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            cliente_id     INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            numero_factura TEXT,
            regimen        TEXT,
            fecha          TEXT,
            precio         REAL DEFAULT 0,
            cruz_fin       REAL DEFAULT 0,
            cruz_seg       REAL DEFAULT 0,
            cruz_gar       REAL DEFAULT 0,
            forma_pago     TEXT,
            notas          TEXT,
            creado         TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS taller (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            tipo        TEXT,
            descripcion TEXT,
            proveedor   TEXT,
            fecha       TEXT,
            coste       REAL DEFAULT 0,
            pago        TEXT DEFAULT 'Pendiente',
            notas       TEXT,
            creado      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            nombre      TEXT,
            canal       TEXT,
            telefono    TEXT,
            fecha       TEXT,
            estado      TEXT DEFAULT 'Nuevo',
            notas       TEXT,
            creado      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS gestoria (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id      INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            tipo             TEXT,
            estado           TEXT DEFAULT 'Pendiente',
            gestoria         TEXT,
            fecha_solicitud  TEXT,
            fecha_resolucion TEXT,
            notas            TEXT,
            creado           TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS documentos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id     INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            tipo            TEXT,
            archivo         TEXT,
            nombre_original TEXT,
            mime            TEXT,
            importe         REAL,
            fecha           TEXT,
            notas           TEXT,
            creado          TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT NOT NULL UNIQUE,
            nombre    TEXT,
            salt      TEXT,
            hash      TEXT,
            rol       TEXT DEFAULT 'usuario',
            permisos  TEXT DEFAULT '[]',
            activo    INTEGER DEFAULT 1,
            creado    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS sesiones (
            token      TEXT PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            creado     TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS comerciales (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre              TEXT NOT NULL,
            nif                 TEXT,
            telefono            TEXT,
            email               TEXT,
            fecha_incorporacion TEXT,
            comision_pct        REAL DEFAULT 0,
            franquicia          INTEGER DEFAULT 0,
            activo              INTEGER DEFAULT 1,
            notas               TEXT,
            creado              TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS proveedores (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            nif       TEXT,
            telefono  TEXT,
            email     TEXT,
            direccion TEXT,
            notas     TEXT,
            creado    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS garantias (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id  INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            cliente_id   INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            tipo         TEXT,
            fecha_inicio TEXT,
            meses        INTEGER,
            fecha_fin    TEXT,
            alcance      TEXT,
            estado       TEXT DEFAULT 'Vigente',
            notas        TEXT,
            creado       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS postventa (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            tipo        TEXT,
            descripcion TEXT,
            proveedor   TEXT,
            fecha       TEXT,
            coste       REAL DEFAULT 0,
            asume       TEXT,
            pago        TEXT DEFAULT 'Pendiente',
            notas       TEXT,
            creado      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS agenda (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            fecha       TEXT,
            tipo        TEXT,
            asunto      TEXT,
            detalle     TEXT,
            notas       TEXT,
            creado      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS seguimientos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ambito        TEXT,
            ref_id        INTEGER,
            fecha         TEXT,
            contacto      TEXT,
            detalle       TEXT,
            proxima_fecha TEXT,
            comercial_id  INTEGER,
            creado        TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS extractos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT,
            cuenta          TEXT,
            nombre_archivo  TEXT,
            notas           TEXT,
            creado          TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS movimientos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            extracto_id         INTEGER REFERENCES extractos(id) ON DELETE CASCADE,
            fecha               TEXT,
            concepto            TEXT,
            importe             REAL,
            saldo               REAL,
            categoria           TEXT,
            ref_tipo            TEXT,
            ref_id              INTEGER,
            conciliado          INTEGER DEFAULT 0,
            observacion_app     TEXT,
            observacion_usuario TEXT,
            creado              TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS recepciones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id  INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            fecha        TEXT,
            responsable  TEXT,
            almacen_id   INTEGER,
            ubicacion    TEXT,
            tiene_desperfectos INTEGER DEFAULT 0,
            desperfectos TEXT,
            marcas       TEXT,
            notas        TEXT,
            creado       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS almacenes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            direccion TEXT,
            notas     TEXT,
            creado    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS traspasos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id     INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            almacen_origen  INTEGER,
            almacen_destino INTEGER,
            fecha           TEXT,
            notas           TEXT,
            creado          TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS logistica (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo_id     INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
            transportista_id INTEGER REFERENCES transportistas(id) ON DELETE SET NULL,
            transportista   TEXT,
            origen          TEXT,
            destino         TEXT,
            destinatario    TEXT,
            ubicacion       TEXT,
            coste           REAL DEFAULT 0,
            fecha_recogida  TEXT,
            fecha_entrega   TEXT,
            estado          TEXT DEFAULT 'Pendiente',
            notas           TEXT,
            creado          TEXT DEFAULT (datetime('now','localtime'))
        );
        """
    )
    conn.commit()
    # Migracion no destructiva: anadir columnas nuevas a BD ya existentes
    migrate(conn)
    seed_listas(conn)
    seed_modelos(conn)
    seed_admin(conn)
    conn.close()


# --------------------------------------------------------------------------
# Usuarios / autenticacion
# --------------------------------------------------------------------------

SESSIONS = {}  # token -> {id, username, nombre, rol, permisos}
AREAS = ["panel", "stock", "compras", "taller", "logistica", "marketing",
         "agenda", "ventas", "gestoria", "garantias", "postventa", "documentos",
         "almacenes", "tesoreria", "bancos", "web", "clientes", "proveedores",
         "comerciales", "transportistas", "informes"]

# Que area controla la ESCRITURA de cada tabla (las no listadas no se restringen)
TABLE_AREA = {
    "vehiculos": "stock", "compras": "compras", "ventas": "ventas",
    "cobros": "ventas", "logistica": "logistica", "traspasos": "logistica",
    "taller": "taller", "leads": "marketing", "gestoria": "gestoria",
    "garantias": "garantias", "postventa": "postventa", "almacenes": "almacenes",
    "clientes": "clientes", "proveedores": "proveedores",
    "comerciales": "comerciales", "transportistas": "transportistas",
    "extractos": "bancos", "movimientos": "bancos",
    "recepciones": "logistica", "gestorias": "gestoria",
}


def puede_escribir(user, table):
    """El admin puede todo. Para el resto, según el nivel del área de la tabla."""
    if not user:
        return False
    if user.get("rol") == "admin":
        return True
    area = TABLE_AREA.get(table)
    if not area:            # tablas auxiliares (listas, documentos, agenda, seguimientos): sin restricción
        return True
    p = user.get("permisos")
    if isinstance(p, dict):
        return p.get(area) == "w"
    if isinstance(p, list):  # formato antiguo: tener acceso = poder escribir
        return area in p
    return False


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"),
                            bytes.fromhex(salt), 100000).hex()
    return salt, h


def seed_admin(conn):
    n = conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"]
    if n == 0:
        salt, h = hash_password("admin1234")
        conn.execute(
            "INSERT INTO usuarios (username, nombre, salt, hash, rol, permisos, activo)"
            " VALUES ('admin','Administrador',?,?,'admin','[]',1)", (salt, h))
        conn.commit()


def _sesion_dict(row):
    keys = row.keys()
    return {
        "id": row["id"], "username": row["username"], "nombre": row["nombre"],
        "rol": row["rol"], "permisos": json.loads(row["permisos"] or "[]"),
        "comercial_id": (row["comercial_id"] if "comercial_id" in keys else None)}


def crear_sesion(row):
    tok = secrets.token_hex(32)
    SESSIONS[tok] = _sesion_dict(row)
    # Persistir en BD para que la sesión sobreviva a reinicios del servidor (p.ej. cada redespliegue en la nube)
    try:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO sesiones (token, usuario_id) VALUES (?,?)", (tok, row["id"]))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return tok


def cargar_sesion_db(tok):
    """Recupera de la BD una sesión no presente en memoria (tras un reinicio) y la recachea."""
    if not tok:
        return None
    try:
        conn = get_db()
        row = conn.execute(
            """SELECT u.* FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id
               WHERE s.token = ? AND u.activo = 1""", (tok,)).fetchone()
        conn.close()
    except Exception:
        return None
    if not row:
        return None
    d = _sesion_dict(row)
    SESSIONS[tok] = d
    return d


def borrar_sesion_db(tok):
    if not tok:
        return
    try:
        conn = get_db()
        conn.execute("DELETE FROM sesiones WHERE token=?", (tok,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def autenticar(username, password):
    conn = get_db()
    row = conn.execute("SELECT * FROM usuarios WHERE username=? AND activo=1",
                       (username,)).fetchone()
    conn.close()
    if not row:
        return None
    _, h = hash_password(password, row["salt"])
    if not secrets.compare_digest(h, row["hash"] or ""):
        return None
    return row


def list_usuarios():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, nombre, rol, permisos, activo, comercial_id, creado FROM usuarios ORDER BY username"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["permisos"] = json.loads(d["permisos"] or "[]")
        out.append(d)
    return out


def crear_usuario(data):
    if not data.get("username"):
        raise ReglaNegocio("El usuario es obligatorio.")
    salt, h = hash_password(data.get("password") or "cambiar1234")
    perms = json.dumps(data.get("permisos") or [])
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO usuarios (username, nombre, salt, hash, rol, permisos, activo, comercial_id)"
            " VALUES (?,?,?,?,?,?,1,?)",
            (data.get("username").strip(), data.get("nombre"), salt, h,
             data.get("rol") or "usuario", perms, data.get("comercial_id") or None))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ReglaNegocio("Ese nombre de usuario ya existe.")
    finally:
        conn.close()


def actualizar_usuario(uid, data):
    sets, vals = [], []
    for k in ("nombre", "rol"):
        if k in data:
            sets.append(f"{k}=?")
            vals.append(data[k])
    if "comercial_id" in data:
        sets.append("comercial_id=?")
        vals.append(data.get("comercial_id") or None)
    if "permisos" in data:
        sets.append("permisos=?")
        vals.append(json.dumps(data["permisos"] or []))
    if "activo" in data:
        sets.append("activo=?")
        vals.append(1 if data["activo"] else 0)
    if data.get("password"):
        salt, h = hash_password(data["password"])
        sets += ["salt=?", "hash=?"]
        vals += [salt, h]
    if sets:
        conn = get_db()
        conn.execute(f"UPDATE usuarios SET {','.join(sets)} WHERE id=?", vals + [uid])
        conn.commit()
        conn.close()


def migrate(conn):
    """Anade columnas/tablas nuevas si la base de datos es de una version previa."""
    def cols(table):
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def add(table, coldef):
        name = coldef.split()[0]
        if name not in cols(table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")

    def has_table(t):
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone() is not None

    try:
        add("vehiculos", "foto TEXT")
        add("vehiculos", "ubicacion TEXT")
        add("vehiculos", "itv_pasada TEXT")
        add("vehiculos", "itv_expira TEXT")
        add("vehiculos", "ref_web TEXT")
        add("vehiculos", "almacen_id INTEGER")
        add("vehiculos", "recepcionado INTEGER DEFAULT 0")
        add("vehiculos", "reserva_cliente_id INTEGER")
        add("vehiculos", "reserva_fecha TEXT")
        # Invariante: un coche disponible o vendido siempre esta recepcionado
        conn.execute("UPDATE vehiculos SET recepcionado=1 WHERE estado IN ('disponible','vendido')")
        if has_table("logistica"):
            add("logistica", "almacen_id INTEGER")
        add("compras", "prov_id INTEGER")
        add("compras", "pagado TEXT")
        add("compras", "fecha_pago_est TEXT")
        add("ventas", "fecha_cobro_est TEXT")
        add("ventas", "entregado TEXT")
        add("ventas", "fecha_entrega_cli TEXT")
        add("ventas", "comercial_id INTEGER")
        if has_table("leads"):
            add("leads", "comercial_id INTEGER")
            add("leads", "cerrado INTEGER DEFAULT 0")
            add("leads", "motivo_cierre TEXT")
        if has_table("agenda"):
            add("agenda", "cerrado INTEGER DEFAULT 0")
            add("agenda", "motivo_cierre TEXT")
        if has_table("documentos"):
            add("documentos", "agenda_id INTEGER")
        add("compras", "iva_pct REAL")
        if has_table("taller"):
            add("taller", "fecha_pago_est TEXT")
            add("taller", "numero_factura TEXT")
            add("taller", "nif_proveedor TEXT")
            add("taller", "iva_pct REAL")
        if has_table("postventa"):
            add("postventa", "fecha_pago_est TEXT")
            add("postventa", "numero_factura TEXT")
            add("postventa", "nif_proveedor TEXT")
            add("postventa", "iva_pct REAL")
        add("compras", "numero_factura TEXT")
        add("compras", "regimen TEXT")
        add("ventas", "numero_factura TEXT")
        add("ventas", "regimen TEXT")
        if has_table("logistica"):
            add("logistica", "transportista_id INTEGER")
            add("logistica", "destino TEXT")
            add("logistica", "ubicacion TEXT")
            add("logistica", "coste REAL DEFAULT 0")
        add("ventas", "cruz_fin REAL DEFAULT 0")
        add("ventas", "cruz_seg REAL DEFAULT 0")
        add("ventas", "cruz_gar REAL DEFAULT 0")
        if has_table("taller"):
            add("taller", "prov_id INTEGER")
        if has_table("logistica"):
            add("logistica", "numero_factura TEXT")      # facturación del transporte (#17)
            add("logistica", "factura_recibida TEXT")
            add("logistica", "fecha_factura TEXT")
            add("logistica", "pagado TEXT")
            add("logistica", "fecha_pago_est TEXT")
            add("logistica", "destinatario_id INTEGER")
            # Backfill: coches ya recepcionados cuyo transporte quedó 'En tránsito' → 'Entregado'
            conn.execute(
                """UPDATE logistica SET estado='Entregado',
                       fecha_entrega=COALESCE(NULLIF(fecha_entrega,''), date('now','localtime'))
                   WHERE estado='En tránsito'
                     AND vehiculo_id IN (SELECT id FROM vehiculos WHERE recepcionado=1)""")
        # Control de facturas de proveedor: factura recibida sí/no + fecha
        if has_table("taller"):
            add("taller", "factura_recibida TEXT")
            add("taller", "fecha_factura TEXT")
        if has_table("postventa"):
            add("postventa", "factura_recibida TEXT")
            add("postventa", "fecha_factura TEXT")
        add("compras", "factura_recibida TEXT")
        add("compras", "fecha_factura TEXT")
        if has_table("gestoria"):
            add("gestoria", "coste REAL")
            add("gestoria", "numero_factura TEXT")
            add("gestoria", "factura_recibida TEXT")
            add("gestoria", "fecha_factura TEXT")
            add("gestoria", "pagado TEXT")
            add("gestoria", "fecha_pago_est TEXT")
            add("gestoria", "nif_gestoria TEXT")
        add("vehiculos", "proxima_revision TEXT")   # ITV: próxima revisión concertada (#11)
        add("vehiculos", "etiqueta TEXT")            # etiqueta medioambiental DGT
        if has_table("gestoria"):
            add("gestoria", "gestoria_id INTEGER")   # enlaza con la gestoría del directorio
        if has_table("leads"):
            add("leads", "proxima_fecha TEXT")       # próxima gestión (#5)
            add("leads", "email TEXT")               # contacto (#19)
            add("leads", "nif TEXT")                 # datos completos del contacto (aún no cliente)
            add("leads", "direccion TEXT")
            add("leads", "poblacion TEXT")
        add("clientes", "datos_cobro TEXT")          # datos de cobro obligatorios en clientes (#19)
        add("clientes", "es_flexicar INTEGER DEFAULT 0")  # cliente del módulo Flexicar
        if has_table("usuarios"):
            add("usuarios", "comercial_id INTEGER")   # vincular usuario con comercial (#21)
        # Proforma obligatoria + campos Flexicar
        add("vehiculos", "fecha_liberacion TEXT")
        add("compras", "fecha_pago TEXT")            # fecha real de pago al proveedor
        add("ventas", "estado_factura TEXT")          # 'proforma' | 'factura'
        add("ventas", "numero_proforma TEXT")
        add("ventas", "fecha_proforma TEXT")
        add("ventas", "fecha_entrega_doc TEXT")       # entrega de documentación al cliente
        # Ventas existentes = ya son facturas confirmadas
        conn.execute("UPDATE ventas SET estado_factura='factura' WHERE estado_factura IS NULL OR estado_factura=''")
        # Versión del modelo (relleno manual) y verificación de luz testigo de motor en recepción
        add("vehiculos", "version TEXT")
        add("vehiculos", "luz_motor TEXT")           # '' no verificada | 'apagada' | 'encendida'
        if has_table("recepciones"):
            add("recepciones", "luz_motor TEXT")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gestorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL, nif TEXT, telefono TEXT, email TEXT,
                direccion TEXT, notas TEXT,
                creado TEXT DEFAULT (datetime('now','localtime'))
            );
            """)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS taller (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehiculo_id INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
                tipo TEXT, descripcion TEXT, proveedor TEXT, fecha TEXT,
                coste REAL DEFAULT 0, pago TEXT DEFAULT 'Pendiente', notas TEXT,
                creado TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehiculo_id INTEGER REFERENCES vehiculos(id) ON DELETE CASCADE,
                nombre TEXT, canal TEXT, telefono TEXT, fecha TEXT,
                estado TEXT DEFAULT 'Nuevo', notas TEXT,
                creado TEXT DEFAULT (datetime('now','localtime'))
            );
            """
        )
        conn.commit()
    except Exception as e:
        print("Aviso migracion:", e)


MARCAS_SEED = [
    "Abarth", "Alfa Romeo", "Audi", "BMW", "Citroën", "Cupra", "Dacia",
    "DS", "Fiat", "Ford", "Honda", "Hyundai", "Jaguar", "Jeep", "Kia",
    "Land Rover", "Lexus", "Mazda", "Mercedes-Benz", "MG", "Mini",
    "Mitsubishi", "Nissan", "Opel", "Peugeot", "Porsche", "Renault",
    "Seat", "Skoda", "Smart", "SsangYong", "Subaru", "Suzuki", "Tesla",
    "Toyota", "Volkswagen", "Volvo",
]


def seed_listas(conn):
    """Si no hay marcas en 'listas', siembra un catalogo inicial de marcas."""
    n = conn.execute("SELECT COUNT(*) AS n FROM listas WHERE tipo='marca'").fetchone()["n"]
    if n == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO listas (tipo, valor, padre) VALUES ('marca', ?, '')",
            [(m,) for m in MARCAS_SEED],
        )
        conn.commit()


# Catalogo de modelos por marca (mercado español). Al elegir la marca se
# despliegan estos modelos, para que todos usen la misma denominacion.
MODELOS_SEED = {
    "Abarth": ["500", "595", "695", "124 Spider"],
    "Alfa Romeo": ["MiTo", "Giulietta", "Giulia", "Stelvio", "Tonale", "147", "156", "159", "Brera"],
    "Audi": ["A1", "A3", "A4", "A5", "A6", "A7", "A8", "Q2", "Q3", "Q4 e-tron", "Q5", "Q7", "Q8", "TT", "e-tron", "S3", "RS3", "S4", "RS6"],
    "BMW": ["Serie 1", "Serie 2", "Serie 2 Active Tourer", "Serie 3", "Serie 4", "Serie 5", "Serie 6", "Serie 7", "Serie 8", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "Z4", "i3", "i4", "iX", "iX3", "M3", "M4"],
    "Citroën": ["C1", "C3", "C3 Aircross", "C4", "C4 X", "C4 Cactus", "C5", "C5 Aircross", "C5 X", "Berlingo", "C-Elysée", "C4 Picasso", "Grand C4 Picasso", "C4 SpaceTourer", "Ami"],
    "Cupra": ["Formentor", "León", "Ateca", "Born", "Tavascan"],
    "Dacia": ["Sandero", "Sandero Stepway", "Duster", "Logan", "Lodgy", "Dokker", "Jogger", "Spring"],
    "DS": ["DS 3", "DS 3 Crossback", "DS 4", "DS 5", "DS 7 Crossback", "DS 9"],
    "Fiat": ["500", "500e", "500L", "500X", "Panda", "Punto", "Tipo", "Doblò", "Ducato", "Qubo"],
    "Ford": ["Fiesta", "Focus", "Puma", "Kuga", "Mondeo", "EcoSport", "Ka+", "C-Max", "S-Max", "Galaxy", "Mustang", "Mustang Mach-E", "Transit", "Transit Custom", "Ranger", "Tourneo Connect", "Tourneo Courier"],
    "Honda": ["Jazz", "Civic", "HR-V", "CR-V", "ZR-V", "Accord", "e"],
    "Hyundai": ["i10", "i20", "i30", "i40", "Bayon", "Kona", "Tucson", "Santa Fe", "Ioniq", "Ioniq 5", "Ioniq 6", "ix20", "ix35"],
    "Jaguar": ["XE", "XF", "XJ", "E-Pace", "F-Pace", "I-Pace", "F-Type"],
    "Jeep": ["Renegade", "Compass", "Avenger", "Cherokee", "Grand Cherokee", "Wrangler"],
    "Kia": ["Picanto", "Rio", "Ceed", "XCeed", "Stonic", "Niro", "Sportage", "Sorento", "EV6", "Soul", "Venga", "Stinger"],
    "Land Rover": ["Defender", "Discovery", "Discovery Sport", "Range Rover", "Range Rover Sport", "Range Rover Evoque", "Range Rover Velar", "Freelander"],
    "Lexus": ["CT", "IS", "ES", "LS", "UX", "NX", "RX", "RC", "RZ"],
    "Mazda": ["Mazda2", "Mazda3", "Mazda6", "CX-3", "CX-30", "CX-5", "CX-60", "MX-5", "MX-30"],
    "Mercedes-Benz": ["Clase A", "Clase B", "Clase C", "Clase E", "Clase S", "CLA", "CLS", "GLA", "GLB", "GLC", "GLE", "GLS", "Clase G", "Clase V", "Vito", "Sprinter", "Citan", "EQA", "EQB", "EQC", "SLK", "SL"],
    "MG": ["MG3", "ZS", "HS", "MG4", "MG5", "Marvel R", "EHS"],
    "Mini": ["Cooper", "One", "Countryman", "Clubman", "Cabrio", "Paceman"],
    "Mitsubishi": ["Space Star", "ASX", "Eclipse Cross", "Outlander", "L200", "Montero"],
    "Nissan": ["Micra", "Note", "Juke", "Qashqai", "X-Trail", "Leaf", "Ariya", "Pulsar", "Navara", "Townstar", "Primastar", "Townstar Combi"],
    "Opel": ["Corsa", "Astra", "Insignia", "Crossland", "Grandland", "Mokka", "Zafira", "Combo", "Vivaro", "Adam", "Karl", "Meriva", "Antara"],
    "Peugeot": ["108", "208", "308", "408", "508", "2008", "3008", "5008", "Partner", "Rifter", "Traveller", "Expert", "Boxer", "207", "407"],
    "Porsche": ["911", "718 Cayman", "718 Boxster", "Panamera", "Macan", "Cayenne", "Taycan"],
    "Renault": ["Twingo", "Clio", "Captur", "Mégane", "Mégane E-Tech", "Scénic", "Kadjar", "Arkana", "Austral", "Kangoo", "Trafic", "Master", "Zoe", "Talisman", "Espace", "Koleos", "Laguna"],
    "Seat": ["Ibiza", "León", "Arona", "Ateca", "Tarraco", "Alhambra", "Toledo", "Mii", "Exeo", "Altea"],
    "Skoda": ["Fabia", "Scala", "Octavia", "Superb", "Kamiq", "Karoq", "Kodiaq", "Enyaq", "Rapid", "Citigo", "Yeti", "Roomster"],
    "Smart": ["ForTwo", "ForFour", "#1", "#3"],
    "SsangYong": ["Tivoli", "Korando", "Rexton", "Musso", "XLV"],
    "Subaru": ["Impreza", "XV", "Forester", "Outback", "Legacy", "BRZ"],
    "Suzuki": ["Ignis", "Swift", "Baleno", "Vitara", "S-Cross", "Jimny", "Across", "Swace", "SX4"],
    "Tesla": ["Model 3", "Model S", "Model X", "Model Y"],
    "Toyota": ["Aygo", "Aygo X", "Yaris", "Yaris Cross", "Corolla", "C-HR", "RAV4", "Camry", "Prius", "Land Cruiser", "Hilux", "Proace", "Proace City", "Auris", "Avensis", "Supra", "bZ4X"],
    "Volkswagen": ["up!", "Polo", "Golf", "T-Cross", "T-Roc", "Tiguan", "Tiguan Allspace", "Passat", "Arteon", "Touran", "Sharan", "Touareg", "ID.3", "ID.4", "ID.5", "Caddy", "Transporter", "California", "Scirocco", "Beetle"],
    "Volvo": ["V40", "V60", "V90", "S60", "S90", "XC40", "XC60", "XC90", "C40", "EX30"],
}


def seed_modelos(conn):
    """Siembra (una vez) el catalogo de modelos por marca. Idempotente:
    INSERT OR IGNORE respeta los que el usuario haya añadido."""
    row = conn.execute("SELECT valor FROM contadores WHERE clave='modelos_seed_v1'").fetchone()
    if row and row["valor"]:
        return
    data = [("modelo", mod, marca) for marca, mods in MODELOS_SEED.items() for mod in mods]
    conn.executemany("INSERT OR IGNORE INTO listas (tipo, valor, padre) VALUES (?,?,?)", data)
    conn.execute("INSERT OR REPLACE INTO contadores (clave, valor) VALUES ('modelos_seed_v1', 1)")
    conn.commit()


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def rows_to_list(rows):
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Validacion de NIF / DNI / NIE / CIF (espanoles)
# --------------------------------------------------------------------------

def validar_nif(valor):
    """Devuelve True/False/None. None si esta vacio (no se valida)."""
    if not valor:
        return None
    s = "".join(valor.split()).upper().replace("-", "").replace(".", "")
    if not s:
        return None
    letras = "TRWAGMYFPDXBNJZSQVHLCKE"
    # DNI: 8 digitos + letra
    if len(s) == 9 and s[:8].isdigit() and s[8].isalpha():
        return s[8] == letras[int(s[:8]) % 23]
    # NIE: X/Y/Z + 7 digitos + letra
    if len(s) == 9 and s[0] in "XYZ" and s[1:8].isdigit() and s[8].isalpha():
        num = str("XYZ".index(s[0])) + s[1:8]
        return s[8] == letras[int(num) % 23]
    # CIF: letra + 7 digitos + control (digito o letra)
    if len(s) == 9 and s[0] in "ABCDEFGHJNPQRSUVW" and s[1:8].isdigit():
        digs = s[1:8]
        suma_par = sum(int(d) for d in digs[1::2])
        suma_impar = 0
        for d in digs[0::2]:
            x = int(d) * 2
            suma_impar += x if x < 10 else x - 9
        c = (10 - (suma_par + suma_impar) % 10) % 10
        control = s[8]
        letra_ctrl = "JABCDEFGHI"[c]
        if s[0] in "PQSW" or s[8].isalpha():   # control debe ser letra
            return control == letra_ctrl
        if s[0] in "ABEH":                     # control debe ser digito
            return control == str(c)
        return control == str(c) or control == letra_ctrl
    return False


# Campos permitidos por tabla (para inserciones/actualizaciones seguras)
FIELDS = {
    "clientes": ["nombre", "nif", "telefono", "email", "direccion", "datos_cobro", "es_flexicar", "notas"],
    "transportistas": ["nombre", "nif", "telefono", "email", "direccion", "notas"],
    "vehiculos": ["matricula", "bastidor", "marca", "modelo", "version", "anio", "km",
                  "color", "combustible", "estado", "recepcionado", "luz_motor",
                  "reserva_cliente_id", "reserva_fecha", "almacen_id", "ubicacion",
                  "itv_pasada", "itv_expira", "proxima_revision", "etiqueta",
                  "fecha_liberacion", "ref_web", "foto", "notas"],
    "compras": ["vehiculo_id", "proveedor_id", "prov_id", "numero_factura",
                "regimen", "fecha", "precio", "gastos", "iva_pct", "forma_pago",
                "pagado", "fecha_pago_est", "fecha_pago", "factura_recibida", "fecha_factura", "notas"],
    "proveedores": ["nombre", "nif", "telefono", "email", "direccion", "notas"],
    "ventas": ["vehiculo_id", "cliente_id", "comercial_id", "numero_factura",
               "regimen", "fecha", "precio", "cruz_fin", "cruz_seg", "cruz_gar",
               "forma_pago", "fecha_cobro_est", "entregado",
               "fecha_entrega_cli", "estado_factura", "numero_proforma",
               "fecha_proforma", "fecha_entrega_doc", "notas"],
    "comerciales": ["nombre", "nif", "telefono", "email", "fecha_incorporacion",
                    "comision_pct", "franquicia", "activo", "notas"],
    "logistica": ["vehiculo_id", "transportista_id", "transportista", "origen",
                  "destino", "destinatario", "destinatario_id", "ubicacion", "almacen_id", "coste",
                  "fecha_recogida", "fecha_entrega", "estado",
                  "numero_factura", "factura_recibida", "fecha_factura", "pagado", "fecha_pago_est", "notas"],
    "almacenes": ["nombre", "direccion", "notas"],
    "recepciones": ["vehiculo_id", "fecha", "responsable", "almacen_id",
                    "ubicacion", "tiene_desperfectos", "desperfectos", "marcas", "luz_motor", "notas"],
    "traspasos": ["vehiculo_id", "almacen_destino", "fecha", "notas"],
    "garantias": ["vehiculo_id", "cliente_id", "tipo", "fecha_inicio", "meses",
                  "fecha_fin", "alcance", "estado", "notas"],
    "postventa": ["vehiculo_id", "tipo", "descripcion", "proveedor", "fecha",
                  "coste", "asume", "pago", "fecha_pago_est",
                  "numero_factura", "nif_proveedor", "iva_pct",
                  "factura_recibida", "fecha_factura", "notas"],
    "agenda": ["vehiculo_id", "fecha", "tipo", "asunto", "detalle",
               "cerrado", "motivo_cierre", "notas"],
    "cobros": ["venta_id", "fecha", "medio", "importe", "veh_cambio_id", "notas"],
    "taller": ["vehiculo_id", "tipo", "descripcion", "proveedor", "prov_id", "fecha",
               "coste", "pago", "fecha_pago_est",
               "numero_factura", "nif_proveedor", "iva_pct",
               "factura_recibida", "fecha_factura", "notas"],
    "leads": ["vehiculo_id", "comercial_id", "nombre", "canal", "telefono", "email",
              "nif", "direccion", "poblacion",
              "fecha", "estado", "proxima_fecha", "cerrado", "motivo_cierre", "notas"],
    "seguimientos": ["ambito", "ref_id", "fecha", "contacto", "detalle",
                     "proxima_fecha", "comercial_id"],
    "extractos": ["fecha", "cuenta", "nombre_archivo", "notas"],
    "movimientos": ["categoria", "ref_tipo", "ref_id", "conciliado",
                    "observacion_usuario", "observacion_app"],
    "gestoria": ["vehiculo_id", "tipo", "estado", "gestoria", "gestoria_id",
                 "fecha_solicitud", "fecha_resolucion",
                 "coste", "numero_factura", "nif_gestoria", "factura_recibida",
                 "fecha_factura", "pagado", "fecha_pago_est", "notas"],
    "gestorias": ["nombre", "nif", "telefono", "email", "direccion", "notas"],
    "documentos": ["vehiculo_id", "tipo", "importe", "fecha", "notas"],
    "listas": ["tipo", "valor", "padre"],
}

# Campos del vehiculo que pueden venir dentro del formulario de compra
VEH_INLINE = ["matricula", "marca", "modelo", "version", "bastidor"]


def _ensure_vehiculo(conn, data):
    """Para compras: si no hay vehiculo_id pero llegan datos de vehiculo,
    crea uno nuevo. Si hay vehiculo_id, actualiza sus datos basicos.
    Devuelve el vehiculo_id resultante. Modifica 'data' quitando los
    campos de vehiculo (no pertenecen a la tabla compras)."""
    veh = {k: data.pop(k) for k in VEH_INLINE if k in data}
    vid = data.get("vehiculo_id")
    if vid:
        sets = [k for k in veh if veh.get(k) not in (None, "")]
        if sets:
            assign = ",".join(f"{k}=?" for k in sets)
            conn.execute(f"UPDATE vehiculos SET {assign} WHERE id=?",
                         [veh[k] for k in sets] + [vid])
    else:
        if any(v not in (None, "") for v in veh.values()):
            cols = ",".join(veh.keys())
            ph = ",".join("?" for _ in veh)
            # Un vehiculo comprado entra como 'pendiente'; solo pasa a stock
            # (disponible) cuando se ENTREGA desde el area de logistica.
            cur = conn.execute(
                f"INSERT INTO vehiculos ({cols}, estado) VALUES ({ph}, 'pendiente')",
                list(veh.values()))
            vid = cur.lastrowid
            data["vehiculo_id"] = vid
    return vid


class ReglaNegocio(Exception):
    """Error de validacion de negocio que se devuelve al cliente (HTTP 400).
    Si puede_forzar=True, el frontend puede reintentar con {'forzar': true}."""
    def __init__(self, msg, puede_forzar=False):
        super().__init__(msg)
        self.puede_forzar = puede_forzar


def siguiente_factura(conn):
    """Devuelve el siguiente numero de factura correlativo del año en curso,
    con formato AAAA/NNNN. El contador solo sube (no reutiliza numeros)."""
    year = date.today().year
    clave = f"factura:{year}"
    conn.execute("INSERT OR IGNORE INTO contadores (clave, valor) VALUES (?, 0)", (clave,))
    conn.execute("UPDATE contadores SET valor = valor + 1 WHERE clave=?", (clave,))
    val = conn.execute("SELECT valor FROM contadores WHERE clave=?", (clave,)).fetchone()["valor"]
    return f"{year}/{val:04d}"


def siguiente_proforma(conn):
    """Numero de proforma correlativo del año, formato PRO-AAAA/NNNN (contador propio)."""
    year = date.today().year
    clave = f"proforma:{year}"
    conn.execute("INSERT OR IGNORE INTO contadores (clave, valor) VALUES (?, 0)", (clave,))
    conn.execute("UPDATE contadores SET valor = valor + 1 WHERE clave=?", (clave,))
    val = conn.execute("SELECT valor FROM contadores WHERE clave=?", (clave,)).fetchone()["valor"]
    return f"PRO-{year}/{val:04d}"


def confirmar_venta(venta_id):
    """Convierte una proforma en factura de venta: asigna nº correlativo,
    marca el coche como vendido y la venta como 'factura'."""
    conn = get_db()
    try:
        v = conn.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
        if not v:
            raise ReglaNegocio("Venta no encontrada.")
        if v["estado_factura"] == "factura":
            raise ReglaNegocio("Esta venta ya está confirmada como factura.")
        num = v["numero_factura"] if (v["numero_factura"] or "").strip() else siguiente_factura(conn)
        conn.execute(
            "UPDATE ventas SET estado_factura='factura', numero_factura=?, fecha=? WHERE id=?",
            (num, date.today().isoformat(), venta_id))
        if v["vehiculo_id"]:
            conn.execute("UPDATE vehiculos SET estado='vendido' WHERE id=?", (v["vehiculo_id"],))
        conn.commit()
        return num
    finally:
        conn.close()


def _nombre_comercial(conn, cid):
    if not cid:
        return "—"
    r = conn.execute("SELECT nombre FROM comerciales WHERE id=?", (cid,)).fetchone()
    return r["nombre"] if r else "—"


def _estado_vehiculo(conn, vid):
    r = conn.execute(
        "SELECT estado, matricula, recepcionado FROM vehiculos WHERE id=?", (vid,)).fetchone()
    return r


def _aplicar_entrega(conn, data):
    """Si un transporte se marca 'Entregado', el vehiculo entra en stock
    (estado 'disponible') con la ubicacion indicada."""
    if data.get("estado") == "Entregado" and data.get("vehiculo_id"):
        # Recepcionado en instalaciones. Si estaba 'pendiente' pasa a 'disponible';
        # si estaba 'reservado' (reserva anticipada) mantiene la reserva.
        conn.execute(
            """UPDATE vehiculos SET recepcionado=1,
                   estado=CASE WHEN estado='pendiente' THEN 'disponible' ELSE estado END,
                   ubicacion=COALESCE(?, ubicacion),
                   almacen_id=COALESCE(?, almacen_id)
               WHERE id=?""",
            (data.get("ubicacion") or None, data.get("almacen_id") or None,
             data.get("vehiculo_id")))


def registrar_recepcion(data):
    """Recepción del vehículo en las instalaciones: lo da de alta en stock,
    guarda el parte de desperfectos (con las marcas del diagrama), el responsable
    y la localización."""
    vid = data.get("vehiculo_id")
    if not vid:
        raise ReglaNegocio("Falta indicar el vehículo a recepcionar.")
    conn = get_db()
    try:
        # No recepcionar sin transporte, salvo confirmación (con motivo en las notas)
        if not data.get("forzar"):
            n = conn.execute("SELECT COUNT(*) AS c FROM logistica WHERE vehiculo_id=?", (vid,)).fetchone()["c"]
            if not n:
                raise ReglaNegocio(
                    "Este vehículo no tiene ningún transporte dado de alta. Da de alta el "
                    "transporte en Logística, o confirma que el vehículo NO necesita transporte "
                    "indicando el motivo.", puede_forzar=True)
        marcas = data.get("marcas")
        if isinstance(marcas, (list, dict)):
            marcas = json.dumps(marcas, ensure_ascii=False)
        luz = data.get("luz_motor") or ""
        cur = conn.execute(
            """INSERT INTO recepciones
               (vehiculo_id, fecha, responsable, almacen_id, ubicacion,
                tiene_desperfectos, desperfectos, marcas, luz_motor, notas)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (vid, data.get("fecha") or date.today().isoformat(),
             data.get("responsable"), data.get("almacen_id") or None,
             data.get("ubicacion"), 1 if data.get("tiene_desperfectos") else 0,
             data.get("desperfectos"), marcas, luz, data.get("notas")))
        rid = cur.lastrowid
        conn.execute(
            """UPDATE vehiculos SET recepcionado=1,
                   estado=CASE WHEN estado='pendiente' THEN 'disponible' ELSE estado END,
                   ubicacion=COALESCE(?, ubicacion),
                   almacen_id=COALESCE(?, almacen_id),
                   luz_motor=?
               WHERE id=?""",
            (data.get("ubicacion") or None, data.get("almacen_id") or None, luz, vid))
        # Al recepcionar, el transporte deja de estar 'En tránsito' → 'Entregado'
        fentrega = data.get("fecha") or date.today().isoformat()
        conn.execute(
            """UPDATE logistica SET estado='Entregado',
                   fecha_entrega=COALESCE(NULLIF(fecha_entrega,''), ?)
               WHERE vehiculo_id=? AND (estado IS NULL OR estado!='Entregado')""",
            (fentrega, vid))
        conn.commit()
        return rid
    finally:
        conn.close()


def list_recepciones(q=None):
    conn = get_db()
    rows = conn.execute(
        """SELECT r.*, v.matricula, v.marca, v.modelo, a.nombre AS almacen_nombre
           FROM recepciones r
           LEFT JOIN vehiculos v ON v.id=r.vehiculo_id
           LEFT JOIN almacenes a ON a.id=r.almacen_id
           ORDER BY r.fecha DESC, r.id DESC""").fetchall()
    conn.close()
    return rows_to_list(rows)


def insert_row(table, data):
    conn = get_db()
    try:
        if table == "compras":
            _ensure_vehiculo(conn, data)

        # Trazabilidad: no registrar cargos/gestiones sobre un coche NO recepcionado
        if table in ("taller", "postventa") and data.get("vehiculo_id"):
            vg = _estado_vehiculo(conn, data["vehiculo_id"])
            if vg and not vg["recepcionado"] and not data.get("forzar"):
                raise ReglaNegocio(
                    f"El vehículo {vg['matricula'] or ''} aún NO ha sido recepcionado en las "
                    f"instalaciones (pendiente de llegar). No deberían registrarse cargos ni "
                    f"gestiones sobre él hasta su recepción.", puede_forzar=True)

        # Gestoría: no iniciar trámites si el coche aún no ha sido recepcionado
        if table == "gestoria" and data.get("vehiculo_id"):
            vg = _estado_vehiculo(conn, data["vehiculo_id"])
            if vg and not vg["recepcionado"] and not data.get("forzar"):
                raise ReglaNegocio(
                    f"El vehículo {vg['matricula'] or ''} aún NO ha sido recepcionado en las "
                    f"instalaciones. No debería enviarse documentación a la gestoría antes de "
                    f"recibirlo. ¿Confirmas que quieres enviar la documentación igualmente?",
                    puede_forzar=True)

        # Coche a cambio: verificar la documentacion de la compra antes de aceptarlo como pago
        if table == "cobros" and data.get("medio") == "Coche a cambio" and data.get("veh_cambio_id"):
            faltan = docs_faltantes_compra(conn, data["veh_cambio_id"])
            if faltan and not data.get("forzar"):
                raise ReglaNegocio(
                    "No puedes compensar el coche entregado a cambio: falta documentación de "
                    "su compra (" + ", ".join(faltan) + "). Complétala en la ficha de ese "
                    "coche, o acepta expresamente que el cliente no está obligado a aportarla.",
                    puede_forzar=True)

        # Regla: no se puede vender un vehiculo que no este recepcionado / en stock
        if table == "ventas":
            vid = data.get("vehiculo_id")
            v = _estado_vehiculo(conn, vid) if vid else None
            if not v:
                raise ReglaNegocio("Selecciona un vehículo para la venta.")
            if not v["recepcionado"]:
                raise ReglaNegocio(
                    f"El vehículo {v['matricula'] or ''} aún no ha sido recepcionado; "
                    f"no se puede vender hasta que llegue a las instalaciones.")
            if v["estado"] not in ("disponible", "reservado"):
                raise ReglaNegocio(
                    f"El vehículo {v['matricula'] or ''} no está en stock "
                    f"(estado: {v['estado']}). Solo se pueden vender vehículos entregados/en stock.")
            # Toda venta nace como PROFORMA: nº de proforma propio; la factura
            # correlativa se asigna solo al CONFIRMAR la proforma.
            data["estado_factura"] = "proforma"
            data["numero_factura"] = ""
            if not (str(data.get("numero_proforma") or "").strip()):
                data["numero_proforma"] = siguiente_proforma(conn)
            if not (str(data.get("fecha_proforma") or "").strip()):
                data["fecha_proforma"] = data.get("fecha") or date.today().isoformat()

        # traspasos: registra el movimiento y actualiza el almacen del vehiculo
        if table == "traspasos":
            vid = data.get("vehiculo_id")
            dest = data.get("almacen_destino")
            row = conn.execute("SELECT almacen_id FROM vehiculos WHERE id=?", (vid,)).fetchone()
            origen = row["almacen_id"] if row else None
            cur = conn.execute(
                """INSERT INTO traspasos (vehiculo_id, almacen_origen, almacen_destino, fecha, notas)
                   VALUES (?,?,?,?,?)""",
                (vid, origen, dest, data.get("fecha"), data.get("notas")))
            conn.execute("UPDATE vehiculos SET almacen_id=? WHERE id=?", (dest, vid))
            conn.commit()
            nid = cur.lastrowid
            conn.close()
            return nid

        # listas: evitar duplicados (INSERT OR IGNORE) y devolver id existente
        if table == "listas":
            data.setdefault("padre", "")
            conn.execute(
                "INSERT OR IGNORE INTO listas (tipo, valor, padre) VALUES (?,?,?)",
                (data.get("tipo"), data.get("valor"), data.get("padre") or ""))
            conn.commit()
            row = conn.execute(
                "SELECT id FROM listas WHERE tipo=? AND valor=? AND padre=?",
                (data.get("tipo"), data.get("valor"), data.get("padre") or "")).fetchone()
            conn.close()
            return row["id"] if row else None

        fields = [f for f in FIELDS[table] if f in data]
        placeholders = ",".join("?" for _ in fields)
        cols = ",".join(fields)
        values = [data.get(f) for f in fields]
        cur = conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", values)
        new_id = cur.lastrowid

        if table == "ventas" and data.get("vehiculo_id"):
            # Proforma nueva: solo reserva el coche si se pide expresamente (checkbox).
            # Una proforma-presupuesto no retira el coche de la venta a otros.
            if data.get("reservar"):
                conn.execute("UPDATE vehiculos SET estado='reservado' WHERE id=? AND estado!='vendido'",
                             (data.get("vehiculo_id"),))
        if table == "logistica":
            _aplicar_entrega(conn, data)
        conn.commit()
        return new_id
    finally:
        try:
            conn.close()
        except Exception:
            pass


def update_row(table, row_id, data):
    conn = get_db()
    try:
        if table == "compras":
            _ensure_vehiculo(conn, data)
            # Al marcar la compra pagada, guardar la fecha real de pago (si no la había)
            if data.get("pagado") == "Sí" and not (str(data.get("fecha_pago") or "").strip()):
                cur = conn.execute("SELECT fecha_pago FROM compras WHERE id=?", (row_id,)).fetchone()
                if not (cur and (cur["fecha_pago"] or "").strip()):
                    data["fecha_pago"] = date.today().isoformat()

        # Cerrar una gestión (lead o reclamación) exige consignar el motivo
        if table in ("leads", "agenda") and data.get("cerrado"):
            if not (str(data.get("motivo_cierre") or "").strip()):
                raise ReglaNegocio("Para cerrar la gestión debes indicar el motivo del cierre.")

        # Cambio de comercial de un lead: exige motivo y lo registra en el historial
        if table == "leads" and "comercial_id" in data:
            cur = conn.execute("SELECT comercial_id, notas FROM leads WHERE id=?", (row_id,)).fetchone()
            old = cur["comercial_id"] if cur else None
            new = data.get("comercial_id")
            if old is not None and old != new:
                motivo = (data.get("motivo_cambio") or "").strip()
                if not motivo:
                    raise ReglaNegocio("Para cambiar el comercial del lead debes indicar el motivo del cambio.")
                linea = (f"[{date.today().isoformat()}] Cambio de comercial: "
                         f"{_nombre_comercial(conn, old)} → {_nombre_comercial(conn, new)}. Motivo: {motivo}")
                prev = (cur["notas"] or "") if cur else ""
                data["notas"] = (prev + ("\n" if prev else "") + linea)

        if table == "ventas" and "vehiculo_id" in data:
            vid = data.get("vehiculo_id")
            v = _estado_vehiculo(conn, vid) if vid else None
            if v and v["estado"] not in ("disponible", "reservado", "vendido"):
                raise ReglaNegocio(
                    f"El vehículo {v['matricula'] or ''} no está en stock "
                    f"(estado: {v['estado']}).")

        fields = [f for f in FIELDS[table] if f in data]
        if not fields:
            return
        assignments = ",".join(f"{f}=?" for f in fields)
        values = [data.get(f) for f in fields] + [row_id]
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id=?", values)

        if table == "ventas" and data.get("vehiculo_id"):
            ef = conn.execute("SELECT estado_factura FROM ventas WHERE id=?", (row_id,)).fetchone()
            nuevo = "vendido" if (ef and ef["estado_factura"] == "factura") else "reservado"
            conn.execute("UPDATE vehiculos SET estado=? WHERE id=? AND estado!='vendido'",
                         (nuevo, data.get("vehiculo_id")))
        if table == "logistica":
            _aplicar_entrega(conn, data)
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def delete_row(table, row_id):
    conn = get_db()
    conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
    conn.commit()
    conn.close()


def _borrar_ficheros_docs(conn, where_sql, params):
    """Borra del disco los archivos escaneados de los documentos seleccionados."""
    for r in conn.execute(f"SELECT archivo FROM documentos WHERE {where_sql}", params).fetchall():
        if r["archivo"]:
            try:
                os.remove(os.path.join(DOCS_DIR, r["archivo"]))
            except OSError:
                pass


def borrar_vehiculo(vid):
    """Elimina un vehículo y, por CASCADE, todo lo asociado. Limpia también los ficheros del expediente."""
    conn = get_db()
    _borrar_ficheros_docs(conn, "vehiculo_id=?", (vid,))
    conn.execute("DELETE FROM vehiculos WHERE id=?", (vid,))
    conn.commit()
    conn.close()


def vaciar_stock():
    """Elimina TODOS los vehículos (y por CASCADE compras, ventas, taller, etc.). Devuelve cuántos había."""
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) AS n FROM vehiculos").fetchone()["n"]
    _borrar_ficheros_docs(conn, "vehiculo_id IS NOT NULL", ())
    conn.execute("DELETE FROM vehiculos")
    conn.commit()
    conn.close()
    return n


# --------------------------------------------------------------------------
# Consultas de listados (con JOINs y busqueda)
# --------------------------------------------------------------------------

def _with_nif_ok(rows):
    out = []
    for r in rows:
        d = dict(r)
        d["nif_ok"] = validar_nif(d.get("nif"))
        out.append(d)
    return out


def list_clientes(q=None):
    conn = get_db()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT * FROM clientes
               WHERE nombre LIKE ? OR nif LIKE ? OR telefono LIKE ?
                     OR email LIKE ? OR direccion LIKE ?
               ORDER BY nombre""",
            (like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM clientes ORDER BY nombre").fetchall()
    conn.close()
    return _with_nif_ok(rows)


def list_comerciales(q=None):
    conn = get_db()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT * FROM comerciales WHERE nombre LIKE ? OR nif LIKE ? OR email LIKE ? ORDER BY nombre",
            (like, like, like)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM comerciales ORDER BY nombre").fetchall()
    conn.close()
    return _with_nif_ok(rows)


def list_proveedores(q=None):
    conn = get_db()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT * FROM proveedores
               WHERE nombre LIKE ? OR nif LIKE ? OR telefono LIKE ?
                     OR email LIKE ? OR direccion LIKE ?
               ORDER BY nombre""",
            (like, like, like, like, like)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()
    conn.close()
    return _with_nif_ok(rows)


def list_garantias(q=None):
    conn = get_db()
    base = """
        SELECT g.*, v.matricula, v.marca, v.modelo, cl.nombre AS cliente
        FROM garantias g
        LEFT JOIN vehiculos v ON v.id = g.vehiculo_id
        LEFT JOIN clientes cl ON cl.id = g.cliente_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE g.tipo LIKE ? OR g.estado LIKE ? OR g.alcance LIKE ?
                             OR v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                             OR cl.nombre LIKE ?
                       ORDER BY g.fecha_fin DESC, g.id DESC""",
            (like, like, like, like, like, like, like)).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY g.fecha_fin DESC, g.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_postventa(q=None):
    conn = get_db()
    base = """
        SELECT p.*, v.matricula, v.marca, v.modelo
        FROM postventa p LEFT JOIN vehiculos v ON v.id = p.vehiculo_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE p.tipo LIKE ? OR p.descripcion LIKE ? OR p.proveedor LIKE ?
                             OR v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                       ORDER BY p.fecha DESC, p.id DESC""",
            (like, like, like, like, like, like)).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY p.fecha DESC, p.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_seguimientos(q=None):
    conn = get_db()
    rows = conn.execute(
        """SELECT s.*, co.nombre AS comercial
           FROM seguimientos s LEFT JOIN comerciales co ON co.id = s.comercial_id
           ORDER BY s.fecha, s.id""").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_agenda(q=None):
    conn = get_db()
    base = """
        SELECT a.*, v.matricula, v.marca, v.modelo
        FROM agenda a LEFT JOIN vehiculos v ON v.id = a.vehiculo_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE a.tipo LIKE ? OR a.asunto LIKE ? OR a.detalle LIKE ?
                             OR v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                       ORDER BY a.fecha DESC, a.id DESC""",
            (like, like, like, like, like, like)).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY a.fecha DESC, a.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_cobros(q=None):
    conn = get_db()
    rows = conn.execute(
        """SELECT c.*, vc.matricula AS cambio_matricula, vc.marca AS cambio_marca,
                  vc.modelo AS cambio_modelo
           FROM cobros c
           LEFT JOIN vehiculos vc ON vc.id = c.veh_cambio_id
           ORDER BY c.fecha, c.id""").fetchall()
    conn.close()
    return rows_to_list(rows)


# Documentos minimos que debe aportar la compra de un coche (p.ej. un coche a cambio)
REQUIRED_COMPRA_DOCS = ["Factura de compra", "Permiso de circulación", "Ficha técnica"]


def docs_faltantes_compra(conn, vehiculo_id):
    have = {r["tipo"] for r in conn.execute(
        "SELECT DISTINCT tipo FROM documentos WHERE vehiculo_id=? AND (agenda_id IS NULL OR agenda_id='')",
        (vehiculo_id,)).fetchall()}
    return [t for t in REQUIRED_COMPRA_DOCS if t not in have]


def list_transportistas(q=None):
    conn = get_db()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT * FROM transportistas
               WHERE nombre LIKE ? OR nif LIKE ? OR telefono LIKE ?
                     OR email LIKE ? OR direccion LIKE ?
               ORDER BY nombre""",
            (like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM transportistas ORDER BY nombre").fetchall()
    conn.close()
    return _with_nif_ok(rows)


def list_listas(tipo=None, padre=None):
    conn = get_db()
    if tipo and padre is not None:
        rows = conn.execute(
            "SELECT * FROM listas WHERE tipo=? AND padre=? ORDER BY valor",
            (tipo, padre)).fetchall()
    elif tipo:
        rows = conn.execute(
            "SELECT * FROM listas WHERE tipo=? ORDER BY valor", (tipo,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM listas ORDER BY tipo, valor").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_itv_avisos(dias=15):
    """Vehiculos EN STOCK cuya ITV caduca en los proximos 'dias' dias
    (o ya esta caducada). Ordenados por fecha de expiracion."""
    hoy = date.today()
    limite = (hoy + timedelta(days=dias)).isoformat()
    conn = get_db()
    rows = conn.execute(
        """SELECT id, matricula, marca, modelo, ubicacion, itv_expira
           FROM vehiculos
           WHERE estado='disponible' AND itv_expira IS NOT NULL AND itv_expira<>''
                 AND itv_expira <= ?
           ORDER BY itv_expira""",
        (limite,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            fexp = date.fromisoformat(d["itv_expira"][:10])
            d["dias_restantes"] = (fexp - hoy).days
        except Exception:
            d["dias_restantes"] = None
        out.append(d)
    return out


def list_vehiculos(q=None):
    conn = get_db()
    base = """
        SELECT v.*,
               (SELECT nombre FROM almacenes a WHERE a.id=v.almacen_id) AS almacen_nombre,
               (SELECT precio FROM compras c WHERE c.vehiculo_id=v.id ORDER BY c.id DESC LIMIT 1) AS precio_compra,
               (SELECT precio FROM ventas  s WHERE s.vehiculo_id=v.id ORDER BY s.id DESC LIMIT 1) AS precio_venta
        FROM vehiculos v
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE v.matricula LIKE ? OR v.bastidor LIKE ? OR v.marca LIKE ?
                             OR v.modelo LIKE ? OR v.color LIKE ? OR v.combustible LIKE ?
                             OR v.ref_web LIKE ?
                       ORDER BY v.marca, v.modelo""",
            (like, like, like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY v.creado DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_compras(q=None):
    conn = get_db()
    base = """
        SELECT c.*, v.matricula, v.marca, v.modelo, v.bastidor,
               COALESCE(p.nombre, cl.nombre) AS proveedor
        FROM compras c
        LEFT JOIN vehiculos v ON v.id = c.vehiculo_id
        LEFT JOIN clientes  cl ON cl.id = c.proveedor_id
        LEFT JOIN proveedores p ON p.id = c.prov_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                             OR v.bastidor LIKE ? OR cl.nombre LIKE ?
                             OR c.numero_factura LIKE ?
                       ORDER BY c.fecha DESC, c.id DESC""",
            (like, like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY c.fecha DESC, c.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_ventas(q=None):
    conn = get_db()
    base = """
        SELECT s.*, v.matricula, v.marca, v.modelo, v.bastidor, v.anio, v.km,
               cl.nombre AS cliente, cl.nif AS cliente_nif,
               cl.direccion AS cliente_direccion, cl.email AS cliente_email,
               cl.telefono AS cliente_telefono, cl.es_flexicar AS cliente_flexicar, co.nombre AS comercial,
               (COALESCE((SELECT precio + gastos FROM compras c WHERE c.vehiculo_id=v.id ORDER BY c.id DESC LIMIT 1),0)
                + COALESCE((SELECT SUM(coste) FROM taller t WHERE t.vehiculo_id=v.id),0)
                + COALESCE((SELECT SUM(coste) FROM logistica l WHERE l.vehiculo_id=v.id),0)) AS coste
        FROM ventas s
        LEFT JOIN vehiculos v ON v.id = s.vehiculo_id
        LEFT JOIN clientes  cl ON cl.id = s.cliente_id
        LEFT JOIN comerciales co ON co.id = s.comercial_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                             OR v.bastidor LIKE ? OR cl.nombre LIKE ?
                             OR s.numero_factura LIKE ?
                       ORDER BY s.fecha DESC, s.id DESC""",
            (like, like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY s.fecha DESC, s.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_taller(q=None):
    conn = get_db()
    base = """
        SELECT t.*, v.matricula, v.marca, v.modelo,
               COALESCE(p.nombre, t.proveedor) AS proveedor
        FROM taller t
        LEFT JOIN vehiculos v ON v.id = t.vehiculo_id
        LEFT JOIN proveedores p ON p.id = t.prov_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE t.tipo LIKE ? OR t.descripcion LIKE ? OR COALESCE(p.nombre, t.proveedor) LIKE ?
                             OR v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                       ORDER BY t.fecha DESC, t.id DESC""",
            (like, like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY t.fecha DESC, t.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_gestorias(q=None):
    conn = get_db()
    rows = conn.execute("SELECT * FROM gestorias ORDER BY nombre").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_leads(q=None):
    conn = get_db()
    base = """
        SELECT l.*, v.matricula, v.marca, v.modelo, co.nombre AS comercial
        FROM leads l LEFT JOIN vehiculos v ON v.id = l.vehiculo_id
        LEFT JOIN comerciales co ON co.id = l.comercial_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE l.nombre LIKE ? OR l.canal LIKE ? OR l.estado LIKE ?
                             OR v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                       ORDER BY l.fecha DESC, l.id DESC""",
            (like, like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY l.fecha DESC, l.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_almacenes(q=None):
    conn = get_db()
    rows = conn.execute("SELECT * FROM almacenes ORDER BY nombre").fetchall()
    out = []
    for a in rows:
        st = conn.execute(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM((SELECT c.precio FROM compras c
                          WHERE c.vehiculo_id=v.id ORDER BY c.id DESC LIMIT 1)),0) AS valor
               FROM vehiculos v
               WHERE v.estado='disponible' AND v.almacen_id=?""",
            (a["id"],)).fetchone()
        d = dict(a)
        d["stock"] = st["n"]
        d["valor"] = st["valor"]
        out.append(d)
    conn.close()
    if q:
        ql = q.lower()
        out = [a for a in out if ql in (a["nombre"] or "").lower()
               or ql in (a["direccion"] or "").lower()]
    return out


def list_traspasos(q=None):
    conn = get_db()
    rows = conn.execute(
        """SELECT t.*, v.matricula, v.marca, v.modelo,
                  ao.nombre AS origen_nombre, ad.nombre AS destino_nombre
           FROM traspasos t
           LEFT JOIN vehiculos v ON v.id = t.vehiculo_id
           LEFT JOIN almacenes ao ON ao.id = t.almacen_origen
           LEFT JOIN almacenes ad ON ad.id = t.almacen_destino
           ORDER BY t.fecha DESC, t.id DESC""").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_gestoria(q=None):
    conn = get_db()
    base = """
        SELECT g.*, v.matricula, v.marca, v.modelo,
               COALESCE(ge.nombre, g.gestoria) AS gestoria
        FROM gestoria g
        LEFT JOIN vehiculos v ON v.id = g.vehiculo_id
        LEFT JOIN gestorias ge ON ge.id = g.gestoria_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE g.tipo LIKE ? OR g.estado LIKE ? OR COALESCE(ge.nombre, g.gestoria) LIKE ?
                             OR v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                       ORDER BY g.fecha_solicitud DESC, g.id DESC""",
            (like, like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(base + " ORDER BY g.fecha_solicitud DESC, g.id DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_documentos(vehiculo_id=None):
    conn = get_db()
    if vehiculo_id:
        rows = conn.execute(
            "SELECT * FROM documentos WHERE vehiculo_id=? ORDER BY tipo, id",
            (vehiculo_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM documentos ORDER BY vehiculo_id, tipo, id").fetchall()
    conn.close()
    return rows_to_list(rows)


def guardar_documento(data):
    """Decodifica el archivo (dataURI base64), lo guarda en disco y crea el registro."""
    vid = data.get("vehiculo_id")
    tipo = data.get("tipo")
    dataurl = data.get("data") or ""
    m = re.match(r"data:([^;]+);base64,(.*)", dataurl, re.S)
    if not m or not vid or not tipo:
        raise ReglaNegocio("Archivo o datos no válidos.")
    mime = m.group(1)
    try:
        raw = base64.b64decode(m.group(2))
    except Exception:
        raise ReglaNegocio("No se pudo leer el archivo.")
    if len(raw) > 20 * 1024 * 1024:
        raise ReglaNegocio("El archivo supera los 20 MB.")
    ext = (mimetypes.guess_extension(mime) or "").lstrip(".")
    if not ext:
        fn = data.get("filename") or ""
        ext = (fn.rsplit(".", 1)[-1] if "." in fn else "bin").lower()[:5]
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO documentos (vehiculo_id, tipo, nombre_original, mime, importe, fecha, notas, agenda_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (vid, tipo, data.get("filename"), mime,
         data.get("importe"), data.get("fecha"), data.get("notas"),
         data.get("agenda_id")))
    did = cur.lastrowid
    fname = f"doc_{did}.{ext}"
    with open(os.path.join(DOCS_DIR, fname), "wb") as f:
        f.write(raw)
    conn.execute("UPDATE documentos SET archivo=? WHERE id=?", (fname, did))
    conn.commit()
    conn.close()
    return did


def borrar_documento(did):
    conn = get_db()
    row = conn.execute("SELECT archivo FROM documentos WHERE id=?", (did,)).fetchone()
    if row and row["archivo"]:
        try:
            os.remove(os.path.join(DOCS_DIR, row["archivo"]))
        except OSError:
            pass
    conn.execute("DELETE FROM documentos WHERE id=?", (did,))
    conn.commit()
    conn.close()


def list_logistica(q=None):
    conn = get_db()
    base = """
        SELECT l.*, v.matricula, v.marca, v.modelo,
               COALESCE(t.nombre, l.transportista) AS transportista_nombre
        FROM logistica l
        LEFT JOIN vehiculos v ON v.id = l.vehiculo_id
        LEFT JOIN transportistas t ON t.id = l.transportista_id
    """
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            base + """ WHERE COALESCE(t.nombre,l.transportista) LIKE ? OR l.origen LIKE ?
                             OR l.destino LIKE ? OR l.destinatario LIKE ? OR l.estado LIKE ?
                             OR v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ?
                       ORDER BY (l.fecha_recogida IS NULL), l.fecha_recogida DESC, l.id DESC""",
            (like, like, like, like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(
            base + " ORDER BY (l.fecha_recogida IS NULL), l.fecha_recogida DESC, l.id DESC"
        ).fetchall()
    conn.close()
    return rows_to_list(rows)


# --------------------------------------------------------------------------
# Panel de control (estadisticas personalizables)
# --------------------------------------------------------------------------

def dashboard(params):
    desde = params.get("desde", [""])[0]
    hasta = params.get("hasta", [""])[0]
    group_by = params.get("group_by", ["mes"])[0]   # mes | marca | modelo | combustible
    marca = params.get("marca", [""])[0]

    # Expresion de agrupacion segura
    group_expr = {
        "mes":         "substr(fecha,1,7)",
        "marca":       "marca",
        "modelo":      "marca || ' ' || modelo",
        "combustible": "combustible",
    }.get(group_by, "substr(fecha,1,7)")

    def build_filters(alias_fecha):
        clauses = []
        args = []
        if desde:
            clauses.append(f"{alias_fecha} >= ?")
            args.append(desde)
        if hasta:
            clauses.append(f"{alias_fecha} <= ?")
            args.append(hasta)
        if marca:
            clauses.append("v.marca = ?")
            args.append(marca)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, args

    conn = get_db()

    # --- Totales generales ---
    where_c, args_c = build_filters("c.fecha")
    where_s, args_s = build_filters("s.fecha")

    tot_compras = conn.execute(
        f"""SELECT COALESCE(SUM(c.precio+c.gastos),0) AS total, COUNT(*) AS n
            FROM compras c LEFT JOIN vehiculos v ON v.id=c.vehiculo_id {where_c}""",
        args_c,
    ).fetchone()

    tot_ventas = conn.execute(
        f"""SELECT COALESCE(SUM(s.precio),0) AS total, COUNT(*) AS n
            FROM ventas s LEFT JOIN vehiculos v ON v.id=s.vehiculo_id {where_s}""",
        args_s,
    ).fetchone()

    # Margen: por cada venta, precio de venta menos coste de compra del vehiculo
    margen_row = conn.execute(
        f"""SELECT COALESCE(SUM(s.precio - COALESCE(
                    (SELECT c.precio + c.gastos FROM compras c
                     WHERE c.vehiculo_id = s.vehiculo_id ORDER BY c.id DESC LIMIT 1), 0)),0) AS margen
            FROM ventas s LEFT JOIN vehiculos v ON v.id=s.vehiculo_id {where_s}""",
        args_s,
    ).fetchone()

    # --- Serie agrupada de compras ---
    g = group_expr if group_by == "mes" else group_expr  # marca/modelo/combustible vienen de vehiculos
    compras_group = conn.execute(
        f"""SELECT {'substr(c.fecha,1,7)' if group_by=='mes' else group_expr} AS clave,
                   COALESCE(SUM(c.precio+c.gastos),0) AS total, COUNT(*) AS n
            FROM compras c LEFT JOIN vehiculos v ON v.id=c.vehiculo_id {where_c}
            GROUP BY clave ORDER BY clave""",
        args_c,
    ).fetchall()

    ventas_group = conn.execute(
        f"""SELECT {'substr(s.fecha,1,7)' if group_by=='mes' else group_expr} AS clave,
                   COALESCE(SUM(s.precio),0) AS total, COUNT(*) AS n
            FROM ventas s LEFT JOIN vehiculos v ON v.id=s.vehiculo_id {where_s}
            GROUP BY clave ORDER BY clave""",
        args_s,
    ).fetchall()

    # Stock actual y su valoracion a precio de compra de cada vehiculo
    stock = conn.execute(
        """SELECT COUNT(*) AS n,
                  COALESCE(SUM(
                    (SELECT c.precio FROM compras c
                     WHERE c.vehiculo_id = v.id ORDER BY c.id DESC LIMIT 1)
                  ),0) AS valor
           FROM vehiculos v WHERE v.estado='disponible'"""
    ).fetchone()

    # Lista de marcas para el filtro
    marcas = [r["marca"] for r in conn.execute(
        "SELECT DISTINCT marca FROM vehiculos WHERE marca IS NOT NULL AND marca<>'' ORDER BY marca"
    ).fetchall()]

    conn.close()

    return {
        "totales": {
            "compras": tot_compras["total"],
            "n_compras": tot_compras["n"],
            "ventas": tot_ventas["total"],
            "n_ventas": tot_ventas["n"],
            "margen": margen_row["margen"],
            "stock": stock["n"],
            "valor_stock": stock["valor"],
        },
        "group_by": group_by,
        "compras_group": rows_to_list(compras_group),
        "ventas_group": rows_to_list(ventas_group),
        "marcas": marcas,
    }


# --------------------------------------------------------------------------
# Conciliacion con la web (minacar.es) mediante su sitemap publico
# --------------------------------------------------------------------------

SITEMAP_VEHICULOS = "https://www.minacar.es/sitemap.vehiculosDetalles.xml"


def _slug_norm(s):
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _extract_ref(s):
    """Ultimo grupo de 4+ digitos (la referencia numerica de la web)."""
    if not s:
        return None
    m = re.findall(r"\d{4,}", str(s))
    return m[-1] if m else None


def _parse_sitemap(xml_bytes, marcas):
    root = ET.fromstring(xml_bytes)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
          "image": "http://www.google.com/schemas/sitemap-image/1.1"}
    # marcas ordenadas por longitud de slug (para casar 'mercedes-benz' antes que 'mercedes')
    marcas_slug = sorted(((m, _slug_norm(m)) for m in marcas), key=lambda x: -len(x[1]))
    out = []
    vistos = set()
    for url in root.findall("sm:url", ns):
        loc = url.findtext("sm:loc", default="", namespaces=ns) or ""
        # Solo la ficha canonica: la web repite cada coche en /vehiculos-detalle/,
        # /vehiculos-detalle-contacto/, etc. Nos quedamos con la canonica.
        if "/vehiculos-detalle/" not in loc:
            continue
        lastmod = url.findtext("sm:lastmod", default="", namespaces=ns) or ""
        img = url.find("image:image/image:loc", ns)
        imagen = img.text if img is not None else None
        ref = _extract_ref(loc)
        if ref in vistos:
            continue
        vistos.add(ref)
        slug = loc.split("/vehiculos-detalle/", 1)[1] if "/vehiculos-detalle/" in loc else ""
        slug_sin_id = re.sub(r"-?\d{4,}$", "", slug)
        marca, modelo = "", ""
        for m, ms in marcas_slug:
            if ms and (slug_sin_id == ms or slug_sin_id.startswith(ms + "-")):
                marca = m
                modelo = slug_sin_id[len(ms):].strip("-").replace("-", " ")
                break
        if not marca and slug_sin_id:   # respaldo: primera palabra como marca
            partes = slug_sin_id.split("-")
            marca = partes[0].capitalize()
            modelo = " ".join(partes[1:])
        out.append({
            "ref": ref, "url": loc, "lastmod": lastmod[:10], "imagen": imagen,
            "marca": marca, "modelo": modelo,
            "titulo": slug_sin_id.replace("-", " ").strip(),
        })
    return out


def web_sync():
    conn = get_db()
    marcas = [r["valor"] for r in conn.execute(
        "SELECT valor FROM listas WHERE tipo='marca'").fetchall()]
    vehiculos = rows_to_list(conn.execute(
        "SELECT id, matricula, marca, modelo, estado, ref_web, ubicacion FROM vehiculos"
    ).fetchall())
    conn.close()

    try:
        req = urllib.request.Request(
            SITEMAP_VEHICULOS, headers={"User-Agent": "MinacarApp/1.0 (gestion local)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            xmlb = r.read()
    except Exception as e:
        return {"ok": False,
                "error": f"No se pudo descargar el índice de la web (¿sin conexión a internet?): {e}"}

    try:
        web = _parse_sitemap(xmlb, marcas)
    except Exception as e:
        return {"ok": False, "error": f"No se pudo interpretar el índice de la web: {e}"}

    app_por_ref = {}
    for v in vehiculos:
        r = _extract_ref(v.get("ref_web"))
        if r:
            app_por_ref[r] = v

    refs_web = set()
    for w in web:
        refs_web.add(w["ref"])
        m = app_por_ref.get(w["ref"])
        w["app_id"] = m["id"] if m else None
        w["app_matricula"] = m["matricula"] if m else None

    sin_publicar = []
    for v in vehiculos:
        if v.get("estado") == "disponible":
            r = _extract_ref(v.get("ref_web"))
            if not r or r not in refs_web:
                sin_publicar.append(v)

    web.sort(key=lambda w: (w["app_id"] is not None, w["marca"], w["modelo"]))
    return {
        "ok": True,
        "publicados": web,
        "sin_publicar": sin_publicar,
        "vehiculos": vehiculos,
        "resumen": {
            "web": len(web),
            "stock": sum(1 for v in vehiculos if v.get("estado") == "disponible"),
            "vinculados": sum(1 for w in web if w["app_id"]),
        },
    }


# --------------------------------------------------------------------------
# Informe Excel (.xlsx nativo, varias hojas) — solo libreria estandar (zipfile)
# --------------------------------------------------------------------------

def _col_letter(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _xml_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _sheet_xml(cols, rows):
    def cell(ci, ri, val):
        ref = f"{_col_letter(ci)}{ri}"
        if isinstance(val, bool):
            val = "Sí" if val else "No"
        if isinstance(val, (int, float)):
            return f'<c r="{ref}"><v>{val}</v></c>'
        s = _xml_escape("" if val is None else val)
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{s}</t></is></c>'
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    out.append('<row r="1">' + "".join(cell(i + 1, 1, c) for i, c in enumerate(cols)) + '</row>')
    for ri, row in enumerate(rows, start=2):
        out.append(f'<row r="{ri}">' + "".join(cell(ci + 1, ri, v) for ci, v in enumerate(row)) + '</row>')
    out.append('</sheetData></worksheet>')
    return "".join(out)


def build_xlsx(sheets):
    """sheets: lista de (nombre, cols, rows) -> bytes de un .xlsx valido."""
    names, seen = [], set()
    for name, _, _ in sheets:
        nm = re.sub(r'[\[\]:*?/\\]', " ", str(name))[:31] or "Hoja"
        base = nm
        k = 2
        while nm.lower() in seen:
            nm = f"{base[:28]}_{k}"
            k += 1
        seen.add(nm.lower())
        names.append(nm)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
              '<Default Extension="xml" ContentType="application/xml"/>',
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
        for i in range(len(sheets)):
            ct.append(f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        ct.append('</Types>')
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
        for i, nm in enumerate(names):
            wb.append(f'<sheet name="{_xml_escape(nm)}" sheetId="{i+1}" r:id="rId{i+1}"/>')
        wb.append('</sheets></workbook>')
        z.writestr("xl/workbook.xml", "".join(wb))
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for i in range(len(sheets)):
            rels.append(f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i+1}.xml"/>')
        rels.append('</Relationships>')
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        for i, (name, cols, rows) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i+1}.xml", _sheet_xml(cols, rows))
    return buf.getvalue()


# ---- Importación desde Excel/CSV -------------------------------------------
# Para cada tabla importable: lista de (etiqueta de columna, campo, tipo)
IMPORT_SPECS = {
    "clientes": [("Nombre", "nombre", "t"), ("NIF", "nif", "t"), ("Teléfono", "telefono", "t"),
                 ("Email", "email", "t"), ("Dirección", "direccion", "t"), ("Notas", "notas", "t")],
    "proveedores": [("Nombre", "nombre", "t"), ("NIF", "nif", "t"), ("Teléfono", "telefono", "t"),
                    ("Email", "email", "t"), ("Dirección", "direccion", "t"), ("Notas", "notas", "t")],
    "transportistas": [("Nombre", "nombre", "t"), ("NIF", "nif", "t"), ("Teléfono", "telefono", "t"),
                       ("Email", "email", "t"), ("Dirección", "direccion", "t"), ("Notas", "notas", "t")],
    "gestorias": [("Nombre", "nombre", "t"), ("NIF", "nif", "t"), ("Teléfono", "telefono", "t"),
                  ("Email", "email", "t"), ("Dirección", "direccion", "t"), ("Notas", "notas", "t")],
    "comerciales": [("Nombre", "nombre", "t"), ("NIF", "nif", "t"), ("Teléfono", "telefono", "t"),
                    ("Email", "email", "t"), ("Fecha incorporación", "fecha_incorporacion", "d"),
                    ("% Comisión", "comision_pct", "n"), ("Franquicia", "franquicia", "n"), ("Notas", "notas", "t")],
    "vehiculos": [("Matrícula", "matricula", "t"), ("Bastidor", "bastidor", "t"), ("Marca", "marca", "t"),
                  ("Modelo", "modelo", "t"), ("Año", "anio", "n"), ("Kilómetros", "km", "n"),
                  ("Color", "color", "t"), ("Combustible", "combustible", "t"), ("Estado", "estado", "t"),
                  ("ITV pasada", "itv_pasada", "t"), ("Caducidad ITV", "itv_expira", "d"),
                  ("Próxima revisión", "proxima_revision", "d"), ("Notas", "notas", "t")],
}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


def _archivo_a_filas(data):
    """Convierte el archivo subido (xlsx / html-xls / csv, en base64 o texto) en filas."""
    b64 = data.get("archivo_b64")
    if b64:
        try:
            raw = base64.b64decode(b64.split(",")[-1])
        except Exception:
            raise ReglaNegocio("No he podido leer el archivo subido.")
        if not raw:
            return []
        if raw[:2] == b"PK":
            return _xlsx_rows(raw)
        if raw[:4] == b"\xd0\xcf\x11\xe0":
            raise ReglaNegocio("Ese archivo es un Excel antiguo (.xls binario). Ábrelo en Excel y "
                               "guárdalo como «Libro de Excel (.xlsx)» o «CSV», y súbelo de nuevo.")
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc); break
            except Exception:
                continue
        if not text:
            return []
    else:
        text = data.get("csv") or ""
    if not text.strip():
        return []
    low = text.lower()
    if "<table" in low or "<tr" in low or "</td>" in low:
        return _html_rows(text)
    delim = ";" if text[:3000].count(";") >= text[:3000].count(",") else ","
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim)]


def importar_tabla(table, data):
    if table not in IMPORT_SPECS:
        raise ReglaNegocio("Este módulo no admite importación.")
    spec = IMPORT_SPECS[table]
    rows = _archivo_a_filas(data)
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        raise ReglaNegocio("El archivo no tiene datos. Usa la plantilla y rellena al menos una fila.")
    header = [_norm(c) for c in rows[0]]
    # localizar la columna de cada campo por su etiqueta
    label_by_field = {f: lab for lab, f, _ in spec}
    type_by_field = {f: t for _, f, t in spec}
    col = {}
    for lab, field, _t in spec:
        for j, h in enumerate(header):
            if h == _norm(lab):
                col[field] = j
                break
    if not col:
        raise ReglaNegocio("No reconozco las columnas. Descarga la plantilla y respeta la "
                           "primera fila de títulos.")
    insertados, errores = 0, []
    for i, r in enumerate(rows[1:], start=2):
        rec = {}
        for field, j in col.items():
            if j < len(r):
                val = (r[j] or "").strip() if isinstance(r[j], str) else r[j]
                if val in ("", None):
                    continue
                t = type_by_field[field]
                if t == "n":
                    v = _num_es(val) if isinstance(val, str) else val
                    if v is not None:
                        rec[field] = v
                elif t == "d":
                    rec[field] = _fecha_es(str(val))
                else:
                    rec[field] = val
        if not rec:
            continue
        # requisito mínimo: nombre / matrícula
        if table != "vehiculos" and not (rec.get("nombre") or "").strip():
            errores.append(f"Fila {i}: falta el nombre.")
            continue
        if table == "vehiculos" and not (str(rec.get("matricula") or "").strip() or str(rec.get("bastidor") or "").strip()):
            errores.append(f"Fila {i}: falta matrícula o bastidor.")
            continue
        try:
            insert_row(table, rec)
            insertados += 1
        except Exception as e:
            errores.append(f"Fila {i}: {e}")
    return {"ok": True, "insertados": insertados, "errores": errores, "total": len(rows) - 1}


def backup_zip():
    """Empaqueta la base de datos y todos los documentos en un ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB_PATH):
            z.write(DB_PATH, "vehiculos.db")
        if os.path.isdir(DOCS_DIR):
            for fn in os.listdir(DOCS_DIR):
                fp = os.path.join(DOCS_DIR, fn)
                if os.path.isfile(fp):
                    z.write(fp, "documentos_adjuntos/" + fn)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Bancos: lectura de extracto CSV y conciliacion
# --------------------------------------------------------------------------

def _num_es(s):
    s = (s or "").strip().replace("€", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-") or s.startswith("(")
    s = s.strip("()").lstrip("+-")
    if "," in s and "." in s:      # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                 # 1234,56
        s = s.replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def _fecha_es(s):
    s = (s or "").strip()
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if m:
        d, mo, y = m.groups()
        y = ("20" + y) if len(y) == 2 else y
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return s


def _movs_from_rows(rows):
    """Detecta cabecera y extrae movimientos de una lista de filas (celdas string).
    Común a CSV y Excel."""
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        return []
    header_idx = None
    for i, r in enumerate(rows[:20]):
        low = [(c or "").strip().lower() for c in r]
        if any("fecha" in c for c in low) and any(
                ("importe" in c or "concepto" in c or "descrip" in c or "cantidad" in c) for c in low):
            header_idx = i
            break
    movs = []
    if header_idx is not None:
        hdr = [(c or "").strip().lower() for c in rows[header_idx]]

        def col(*keys):
            for j, c in enumerate(hdr):
                if any(k in c for k in keys):
                    return j
            return None
        cf = col("fecha valor", "fecha oper", "fecha")
        cc = col("concepto", "descrip", "detalle", "movimiento")
        ci = col("importe", "cantidad", "cargo", "abono")
        cs = col("saldo")
        for r in rows[header_idx + 1:]:
            if ci is None or ci >= len(r):
                continue
            imp = _num_es(r[ci])
            if imp is None:
                continue
            movs.append({
                "fecha": _fecha_es(r[cf]) if cf is not None and cf < len(r) else "",
                "concepto": (r[cc] or "").strip() if cc is not None and cc < len(r) else "",
                "importe": imp,
                "saldo": _num_es(r[cs]) if cs is not None and cs < len(r) else None})
    else:
        for r in rows:                # sin cabecera: fecha, concepto, importe[, saldo]
            if len(r) < 3:
                continue
            imp = _num_es(r[2])
            if imp is None:
                continue
            movs.append({"fecha": _fecha_es(r[0]), "concepto": (r[1] or "").strip(),
                         "importe": imp, "saldo": _num_es(r[3]) if len(r) > 3 else None})
    return movs


def parse_csv_extracto(text):
    if text and text[0] == "﻿":
        text = text[1:]
    sample = text[:3000]
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return _movs_from_rows(rows)


def _col_idx(ref):
    """'AB12' -> índice de columna 0-based."""
    letters = "".join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1 if n else 0


def _excel_serial_to_iso(v):
    """Convierte el número de serie de fecha de Excel a ISO (base 1899-12-30)."""
    try:
        f = float(v)
    except (ValueError, TypeError):
        return None
    if f < 1:
        return None
    try:
        return (date(1899, 12, 30) + timedelta(days=int(f))).isoformat()
    except Exception:
        return None


def _xlsx_rows(raw):
    """Lee un .xlsx (solo librería estándar: zipfile + XML) y devuelve filas de celdas string."""
    def local(tag):
        return tag.split("}")[-1]
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = zf.namelist()

    def parse(name):
        return ET.fromstring(zf.read(name))

    # cadenas compartidas
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in parse("xl/sharedStrings.xml"):
            shared.append("".join(t.text or "" for t in si.iter() if local(t.tag) == "t"))

    # estilos que son fechas
    date_styles = set()
    if "xl/styles.xml" in names:
        sroot = parse("xl/styles.xml")
        custom_date = set()
        for el in sroot.iter():
            if local(el.tag) == "numFmt":
                fid = el.get("numFmtId")
                code = (el.get("formatCode") or "").lower()
                if fid and any(tok in code for tok in ("d", "m", "y")) and "general" not in code:
                    custom_date.add(fid)
        builtin_date = {str(i) for i in list(range(14, 23)) + list(range(45, 48))}
        cellxfs = next((el for el in sroot if local(el.tag) == "cellXfs"), None)
        if cellxfs is not None:
            for i, xf in enumerate(list(cellxfs)):
                fid = xf.get("numFmtId")
                if fid in builtin_date or fid in custom_date:
                    date_styles.add(i)

    # primera hoja según el orden del libro (con respaldo a sheet1)
    sheet_name = None
    try:
        wb = parse("xl/workbook.xml")
        rels = parse("xl/_rels/workbook.xml.rels")
        rid_to_target = {r.get("Id"): r.get("Target") for r in rels}
        first = next((el for el in wb.iter() if local(el.tag) == "sheet"), None)
        if first is not None:
            rid = next((v for k, v in first.attrib.items() if local(k) == "id"), None)
            target = rid_to_target.get(rid)
            if target:
                target = target.lstrip("/")
                sheet_name = target if target.startswith("xl/") else "xl/" + target
    except Exception:
        pass
    if not sheet_name or sheet_name not in names:
        cands = sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        if not cands:
            return []
        sheet_name = cands[0]

    rows = []
    for row in parse(sheet_name).iter():
        if local(row.tag) != "row":
            continue
        cellmap = {}
        maxc = -1
        auto = 0
        for c in row:
            if local(c.tag) != "c":
                continue
            ref = c.get("r") or ""
            ci = _col_idx(ref) if ref else auto
            auto = ci + 1
            t = c.get("t")
            s = c.get("s")
            vel = next((ch for ch in c if local(ch.tag) == "v"), None)
            isel = next((ch for ch in c if local(ch.tag) == "is"), None)
            vtext = ""
            if t == "s" and vel is not None and vel.text is not None:
                try:
                    vtext = shared[int(vel.text)]
                except (ValueError, IndexError):
                    vtext = ""
            elif t == "inlineStr" and isel is not None:
                vtext = "".join(tt.text or "" for tt in isel.iter() if local(tt.tag) == "t")
            elif t in ("str", "b") and vel is not None:
                vtext = vel.text or ""
            elif vel is not None and vel.text is not None:
                if s is not None and s.isdigit() and int(s) in date_styles:
                    vtext = _excel_serial_to_iso(vel.text) or vel.text
                else:
                    vtext = vel.text
            cellmap[ci] = vtext
            maxc = max(maxc, ci)
        rows.append([cellmap.get(i, "") for i in range(maxc + 1)])
    return rows


def parse_xlsx_extracto(raw):
    return _movs_from_rows(_xlsx_rows(raw))


def _html_rows(text):
    """Extrae filas de una tabla HTML (muchos bancos exportan .xls que en realidad es HTML)."""
    from html.parser import HTMLParser

    class _T(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.rows, self.row, self.cell = [], None, None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th"):
                self.cell = []
            elif tag == "br" and self.cell is not None:
                self.cell.append(" ")

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.cell is not None and self.row is not None:
                self.row.append(" ".join("".join(self.cell).split()))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row = None

        def handle_data(self, data):
            if self.cell is not None:
                self.cell.append(data)

    p = _T()
    p.feed(text)
    return p.rows


def parse_html_extracto(text):
    return _movs_from_rows(_html_rows(text))


def _near(f1, f2, days):
    try:
        a = date.fromisoformat((f1 or "")[:10])
        b = date.fromisoformat((f2 or "")[:10])
        return abs((a - b).days) <= days
    except Exception:
        return True   # si falta alguna fecha, no descartamos por fecha


def _obs(*parts):
    """Une trozos de texto no vacíos con espacios, sin dobles espacios ni paréntesis huecos."""
    out = " ".join(str(p).strip() for p in parts if p and str(p).strip())
    return out or ""

def conciliar_uno(conn, mov):
    """Devuelve (categoria, ref_tipo, ref_id, observacion_app) o (None,...)."""
    imp = mov["importe"]
    f = mov["fecha"]
    tol = 0.02
    if imp > 0:   # INGRESO -> cobro de venta
        for c in conn.execute(
                """SELECT c.id, c.importe, c.fecha, c.medio, v.matricula, cl.nombre AS cliente
                   FROM cobros c LEFT JOIN ventas s ON s.id=c.venta_id
                   LEFT JOIN vehiculos v ON v.id=s.vehiculo_id
                   LEFT JOIN clientes cl ON cl.id=s.cliente_id""").fetchall():
            if abs((c["importe"] or 0) - imp) < tol and _near(f, c["fecha"], 7):
                return ("Cobro de venta", "cobro", c["id"],
                        _obs("Cobro de venta", c["medio"], c["matricula"],
                             ("· " + c["cliente"]) if c["cliente"] else ""))
        for s in conn.execute(
                """SELECT s.id, s.precio, s.fecha, v.matricula, cl.nombre AS cliente
                   FROM ventas s LEFT JOIN vehiculos v ON v.id=s.vehiculo_id
                   LEFT JOIN clientes cl ON cl.id=s.cliente_id""").fetchall():
            if abs((s["precio"] or 0) - imp) < tol and _near(f, s["fecha"], 12):
                return ("Cobro de venta", "venta", s["id"],
                        _obs("Pago total de venta", s["matricula"],
                             ("· " + s["cliente"]) if s["cliente"] else ""))
    else:         # GASTO
        a = abs(imp)
        for c in conn.execute(
                """SELECT c.id, c.precio, c.gastos, c.fecha, v.matricula,
                          COALESCE(p.nombre, cl.nombre) AS prov
                   FROM compras c LEFT JOIN vehiculos v ON v.id=c.vehiculo_id
                   LEFT JOIN proveedores p ON p.id=c.prov_id
                   LEFT JOIN clientes cl ON cl.id=c.proveedor_id""").fetchall():
            tot = (c["precio"] or 0) + (c["gastos"] or 0)
            if abs(tot - a) < tol and _near(f, c["fecha"], 12):
                return ("Pago a proveedor (compra)", "compra", c["id"],
                        _obs("Compra", c["matricula"],
                             ("a " + c["prov"]) if c["prov"] else ""))
        for t in conn.execute(
                "SELECT t.id, t.coste, t.fecha, t.descripcion, v.matricula FROM taller t LEFT JOIN vehiculos v ON v.id=t.vehiculo_id").fetchall():
            if abs((t["coste"] or 0) - a) < tol and _near(f, t["fecha"], 10):
                return ("Pago de taller", "taller", t["id"],
                        f"Taller {t['matricula'] or ''}: {t['descripcion'] or ''}")
        for p in conn.execute(
                "SELECT p.id, p.coste, p.fecha, p.descripcion, v.matricula FROM postventa p LEFT JOIN vehiculos v ON v.id=p.vehiculo_id").fetchall():
            if abs((p["coste"] or 0) - a) < tol and _near(f, p["fecha"], 10):
                return ("Pago de postventa", "postventa", p["id"],
                        f"Postventa {p['matricula'] or ''}: {p['descripcion'] or ''}")
    return (None, None, None, None)


def guardar_extracto(data):
    b64 = data.get("archivo_b64")
    movs = None
    if b64:
        try:
            raw = base64.b64decode(b64.split(",")[-1])
        except Exception:
            raise ReglaNegocio("No he podido leer el archivo subido.")
        if not raw:
            raise ReglaNegocio("El archivo está vacío.")
        if raw[:2] == b"PK":                      # .xlsx / .ods (Excel moderno = zip)
            movs = parse_xlsx_extracto(raw)
        elif raw[:4] == b"\xd0\xcf\x11\xe0":      # .xls binario antiguo (OLE): no soportado
            raise ReglaNegocio(
                "Ese archivo es un Excel antiguo (.xls binario) que no puedo leer directamente. "
                "Ábrelo en Excel y usa «Guardar como» → «Libro de Excel (.xlsx)» o «CSV», y súbelo de nuevo.")
        else:                                     # texto: HTML disfrazado de .xls, o CSV
            text = None
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except Exception:
                    continue
            if text:
                low = text.lower()
                if "<table" in low or "<tr" in low or "</td>" in low:
                    movs = parse_html_extracto(text)
                else:
                    movs = parse_csv_extracto(text)
    else:
        text = data.get("csv") or ""
        if not text.strip():
            raise ReglaNegocio("El archivo está vacío.")
        movs = parse_csv_extracto(text)
    if not movs:
        raise ReglaNegocio("No he podido leer movimientos del archivo. "
                           "Necesito columnas de fecha, concepto e importe (CSV o Excel .xlsx). "
                           "Si tu banco da un .xls antiguo, ábrelo en Excel y «Guardar como» .xlsx o .csv.")
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO extractos (fecha, cuenta, nombre_archivo, notas) VALUES (?,?,?,?)",
        (data.get("fecha") or date.today().isoformat(), data.get("cuenta"),
         data.get("nombre_archivo"), data.get("notas")))
    eid = cur.lastrowid
    for m in movs:
        cat, rt, ri, obs = conciliar_uno(conn, m)
        conn.execute(
            """INSERT INTO movimientos
               (extracto_id, fecha, concepto, importe, saldo, categoria, ref_tipo, ref_id, conciliado, observacion_app)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (eid, m["fecha"], m["concepto"], m["importe"], m.get("saldo"),
             cat or "Desconocido", rt, ri, 1 if cat else 0, obs or ""))
    conn.commit()
    conn.close()
    return eid


def list_extractos(q=None):
    conn = get_db()
    rows = conn.execute(
        """SELECT e.*,
                  (SELECT COUNT(*) FROM movimientos m WHERE m.extracto_id=e.id) AS n_mov,
                  (SELECT COUNT(*) FROM movimientos m WHERE m.extracto_id=e.id AND m.conciliado=1) AS n_conc
           FROM extractos e ORDER BY e.fecha DESC, e.id DESC""").fetchall()
    conn.close()
    return rows_to_list(rows)


def list_movimientos(extracto_id=None):
    conn = get_db()
    if extracto_id:
        rows = conn.execute(
            "SELECT * FROM movimientos WHERE extracto_id=? ORDER BY fecha, id", (extracto_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM movimientos ORDER BY fecha, id").fetchall()
    conn.close()
    return rows_to_list(rows)


def _sheet_from(rows, columns):
    cols = [h for h, _ in columns]
    data = [[r.get(k) for _, k in columns] for r in rows]
    return cols, data


def informe_xlsx():
    """Genera el informe completo con una hoja por modulo."""
    sh = []

    def add(name, rows, columns):
        c, d = _sheet_from(rows, columns)
        sh.append((name, c, d))

    veh = list_vehiculos()
    add("Vehiculos", veh, [
        ("Matrícula", "matricula"), ("Marca", "marca"), ("Modelo", "modelo"),
        ("Año", "anio"), ("Km", "km"), ("Combustible", "combustible"),
        ("Color", "color"), ("Estado", "estado"), ("Almacén", "almacen_nombre"),
        ("Ubicación", "ubicacion"), ("ITV caduca", "itv_expira"),
        ("Precio compra", "precio_compra"), ("Precio venta", "precio_venta"),
        ("Ref web", "ref_web")])
    ventas = list_ventas()
    for s in ventas:
        s["margen"] = (s.get("precio") or 0) - (s.get("coste") or 0)
    add("Ventas", ventas, [
        ("Fecha", "fecha"), ("Nº factura", "numero_factura"), ("Matrícula", "matricula"),
        ("Marca", "marca"), ("Modelo", "modelo"), ("Cliente", "cliente"),
        ("NIF", "cliente_nif"), ("Régimen", "regimen"), ("Precio", "precio"),
        ("Coste", "coste"), ("Margen", "margen"), ("Financiación", "cruz_fin"),
        ("Seguro", "cruz_seg"), ("Garantía", "cruz_gar"), ("Forma pago", "forma_pago")])
    add("Compras", list_compras(), [
        ("Fecha", "fecha"), ("Nº factura", "numero_factura"), ("Matrícula", "matricula"),
        ("Marca", "marca"), ("Modelo", "modelo"), ("Proveedor", "proveedor"),
        ("Régimen", "regimen"), ("Precio", "precio"), ("Gastos", "gastos"),
        ("Forma pago", "forma_pago")])
    add("Taller", list_taller(), [
        ("Matrícula", "matricula"), ("Marca", "marca"), ("Modelo", "modelo"),
        ("Tipo", "tipo"), ("Intervención", "descripcion"), ("Proveedor", "proveedor"),
        ("NIF proveedor", "nif_proveedor"), ("Nº factura", "numero_factura"),
        ("Fecha", "fecha"), ("Coste (IVA incl.)", "coste"), ("% IVA", "iva_pct"),
        ("Pago", "pago")])
    add("Postventa", list_postventa(), [
        ("Matrícula", "matricula"), ("Marca", "marca"), ("Modelo", "modelo"),
        ("Tipo", "tipo"), ("Actuación", "descripcion"), ("Proveedor", "proveedor"),
        ("NIF proveedor", "nif_proveedor"), ("Nº factura", "numero_factura"),
        ("Fecha", "fecha"), ("Coste (IVA incl.)", "coste"), ("% IVA", "iva_pct"),
        ("Asume", "asume"), ("Pago", "pago")])
    add("Garantias", list_garantias(), [
        ("Matrícula", "matricula"), ("Marca", "marca"), ("Modelo", "modelo"),
        ("Cliente", "cliente"), ("Tipo", "tipo"), ("Inicio", "fecha_inicio"),
        ("Meses", "meses"), ("Fin", "fecha_fin"), ("Estado", "estado"),
        ("Alcance", "alcance")])
    add("Agenda postventa", list_agenda(), [
        ("Fecha", "fecha"), ("Matrícula", "matricula"), ("Marca", "marca"),
        ("Modelo", "modelo"), ("Tipo", "tipo"), ("Asunto", "asunto"),
        ("Detalle", "detalle")])
    add("Leads", list_leads(), [
        ("Matrícula", "matricula"), ("Marca", "marca"), ("Modelo", "modelo"),
        ("Contacto", "nombre"), ("Canal", "canal"), ("Teléfono", "telefono"),
        ("Fecha", "fecha"), ("Estado", "estado")])
    add("Logistica", list_logistica(), [
        ("Estado", "estado"), ("Matrícula", "matricula"), ("Marca", "marca"),
        ("Modelo", "modelo"), ("Transportista", "transportista_nombre"),
        ("Origen", "origen"), ("Destino", "destino"), ("Coste", "coste"),
        ("Recogida", "fecha_recogida"), ("Entrega", "fecha_entrega")])
    add("Gestoria", list_gestoria(), [
        ("Matrícula", "matricula"), ("Marca", "marca"), ("Modelo", "modelo"),
        ("Trámite", "tipo"), ("Estado", "estado"), ("Gestoría", "gestoria"),
        ("Solicitud", "fecha_solicitud"), ("Resolución", "fecha_resolucion")])
    stock = [v for v in veh if v.get("estado") == "disponible"]
    add("Stock por almacen", stock, [
        ("Matrícula", "matricula"), ("Marca", "marca"), ("Modelo", "modelo"),
        ("Almacén", "almacen_nombre"), ("Ubicación", "ubicacion"),
        ("Valor compra", "precio_compra")])
    add("Clientes", list_clientes(), [
        ("Nombre", "nombre"), ("NIF", "nif"), ("Teléfono", "telefono"),
        ("Email", "email"), ("Dirección", "direccion")])
    add("Proveedores", list_proveedores(), [
        ("Nombre", "nombre"), ("NIF", "nif"), ("Teléfono", "telefono"),
        ("Email", "email"), ("Dirección", "direccion")])
    add("Transportistas", list_transportistas(), [
        ("Nombre", "nombre"), ("NIF", "nif"), ("Teléfono", "telefono"),
        ("Email", "email"), ("Dirección", "direccion")])
    return build_xlsx(sh)


# --------------------------------------------------------------------------
# Servidor HTTP
# --------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"  # gestiona Expect: 100-continue y keep-alive

    def log_message(self, fmt, *args):
        pass  # silencioso

    # -- helpers de respuesta --
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        # Idempotente: consume el cuerpo una sola vez y lo cachea. Así, aunque un
        # handler responda 401/403/404 antes de leerlo, el cuerpo queda drenado y
        # la conexión keep-alive no se desincroniza.
        if hasattr(self, "_parsed_body"):
            return self._parsed_body
        te = (self.headers.get("Transfer-Encoding", "") or "").lower()
        if "chunked" in te:
            raw = self._read_chunked()
        else:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
        result = {}
        if raw:
            for enc in ("utf-8", "cp1252", "latin-1"):
                try:
                    result = json.loads(raw.decode(enc))
                    break
                except Exception:
                    continue
        self._parsed_body = result
        return result

    def _read_chunked(self):
        data = b""
        while True:
            size_line = self.rfile.readline().strip()
            try:
                size = int(size_line.split(b";")[0], 16)
            except ValueError:
                break
            if size == 0:
                self.rfile.readline()  # trailing CRLF
                break
            data += self.rfile.read(size)
            self.rfile.readline()  # CRLF tras cada chunk
        return data

    def get_cookie(self, name):
        raw = self.headers.get("Cookie", "") or ""
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith(name + "="):
                return part[len(name) + 1:]
        return None

    def current_user(self):
        tok = self.get_cookie("sid") or ""
        return SESSIONS.get(tok) or cargar_sesion_db(tok)

    def send_file(self):
        try:
            with open(INDEX_PATH, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"index.html no encontrado")

    def serve_static(self, path):
        """Sirve iconos y el manifest (para poder instalar la app en el móvil).
        Los iconos son archivos de la carpeta; para cambiarlos, reemplázalos."""
        name = path.strip("/")
        if name == "manifest.webmanifest":
            man = {"name": "MIÑACAR · Gestión 360", "short_name": "MIÑACAR",
                   "start_url": "/", "scope": "/", "display": "standalone",
                   "background_color": "#eceff2", "theme_color": "#d6e021",
                   "icons": [{"src": "/icono-180.png", "sizes": "180x180", "type": "image/png"},
                             {"src": "/icono.png", "sizes": "512x512", "type": "image/png"}]}
            body = json.dumps(man, ensure_ascii=False).encode("utf-8")
            ct = "application/manifest+json; charset=utf-8"
        else:
            mp = {"icono.svg": ("icono.svg", "image/svg+xml"),
                  "favicon.svg": ("icono.svg", "image/svg+xml"),
                  "favicon.ico": ("icono.ico", "image/x-icon"),
                  "icono.png": ("icono.png", "image/png"),
                  "icono-180.png": ("icono-180.png", "image/png"),
                  "apple-touch-icon.png": ("icono-180.png", "image/png"),
                  "apple-touch-icon-precomposed.png": ("icono-180.png", "image/png")}
            if name not in mp:
                self.send_response(404); self.end_headers(); return
            fn, ct = mp[name]
            try:
                with open(os.path.join(BASE_DIR, fn), "rb") as f:
                    body = f.read()
            except FileNotFoundError:
                self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- rutas --
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            return self.send_file()

        if path in ("/icono.svg", "/favicon.svg", "/favicon.ico", "/icono.png",
                    "/icono-180.png", "/apple-touch-icon.png",
                    "/apple-touch-icon-precomposed.png", "/manifest.webmanifest"):
            return self.serve_static(path)

        if path == "/api/me":
            u = self.current_user()
            return self.send_json({"auth": bool(u), "user": u},
                                  status=200 if u else 401)

        # A partir de aqui todo requiere sesion iniciada
        user = self.current_user()
        if not user:
            return self.send_json({"ok": False, "error": "no autenticado"}, status=401)

        if path == "/api/usuarios":
            if user["rol"] != "admin":
                return self.send_json({"ok": False, "error": "no autorizado"}, status=403)
            return self.send_json(list_usuarios())

        if path == "/api/clientes":
            return self.send_json(list_clientes(params.get("q", [None])[0]))
        if path == "/api/transportistas":
            return self.send_json(list_transportistas(params.get("q", [None])[0]))
        if path == "/api/proveedores":
            return self.send_json(list_proveedores(params.get("q", [None])[0]))
        if path == "/api/comerciales":
            return self.send_json(list_comerciales(params.get("q", [None])[0]))
        if path == "/api/garantias":
            return self.send_json(list_garantias(params.get("q", [None])[0]))
        if path == "/api/postventa":
            return self.send_json(list_postventa(params.get("q", [None])[0]))
        if path == "/api/agenda":
            return self.send_json(list_agenda(params.get("q", [None])[0]))
        if path == "/api/cobros":
            return self.send_json(list_cobros(params.get("q", [None])[0]))
        if path == "/api/seguimientos":
            return self.send_json(list_seguimientos(params.get("q", [None])[0]))
        if path == "/api/extractos":
            return self.send_json(list_extractos(params.get("q", [None])[0]))
        if path == "/api/movimientos":
            vid = params.get("extracto_id", [None])[0]
            return self.send_json(list_movimientos(int(vid) if vid else None))
        if path == "/api/vehiculos":
            return self.send_json(list_vehiculos(params.get("q", [None])[0]))
        if path == "/api/compras":
            return self.send_json(list_compras(params.get("q", [None])[0]))
        if path == "/api/ventas":
            return self.send_json(list_ventas(params.get("q", [None])[0]))
        if path == "/api/logistica":
            return self.send_json(list_logistica(params.get("q", [None])[0]))
        if path == "/api/taller":
            return self.send_json(list_taller(params.get("q", [None])[0]))
        if path == "/api/leads":
            return self.send_json(list_leads(params.get("q", [None])[0]))
        if path == "/api/gestoria":
            return self.send_json(list_gestoria(params.get("q", [None])[0]))
        if path == "/api/almacenes":
            return self.send_json(list_almacenes(params.get("q", [None])[0]))
        if path == "/api/recepciones":
            return self.send_json(list_recepciones(params.get("q", [None])[0]))
        if path == "/api/gestorias":
            return self.send_json(list_gestorias(params.get("q", [None])[0]))
        if path == "/api/traspasos":
            return self.send_json(list_traspasos(params.get("q", [None])[0]))
        if path == "/api/documentos":
            vid = params.get("vehiculo_id", [None])[0]
            return self.send_json(list_documentos(int(vid) if vid else None))
        if path == "/api/doc_tipos":
            return self.send_json(DOC_TIPOS)
        if path.startswith("/doc/"):
            return self.serve_doc(path)
        if path == "/api/listas":
            return self.send_json(list_listas(
                params.get("tipo", [None])[0], params.get("padre", [None])[0]))
        if path == "/api/itv_avisos":
            dias = int(params.get("dias", ["15"])[0] or 15)
            return self.send_json(list_itv_avisos(dias))
        if path == "/api/web_sync":
            return self.send_json(web_sync())
        if path == "/api/backup.zip":
            if user["rol"] != "admin":
                return self.send_json({"ok": False, "error": "no autorizado"}, status=403)
            data = backup_zip()
            self.send_response(200)
            self.close_connection = True
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition",
                             f'attachment; filename="copia_minacar_{date.today().isoformat()}.zip"')
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/plantilla.xlsx":
            table = params.get("table", [""])[0]
            spec = IMPORT_SPECS.get(table)
            if not spec:
                return self.send_json({"ok": False, "error": "Módulo no importable"}, status=400)
            labels = [lab for lab, _, _ in spec]
            data = build_xlsx([(f"plantilla_{table}", labels, [])])
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="plantilla_{table}.xlsx"')
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/informe.xlsx":
            data = informe_xlsx()
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", 'attachment; filename="informe_minacar.xlsx"')
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/dashboard":
            return self.send_json(dashboard(params))

        self.send_response(404)
        self.end_headers()

    def serve_doc(self, path):
        try:
            did = int(path.rstrip("/").split("/")[-1])
        except ValueError:
            self.send_response(404); self.end_headers(); return
        conn = get_db()
        row = conn.execute(
            "SELECT archivo, mime, nombre_original FROM documentos WHERE id=?",
            (did,)).fetchone()
        conn.close()
        if not row or not row["archivo"]:
            self.send_response(404); self.end_headers(); return
        fpath = os.path.join(DOCS_DIR, row["archivo"])
        if not os.path.exists(fpath):
            self.send_response(404); self.end_headers(); return
        with open(fpath, "rb") as f:
            body = f.read()
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", row["mime"] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition",
                         f'inline; filename="{row["nombre_original"] or row["archivo"]}"')
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.__dict__.pop("_parsed_body", None)   # nueva petición: no reutilizar el cuerpo cacheado
        path = urlparse(self.path).path

        if path == "/api/login":
            data = self.read_body()
            row = autenticar((data.get("username") or "").strip(), data.get("password") or "")
            if not row:
                return self.send_json({"ok": False, "error": "Usuario o contraseña incorrectos"}, status=401)
            tok = crear_sesion(row)
            body = json.dumps({"ok": True, "user": SESSIONS[tok]}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", f"sid={tok}; Path=/; HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/logout":
            _sid = self.get_cookie("sid") or ""
            SESSIONS.pop(_sid, None)
            borrar_sesion_db(_sid)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "sid=; Path=/; Max-Age=0")
            self.send_header("Content-Length", "11")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        self.read_body()   # drena/cachea el cuerpo para no desincronizar keep-alive en respuestas tempranas
        user = self.current_user()
        if not user:
            return self.send_json({"ok": False, "error": "no autenticado"}, status=401)

        # Exportar a Excel la tabla que el usuario está viendo (cualquier ventana)
        if path == "/api/tabla.xlsx":
            data = self.read_body()
            name = (data.get("name") or "datos")
            cols = data.get("cols") or []
            rows = data.get("rows") or []
            xls = build_xlsx([(name, cols, rows)])
            self.close_connection = True   # descarga puntual: cerrar evita desincronizar keep-alive en el navegador
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="minacar_{name}.xlsx"')
            self.send_header("Content-Length", str(len(xls)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(xls)
            return

        # Importar datos desde Excel/CSV a un módulo
        if path == "/api/importar":
            data = self.read_body()
            table = data.get("table")
            if table not in IMPORT_SPECS:
                return self.send_json({"ok": False, "error": "Este módulo no admite importación."}, status=400)
            if not puede_escribir(user, table):
                return self.send_json({"ok": False, "error": "No tienes permiso de edición en este módulo."}, status=403)
            try:
                res = importar_tabla(table, data)
            except ReglaNegocio as e:
                return self.send_json({"ok": False, "error": str(e)}, status=400)
            except Exception as e:
                return self.send_json({"ok": False, "error": f"Error al importar: {e}"}, status=400)
            return self.send_json(res)

        # Confirmar una proforma → factura de venta correlativa
        mconf = re.match(r"^/api/ventas/(\d+)/confirmar$", path)
        if mconf:
            if not puede_escribir(user, "ventas"):
                return self.send_json({"ok": False, "error": "No tienes permiso de edición en ventas."}, status=403)
            try:
                num = confirmar_venta(int(mconf.group(1)))
            except ReglaNegocio as e:
                return self.send_json({"ok": False, "error": str(e)}, status=400)
            except Exception as e:
                return self.send_json({"ok": False, "error": f"Error al confirmar: {e}"}, status=400)
            return self.send_json({"ok": True, "numero_factura": num})

        # Vaciar TODO el stock (borrado masivo) — solo administrador
        if path == "/api/vehiculos/vaciar":
            if user["rol"] != "admin":
                return self.send_json({"ok": False, "error": "Solo un administrador puede vaciar todo el stock."}, status=403)
            try:
                n = vaciar_stock()
            except Exception as e:
                return self.send_json({"ok": False, "error": f"Error al vaciar el stock: {e}"}, status=400)
            return self.send_json({"ok": True, "borrados": n})

        if path == "/api/usuarios":
            if user["rol"] != "admin":
                return self.send_json({"ok": False, "error": "no autorizado"}, status=403)
            data = self.read_body()
            try:
                nid = crear_usuario(data)
            except ReglaNegocio as e:
                return self.send_json({"ok": False, "error": str(e)}, status=400)
            return self.send_json({"id": nid, "ok": True})

        table = self._table_from_path()
        if table is None:
            self.send_response(404); self.end_headers(); return
        if not puede_escribir(user, table):
            return self.send_json({"ok": False, "error": "No tienes permiso de edición en este módulo (acceso de solo lectura)."}, status=403)
        data = self.read_body()
        if not data:
            return self.send_json({"ok": False, "error": "sin datos"}, status=400)
        if table == "extractos":
            try:
                eid = guardar_extracto(data)
            except ReglaNegocio as e:
                return self.send_json({"ok": False, "error": str(e)}, status=400)
            except Exception as e:
                return self.send_json({"ok": False, "error": f"Error al procesar el extracto: {e}"}, status=400)
            return self.send_json({"id": eid, "ok": True})
        if table == "documentos":
            try:
                did = guardar_documento(data)
            except ReglaNegocio as e:
                return self.send_json({"ok": False, "error": str(e)}, status=400)
            except Exception as e:
                return self.send_json({"ok": False, "error": f"Error al guardar el documento: {e}"}, status=400)
            return self.send_json({"id": did, "ok": True})
        if table == "recepciones":
            try:
                rid = registrar_recepcion(data)
            except ReglaNegocio as e:
                return self.send_json({"ok": False, "error": str(e),
                                       "puede_forzar": getattr(e, "puede_forzar", False)}, status=400)
            except Exception as e:
                return self.send_json({"ok": False, "error": f"Error al registrar la recepción: {e}"}, status=400)
            return self.send_json({"id": rid, "ok": True})
        try:
            new_id = insert_row(table, data)
        except ReglaNegocio as e:
            return self.send_json({"ok": False, "error": str(e),
                                   "puede_forzar": getattr(e, "puede_forzar", False)}, status=400)
        except sqlite3.IntegrityError:
            return self.send_json({"ok": False, "error": "Datos relacionados no válidos (revisa cliente/proveedor/vehículo seleccionado)."}, status=400)
        except Exception as e:
            return self.send_json({"ok": False, "error": f"Error al guardar: {e}"}, status=400)
        self.send_json({"id": new_id, "ok": True})

    def do_PUT(self):
        self.__dict__.pop("_parsed_body", None)   # nueva petición: no reutilizar el cuerpo cacheado
        self.read_body()   # drena/cachea el cuerpo para no desincronizar keep-alive en respuestas tempranas
        user = self.current_user()
        if not user:
            return self.send_json({"ok": False, "error": "no autenticado"}, status=401)
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[1] == "usuarios":
            if user["rol"] != "admin":
                return self.send_json({"ok": False, "error": "no autorizado"}, status=403)
            actualizar_usuario(int(parts[2]), self.read_body())
            return self.send_json({"ok": True})
        table, row_id = self._table_and_id()
        if table is None or row_id is None:
            self.send_response(404); self.end_headers(); return
        if not puede_escribir(user, table):
            return self.send_json({"ok": False, "error": "No tienes permiso de edición en este módulo (acceso de solo lectura)."}, status=403)
        data = self.read_body()
        try:
            update_row(table, row_id, data)
        except ReglaNegocio as e:
            return self.send_json({"ok": False, "error": str(e),
                                   "puede_forzar": getattr(e, "puede_forzar", False)}, status=400)
        except sqlite3.IntegrityError:
            return self.send_json({"ok": False, "error": "Datos relacionados no válidos (revisa cliente/proveedor/vehículo seleccionado)."}, status=400)
        except Exception as e:
            return self.send_json({"ok": False, "error": f"Error al guardar: {e}"}, status=400)
        self.send_json({"ok": True})

    def do_DELETE(self):
        self.__dict__.pop("_parsed_body", None)   # nueva petición: no reutilizar el cuerpo cacheado
        user = self.current_user()
        if not user:
            return self.send_json({"ok": False, "error": "no autenticado"}, status=401)
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[1] == "usuarios":
            if user["rol"] != "admin":
                return self.send_json({"ok": False, "error": "no autorizado"}, status=403)
            uid = int(parts[2])
            if uid == user["id"]:
                return self.send_json({"ok": False, "error": "No puedes eliminar tu propio usuario."}, status=400)
            conn = get_db()
            conn.execute("DELETE FROM usuarios WHERE id=?", (uid,))
            conn.commit()
            conn.close()
            return self.send_json({"ok": True})
        table, row_id = self._table_and_id()
        if table is None or row_id is None:
            self.send_response(404); self.end_headers(); return
        if not puede_escribir(user, table):
            return self.send_json({"ok": False, "error": "No tienes permiso de edición en este módulo (acceso de solo lectura)."}, status=403)
        if table == "documentos":
            borrar_documento(row_id)
        elif table == "vehiculos":
            borrar_vehiculo(row_id)
        else:
            delete_row(table, row_id)
        self.send_json({"ok": True})

    # -- helpers de ruteo --
    VALID_TABLES = {"clientes", "transportistas", "proveedores", "comerciales",
                    "vehiculos", "compras", "ventas", "logistica", "taller",
                    "leads", "gestoria", "documentos", "almacenes", "traspasos",
                    "garantias", "postventa", "agenda", "cobros",
                    "seguimientos", "extractos", "movimientos", "listas",
                    "recepciones", "gestorias"}

    def _table_from_path(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "api" and parts[1] in self.VALID_TABLES:
            return parts[1]
        return None

    def _table_and_id(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] in self.VALID_TABLES:
            try:
                return parts[1], int(parts[2])
            except ValueError:
                return None, None
        return None, None


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    init_db()
    server = ThreadingServer(("0.0.0.0", PORT), Handler)
    url = f"http://localhost:{PORT}"
    lan = _lan_ip()
    print("=" * 64)
    print("  MIÑACAR · Gestion 360")
    print(f"  En este equipo:      {url}")
    print(f"  Desde movil/red:     http://{lan}:{PORT}   (misma red WiFi)")
    print("  Acceso inicial:      usuario 'admin'  contrasena 'admin1234'")
    print("  Base de datos:       " + DB_PATH)
    print("  Para cerrar la aplicacion pulsa Ctrl+C en esta ventana.")
    print("=" * 64)
    # Abrir el navegador solo cuando se ejecuta en local (no en la nube)
    if "PORT" not in os.environ:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando...")
        server.shutdown()


if __name__ == "__main__":
    main()
