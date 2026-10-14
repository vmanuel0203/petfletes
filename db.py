"""Capa de datos SQLite para PetFletes (MVP) - roles, pines y centro de control."""
import hashlib
import json
import os
import random
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mascotas.db")

# Cuenta del administrador (centro de control). Define PETFLETES_ADMIN_PASSWORD
# antes de la primera ejecución para no usar la contraseña por defecto.
ADMIN_EMAIL = "admin@petfletes.cr"
ADMIN_PASSWORD = os.environ.get("PETFLETES_ADMIN_PASSWORD", "admin123")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    telefono TEXT,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'usuario',
    creado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tiendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    direccion TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tienda_id INTEGER NOT NULL REFERENCES tiendas(id),
    nombre TEXT NOT NULL,
    precio INTEGER NOT NULL,
    peso_kg REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS repartidores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    sinpe TEXT NOT NULL,
    vehiculo TEXT NOT NULL,
    usuario_id INTEGER
);

CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    tienda_id INTEGER NOT NULL REFERENCES tiendas(id),
    items_json TEXT NOT NULL,
    peso_total REAL NOT NULL,
    subtotal INTEGER NOT NULL,
    distancia_km REAL NOT NULL,
    tarifa_minima INTEGER NOT NULL,
    oferta INTEGER NOT NULL,
    origen_nombre TEXT,
    origen_lat REAL,
    origen_lon REAL,
    destino_nombre TEXT NOT NULL,
    destino_senas TEXT NOT NULL,
    destino_lat REAL NOT NULL,
    destino_lon REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'Buscando repartidor',
    repartidor_id INTEGER REFERENCES repartidores(id),
    creado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publicaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    contenido TEXT NOT NULL,
    creado TEXT NOT NULL
);
"""

# Columnas nuevas: se agregan automáticamente a bases de datos creadas con la versión anterior.
_MIGRACIONES = [
    ("usuarios", "rol", "TEXT NOT NULL DEFAULT 'usuario'"),
    ("repartidores", "usuario_id", "INTEGER"),
    ("pedidos", "origen_nombre", "TEXT"),
    ("pedidos", "origen_lat", "REAL"),
    ("pedidos", "origen_lon", "REAL"),
]

TIENDAS_MOCK = [
    {
        "nombre": "PetZone Escazú",
        "direccion": "Avenida Escazú, 200 m norte del Multiplaza, Escazú",
        "lat": 9.9181, "lon": -84.1400,
        "descripcion": "Alimento premium y accesorios para perros y gatos.",
        "productos": [
            ("Arena sanitaria para gatos 10 kg", 7500, 10.0),
            ("Alimento perro adulto 15 kg", 28900, 15.0),
            ("Alimento gato adulto 7.5 kg", 16500, 7.5),
            ("Snacks dentales para perro", 3200, 0.4),
            ("Collar antipulgas", 6900, 0.1),
        ],
    },
    {
        "nombre": "Mundo Mascota Heredia",
        "direccion": "Frente al Parque Central, Heredia centro",
        "lat": 9.9981, "lon": -84.1165,
        "descripcion": "Todo para tu mascota, con precios accesibles.",
        "productos": [
            ("Arena aglomerante 5 kg", 4800, 5.0),
            ("Alimento cachorro 8 kg", 17900, 8.0),
            ("Rascador para gato", 12500, 2.5),
            ("Shampoo hipoalergénico", 4500, 0.5),
            ("Juguete mordedor", 2800, 0.2),
        ],
    },
    {
        "nombre": "Huellitas Curridabat",
        "direccion": "Contiguo a Plaza del Sol, Curridabat",
        "lat": 9.9137, "lon": -84.0334,
        "descripcion": "Boutique de mascotas con productos naturales.",
        "productos": [
            ("Arena perfumada 20 kg", 13900, 20.0),
            ("Alimento premium gato 3 kg", 11200, 3.0),
            ("Cama mediana acolchada", 15000, 1.8),
            ("Pipeta antipulgas", 8400, 0.05),
            ("Comedero de acero inoxidable", 3900, 0.6),
        ],
    },
]

# Repartidores de demostración (sin cuenta): sirven para simular que un pedido es aceptado.
REPARTIDORES_MOCK = [
    ("Carlos Mora", "8801-2345", "Moto"),
    ("Daniela Vargas", "6012-3456", "Carro pequeño"),
    ("Andrés Solano", "7099-4567", "Pick-up"),
]

_SELECT_PEDIDO = """
SELECT p.*, t.nombre AS tienda_nombre, t.direccion AS tienda_direccion,
       t.lat AS tienda_lat, t.lon AS tienda_lon,
       r.nombre AS repartidor_nombre, r.sinpe AS repartidor_sinpe,
       r.vehiculo AS repartidor_vehiculo,
       u.nombre AS cliente_nombre, u.telefono AS cliente_telefono
FROM pedidos p
JOIN tiendas t ON t.id = p.tienda_id
JOIN usuarios u ON u.id = p.usuario_id
LEFT JOIN repartidores r ON r.id = p.repartidor_id
"""


@contextmanager
def conexion():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def init_db():
    """Crea tablas, migra bases antiguas y carga los datos de prueba."""
    with conexion() as conn:
        conn.executescript(SCHEMA)
        _migrar(conn)
        _sembrar(conn)


def _migrar(conn):
    for tabla, columna, definicion in _MIGRACIONES:
        columnas = [f["name"] for f in conn.execute(f"PRAGMA table_info({tabla})")]
        if columna not in columnas:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _asegurar_cuenta(conn, nombre, email, telefono, password, rol, sinpe=None, vehiculo=None):
    """Crea la cuenta si no existe (y su perfil de repartidor). Devuelve el id del usuario."""
    fila = conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
    if fila:
        return fila["id"]
    salt = secrets.token_hex(16)
    uid = conn.execute(
        "INSERT INTO usuarios (nombre, email, telefono, password_hash, salt, rol, creado) VALUES (?,?,?,?,?,?,?)",
        (nombre, email, telefono, _hash_password(password, salt), salt, rol, ahora()),
    ).lastrowid
    if rol == "repartidor":
        conn.execute(
            "INSERT INTO repartidores (nombre, sinpe, vehiculo, usuario_id) VALUES (?,?,?,?)",
            (nombre, sinpe, vehiculo, uid),
        )
    return uid


def _sembrar(conn):
    if conn.execute("SELECT COUNT(*) FROM tiendas").fetchone()[0] == 0:
        for t in TIENDAS_MOCK:
            tid = conn.execute(
                "INSERT INTO tiendas (nombre, direccion, lat, lon, descripcion) VALUES (?,?,?,?,?)",
                (t["nombre"], t["direccion"], t["lat"], t["lon"], t["descripcion"]),
            ).lastrowid
            conn.executemany(
                "INSERT INTO productos (tienda_id, nombre, precio, peso_kg) VALUES (?,?,?,?)",
                [(tid, *p) for p in t["productos"]],
            )

    if conn.execute("SELECT COUNT(*) FROM repartidores").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO repartidores (nombre, sinpe, vehiculo) VALUES (?,?,?)", REPARTIDORES_MOCK
        )

    demo_id = _asegurar_cuenta(conn, "Usuario Demo", "demo@petfletes.cr", "8888-0000", "demo123", "usuario")
    _asegurar_cuenta(conn, "Repartidor Demo", "repartidor@petfletes.cr", "8777-1111", "demo123",
                     "repartidor", sinpe="8777-1111", vehiculo="Moto")
    _asegurar_cuenta(conn, "Administrador", ADMIN_EMAIL, "", ADMIN_PASSWORD, "admin")

    if conn.execute("SELECT COUNT(*) FROM publicaciones").fetchone()[0] == 0:
        ahora_dt = datetime.now()
        posts = [
            ("Oferta de tienda", "2x1 en snacks dentales en PetZone Escazú",
             "Este fin de semana llevá 2 snacks dentales por el precio de 1. ¡Hasta agotar existencias!",
             ahora_dt - timedelta(hours=26)),
            ("Tip de mascotas", "¿Cada cuánto cambiar la arena?",
             "Retirá los residuos a diario y cambiá toda la arena aglomerante cada 2 a 3 semanas.",
             ahora_dt - timedelta(hours=5)),
            ("Pregunta", "¿Recomiendan alimento para gato esterilizado?",
             "Mi gata acaba de ser esterilizada y busco un alimento con control de peso. ¡Gracias!",
             ahora_dt - timedelta(hours=1)),
        ]
        conn.executemany(
            "INSERT INTO publicaciones (usuario_id, tipo, titulo, contenido, creado) VALUES (?,?,?,?,?)",
            [(demo_id, tipo, titulo, cont, dt.strftime("%Y-%m-%d %H:%M:%S"))
             for tipo, titulo, cont, dt in posts],
        )


# ---------------------------------------------------------------- Usuarios
def _normalizar_sinpe(numero):
    digitos = "".join(c for c in numero if c.isdigit())
    if len(digitos) != 8:
        raise ValueError("El número de SINPE Móvil debe tener 8 dígitos.")
    return f"{digitos[:4]}-{digitos[4:]}"


def _usuario_dict(conn, fila):
    rep = conn.execute("SELECT id FROM repartidores WHERE usuario_id = ?", (fila["id"],)).fetchone()
    return {"id": fila["id"], "nombre": fila["nombre"], "email": fila["email"],
            "telefono": fila["telefono"], "rol": fila["rol"],
            "repartidor_id": rep["id"] if rep else None}


def crear_usuario(nombre, email, telefono, password, rol="usuario", sinpe="", vehiculo=""):
    """Registra un usuario o repartidor. Lanza ValueError si los datos no son válidos."""
    nombre, email, telefono = nombre.strip(), email.strip().lower(), telefono.strip()
    if rol not in ("usuario", "repartidor"):
        raise ValueError("Tipo de cuenta no válido.")
    if not nombre or "@" not in email:
        raise ValueError("Ingresa un nombre y un correo válido.")
    if len(password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")
    if rol == "repartidor":
        sinpe = _normalizar_sinpe(sinpe)
        vehiculo = vehiculo.strip()
        if not vehiculo:
            raise ValueError("Indica tu tipo de vehículo.")
    salt = secrets.token_hex(16)
    try:
        with conexion() as conn:
            uid = conn.execute(
                "INSERT INTO usuarios (nombre, email, telefono, password_hash, salt, rol, creado) VALUES (?,?,?,?,?,?,?)",
                (nombre, email, telefono, _hash_password(password, salt), salt, rol, ahora()),
            ).lastrowid
            rid = None
            if rol == "repartidor":
                rid = conn.execute(
                    "INSERT INTO repartidores (nombre, sinpe, vehiculo, usuario_id) VALUES (?,?,?,?)",
                    (nombre, sinpe, vehiculo, uid),
                ).lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("Ese correo ya está registrado.")
    return {"id": uid, "nombre": nombre, "email": email, "telefono": telefono,
            "rol": rol, "repartidor_id": rid}


def autenticar(email, password):
    """Devuelve el usuario (dict con su rol) si las credenciales son correctas; si no, None."""
    with conexion() as conn:
        fila = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),)).fetchone()
        if fila is None:
            return None
        if not secrets.compare_digest(_hash_password(password, fila["salt"]), fila["password_hash"]):
            return None
        return _usuario_dict(conn, fila)


# ------------------------------------------------------ Tiendas y productos
def listar_tiendas():
    with conexion() as conn:
        return [dict(f) for f in conn.execute("SELECT * FROM tiendas ORDER BY nombre")]


def obtener_tienda(tienda_id):
    with conexion() as conn:
        fila = conn.execute("SELECT * FROM tiendas WHERE id = ?", (tienda_id,)).fetchone()
    return dict(fila) if fila else None


def listar_productos(tienda_id):
    with conexion() as conn:
        return [dict(f) for f in conn.execute(
            "SELECT * FROM productos WHERE tienda_id = ? ORDER BY nombre", (tienda_id,))]


# ----------------------------------------------------------------- Pedidos
def _pedido_dict(fila):
    p = dict(fila)
    if p.get("origen_lat") is None:  # pedidos antiguos: el origen era la tienda
        p["origen_lat"], p["origen_lon"] = p["tienda_lat"], p["tienda_lon"]
    if not p.get("origen_nombre"):
        p["origen_nombre"] = p["tienda_nombre"]
    p["items"] = json.loads(p["items_json"])
    return p


def _consultar_pedidos(where="", params=()):
    with conexion() as conn:
        filas = conn.execute(f"{_SELECT_PEDIDO} {where}", params).fetchall()
    return [_pedido_dict(f) for f in filas]


def crear_pedido(usuario_id, tienda_id, items, peso_total, subtotal, distancia_km, tarifa_minima,
                 oferta, origen_nombre, origen_lat, origen_lon,
                 destino_nombre, destino_senas, destino_lat, destino_lon):
    """Guarda un pedido nuevo en estado 'Buscando repartidor' y devuelve su id."""
    with conexion() as conn:
        return conn.execute(
            """INSERT INTO pedidos (usuario_id, tienda_id, items_json, peso_total, subtotal,
               distancia_km, tarifa_minima, oferta, origen_nombre, origen_lat, origen_lon,
               destino_nombre, destino_senas, destino_lat, destino_lon, estado, creado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (usuario_id, tienda_id, json.dumps(items, ensure_ascii=False), peso_total, subtotal,
             distancia_km, tarifa_minima, oferta, origen_nombre, origen_lat, origen_lon,
             destino_nombre, destino_senas, destino_lat, destino_lon,
             "Buscando repartidor", ahora()),
        ).lastrowid


def listar_pedidos_usuario(usuario_id):
    return _consultar_pedidos("WHERE p.usuario_id = ? ORDER BY p.id DESC", (usuario_id,))


def obtener_pedido(pedido_id, usuario_id):
    pedidos = _consultar_pedidos("WHERE p.id = ? AND p.usuario_id = ?", (pedido_id, usuario_id))
    return pedidos[0] if pedidos else None


def listar_pedidos_disponibles():
    """Pedidos que aún no tienen repartidor (para el panel del repartidor)."""
    return _consultar_pedidos("WHERE p.estado = 'Buscando repartidor' ORDER BY p.id DESC")


def listar_entregas_repartidor(repartidor_id):
    return _consultar_pedidos("WHERE p.repartidor_id = ? ORDER BY p.id DESC", (repartidor_id,))


def aceptar_pedido(pedido_id, repartidor_id):
    """Un repartidor toma el pedido. Devuelve False si otro ya lo tomó."""
    with conexion() as conn:
        cur = conn.execute(
            "UPDATE pedidos SET estado = 'Aceptado', repartidor_id = ? WHERE id = ? AND estado = 'Buscando repartidor'",
            (repartidor_id, pedido_id),
        )
        return cur.rowcount == 1


def asignar_repartidor_simulado(pedido_id):
    """Modo demo: simula que un repartidor (de demostración) acepta el pedido."""
    with conexion() as conn:
        ids = [f["id"] for f in conn.execute("SELECT id FROM repartidores WHERE usuario_id IS NULL")]
        if not ids:
            ids = [f["id"] for f in conn.execute("SELECT id FROM repartidores")]
        conn.execute(
            "UPDATE pedidos SET estado = 'Aceptado', repartidor_id = ? WHERE id = ? AND estado = 'Buscando repartidor'",
            (random.choice(ids), pedido_id),
        )


def actualizar_estado(pedido_id, usuario_id, estado):
    with conexion() as conn:
        conn.execute("UPDATE pedidos SET estado = ? WHERE id = ? AND usuario_id = ?",
                     (estado, pedido_id, usuario_id))


def actualizar_estado_repartidor(pedido_id, repartidor_id, estado):
    with conexion() as conn:
        conn.execute("UPDATE pedidos SET estado = ? WHERE id = ? AND repartidor_id = ?",
                     (estado, pedido_id, repartidor_id))


# --------------------------------------------------------- Centro de control
def estadisticas_admin():
    with conexion() as conn:
        def contar(sql):
            return conn.execute(sql).fetchone()[0]
        return {
            "buscando": contar("SELECT COUNT(*) FROM pedidos WHERE estado = 'Buscando repartidor'"),
            "aceptados": contar("SELECT COUNT(*) FROM pedidos WHERE estado = 'Aceptado'"),
            "entregados": contar("SELECT COUNT(*) FROM pedidos WHERE estado = 'Entregado'"),
            "usuarios": contar("SELECT COUNT(*) FROM usuarios WHERE rol = 'usuario'"),
            "repartidores": contar("SELECT COUNT(*) FROM repartidores"),
        }


def listar_pedidos_admin(solo_en_curso=True):
    where = "WHERE p.estado IN ('Buscando repartidor', 'Aceptado') " if solo_en_curso else ""
    return _consultar_pedidos(where + "ORDER BY p.id DESC")


def listar_repartidores_admin():
    with conexion() as conn:
        return [dict(f) for f in conn.execute(
            """SELECT r.id, r.nombre, u.email, u.telefono, r.sinpe, r.vehiculo,
                      CASE WHEN r.usuario_id IS NULL THEN 'Demo' ELSE 'Registrado' END AS tipo,
                      u.creado AS registrado,
                      (SELECT COUNT(*) FROM pedidos p WHERE p.repartidor_id = r.id AND p.estado = 'Aceptado') AS en_curso,
                      (SELECT COUNT(*) FROM pedidos p WHERE p.repartidor_id = r.id AND p.estado = 'Entregado') AS entregas
               FROM repartidores r LEFT JOIN usuarios u ON u.id = r.usuario_id
               ORDER BY r.id DESC""")]


def listar_usuarios_admin():
    with conexion() as conn:
        return [dict(f) for f in conn.execute(
            """SELECT u.id, u.nombre, u.email, u.telefono, u.creado AS registrado,
                      (SELECT COUNT(*) FROM pedidos p WHERE p.usuario_id = u.id) AS pedidos
               FROM usuarios u WHERE u.rol = 'usuario' ORDER BY u.id DESC""")]


# --------------------------------------------------------------- Comunidad
def crear_publicacion(usuario_id, tipo, titulo, contenido):
    with conexion() as conn:
        conn.execute(
            "INSERT INTO publicaciones (usuario_id, tipo, titulo, contenido, creado) VALUES (?,?,?,?,?)",
            (usuario_id, tipo, titulo.strip(), contenido.strip(), ahora()),
        )


def listar_publicaciones(tipo=None):
    """Publicaciones ordenadas de la más reciente a la más antigua."""
    consulta = """SELECT p.*, u.nombre AS autor FROM publicaciones p
                  JOIN usuarios u ON u.id = p.usuario_id"""
    params = ()
    if tipo:
        consulta += " WHERE p.tipo = ?"
        params = (tipo,)
    consulta += " ORDER BY p.creado DESC, p.id DESC"
    with conexion() as conn:
        return [dict(f) for f in conn.execute(consulta, params)]


if __name__ == "__main__":
    init_db()
    print(f"Base de datos lista en: {DB_PATH}")
