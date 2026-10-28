"""Datos iniciales. Se cargan una sola vez, al crear la base de datos.

Catálogo de cubos de GESE CUBES. Usuarios demo: ver README.
"""
import os
from datetime import datetime, timedelta, timezone

from core.seguridad import hashear_contrasena

IVA = 0.16


def _hace(dias):
    return (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")


VAR = '{"Base": ["Stickerless", "Negro"], "Versión": ["Estándar", "Magnético"]}'
# codigo, categoría, marca, nombre, descripción, precio, anterior, etiqueta, destacada,
# fotos, stock, mínimo, ubicación, costo, proveedor, variantes
PRODUCTOS = [
    ("CB-001", "3x3", "GAN", "GAN 11 M Pro 3x3", "Cubo de competencia con núcleo magnético ajustable", 1450, None, "Nuevo", 0,
     ("3x3-stickerless", "3x3-clasico"), 12, 4, "A-01", 900, "Cubos MX", VAR),
    ("CB-002", "3x3", "MoYu", "MoYu RS3 M 3x3", "El favorito para empezar a bajar de 30 segundos", 320, None, "Más vendido", 1,
     ("3x3-clasico", "mapa"), 25, 8, "A-02", 170, "Cubos MX", VAR),
    ("CB-003", "3x3", "QiYi", "QiYi Pastel Curvo 3x3", "Caras curvas en colores pastel, giro suave", 280, None, None, 0,
     ("3x3-pastel", "3x3-stickerless"), 18, 6, "A-03", 140, "Cubos MX", VAR),
    ("CB-004", "3x3", "QiYi", "QiYi Mapa Mundial 3x3", "Edición coleccionista con mapa en las seis caras", 390, None, None, 0,
     ("mapa", "3x3-clasico"), 9, 4, "A-04", 210, "Cubos MX", None),
    ("CB-005", "3x3", "MoYu", "MoYu Bloque Misterio 3x3", "Edición de colección con diseño de bloque", 360, None, None, 0,
     ("mario", "3x3-clasico"), 0, 4, "A-05", 190, "Cubos MX", None),
    ("CB-006", "3x3", "QiYi", "QiYi Hamburguesa 3x3", "Cubo de novedad con relieve de hamburguesa", 520, 620, "Oferta", 1,
     ("hamburguesa", "mario"), 4, 3, "A-06", 280, "Cubos MX", None),
    ("CB-007", "2x2", "MoYu", "MoYu 2x2 Clásico", "El primer paso hacia el cubo 3x3", 180, None, None, 0,
     ("2x2", "3x3-clasico"), 30, 10, "B-01", 85, "Cubos MX", VAR),
    ("CB-008", "5x5+", "GAN", "GAN 13x13 Mega", "Para quien ya lo resolvió todo: 13 capas", 1890, None, "Colección", 0,
     ("gigante", "3x3-clasico"), 3, 2, "C-01", 1200, "Cubos MX", None),
    ("CB-009", "Otras formas", "QiYi", "QiYi Pyraminx", "Pirámide de cuatro colores, giro rápido", 240, None, None, 0,
     ("pyraminx", "estrella-azul"), 15, 5, "D-01", 120, "Cubos MX", VAR),
    ("CB-010", "Otras formas", "GAN", "GAN Megaminx Gema", "Dodecaedro de 12 caras, ideal para velocidad", 620, None, None, 0,
     ("megaminx-gema", "megaminx-fusion"), 10, 4, "D-02", 340, "Cubos MX", VAR),
    ("CB-011", "Otras formas", "MoYu", "MoYu Teraminx", "Megaminx de gran tamaño, solo para expertos", 1650, None, "Nuevo", 0,
     ("teraminx", "megaminx-gema"), 2, 2, "D-03", 980, "Cubos MX", None),
    ("CB-012", "Otras formas", "QiYi", "QiYi Skewb", "Cuatro ejes, seis colores, cero esquinas fáciles", 210, None, None, 0,
     ("skewb", "megaminx-fusion"), 14, 5, "D-04", 100, "Cubos MX", VAR),
    ("CB-013", "Otras formas", "MoYu", "MoYu Estrella Octaedro", "Rompecabezas estrellado de 24 piezas", 340, None, None, 0,
     ("estrella-azul", "estrella-multi"), 7, 3, "D-05", 170, "Cubos MX", None),
    ("CB-014", "Otras formas", "QiYi", "QiYi Estrella Cruz", "Variante estrellada con piezas en cruz", 360, None, None, 0,
     ("estrella-multi", "estrella-azul"), 6, 3, "D-06", 180, "Cubos MX", None),
    ("CB-015", "Otras formas", "GAN", "GAN Hexágono", "Prisma hexagonal con cortes cruzados", 480, None, None, 0,
     ("hexagono", "romboide"), 5, 3, "D-07", 250, "Cubos MX", None),
    ("CB-016", "Otras formas", "QiYi", "QiYi Poliedro", "Poliedro de colores con giros profundos", 410, None, None, 0,
     ("poliedro", "tri-verde"), 8, 3, "D-08", 210, "Cubos MX", None),
]


def cargar(c):
    ahora = _hace(0)

    # Catálogo / inventario -------------------------------------------------
    for nombre in ("1x1", "2x2", "3x3", "4x4", "5x5+", "Otras formas"):
        c.execute("INSERT INTO categorias(nombre) VALUES (?)", (nombre,))
    c.execute("INSERT INTO proveedores(nombre) VALUES ('Cubos MX')")
    c.execute("INSERT INTO unidades_medida(nombre) VALUES ('Pieza')")

    for (cod, cat, marca, nom, desc, precio, ant, etq, dest, fotos, stock, minimo, ubic, costo, prov, var) in PRODUCTOS:
        pid = c.execute(
            """INSERT INTO productos(codigo, categoria_id, proveedor_id, unidad_id, nombre, marca, variantes,
                 descripcion, precio, precio_anterior, precio_compra, etiqueta, etiqueta_destacada,
                 stock, stock_minimo, ubicacion, fecha_registro, actualizado)
               VALUES (?, (SELECT id FROM categorias WHERE nombre = ?),
                       (SELECT id FROM proveedores WHERE nombre = ?), 1,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cod, cat, prov, nom, marca, var or "{}", desc, precio, ant, costo, etq, dest, stock, minimo, ubic,
             ahora, ahora),
        ).lastrowid
        for orden, f in enumerate(fotos):
            c.execute(
                "INSERT INTO fotos_producto(producto_id, ruta, texto_alternativo, orden) VALUES (?, ?, ?, ?)",
                (pid, f"/img/cubos/{f}.jpg", nom, orden),
            )
    c.execute("INSERT INTO configuracion(clave, valor) VALUES ('portada', '/img/cubos/3x3-clasico.jpg')")

    # Usuarios demo -----------------------------------------------------------
    c.execute(
        "INSERT INTO usuarios(nombre, apellidos, email, password_hash, rol, fecha_registro) VALUES (?,?,?,?,?,?)",
        ("Administrador", "GESE Cubes", "admin@gesecubes.mx",
         hashear_contrasena(os.getenv("ADMIN_PASSWORD", "Admin123!")), "admin", ahora),
    )
    c.execute(
        "INSERT INTO usuarios(nombre, apellidos, email, password_hash, rol, fecha_registro) VALUES (?,?,?,?,?,?)",
        ("Ana", "López", "ana@correo.com",
         hashear_contrasena(os.getenv("DEMO_CUSTOMER_PASSWORD", "Cliente123!")), "cliente", ahora),
    )
    c.execute(
        "INSERT INTO perfiles(usuario_id, telefono, actualizado) VALUES (2, '+52 669 111 2233', ?)", (ahora,)
    )
    c.execute(
        """INSERT INTO direcciones(usuario_id, calle, numero, colonia, ciudad, estado, codigo_postal,
             referencia, fecha_creacion) VALUES (2, 'Av. Obregón', '120', 'Centro', 'Los Mochis',
             'Sinaloa', '81200', 'Portón verde', ?)""",
        (ahora,),
    )

    # Pedidos demo (equivalentes a los pedidos 1001-1003 de Seguimiento) ------
    demos = [
        (1001, 2, "Ana López", "ana@correo.com", "+52 669 111 2233", 3, "PAGADO", "TARJETA",
         [("CB-002", "MoYu RS3 M 3x3", 2, 320), ("CB-007", "MoYu 2x2 Clásico", 1, 180)]),
        (1002, 2, "Ana López", "ana@correo.com", "+52 669 111 2233", 10, "ENVIADO", "TARJETA",
         [("CB-010", "GAN Megaminx Gema", 1, 620)]),
        (1003, None, "Daniel López", "daniel.lopez@correo.com", "+52 669 777 8899", 45, "ENTREGADO",
         "TRANSFERENCIA", [("CB-009", "QiYi Pyraminx", 1, 240)]),
    ]
    for pid, uid, nom, mail, tel, dias, estado, metodo, items in demos:
        sub = round(sum(q * p for _, _, q, p in items), 2)
        iva = round(sub * IVA, 2)
        c.execute(
            """INSERT INTO pedidos(id, usuario_id, cliente_nombre, cliente_email, cliente_telefono,
                 fecha, estado, subtotal, impuestos, total, direccion_id, metodo_pago)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, uid, nom, mail, tel, _hace(dias), estado, sub, iva, round(sub + iva, 2),
             1 if uid else None, metodo),
        )
        for sku, nombre, q, p in items:
            c.execute(
                "INSERT INTO pedido_items(pedido_id, sku, nombre, cantidad, precio_unitario) VALUES (?,?,?,?,?)",
                (pid, sku, nombre, q, p),
            )
        c.execute(
            "INSERT INTO pedido_eventos(pedido_id, estado, detalle, fecha) VALUES (?, 'CREADO', 'Pedido recibido', ?)",
            (pid, _hace(dias)),
        )
        c.execute(
            "INSERT INTO pedido_eventos(pedido_id, estado, detalle, fecha) VALUES (?, 'PAGADO', 'Pago confirmado', ?)",
            (pid, _hace(dias)),
        )
        c.execute(
            "INSERT INTO pagos(pedido_id, monto, moneda, estado, referencia, metodo, fecha) VALUES (?,?,?,?,?,?,?)",
            (pid, round(sub + iva, 2), "mxn", "succeeded", f"DEMO-{pid}", metodo, _hace(dias)),
        )
    # Envío del pedido 1002 y entrega del 1003
    for pid, estado, guia, ent in ((1002, "EN_TRANSITO", "GC10020001MX", None), (1003, "ENTREGADO", "GC10030001MX", _hace(40))):
        c.execute(
            "INSERT INTO packing(pedido_id, tipo_empaque, peso, fecha_empaque) VALUES (?, 'Caja de cartón', 1.5, ?)",
            (pid, _hace(9)),
        )
        c.execute(
            "INSERT INTO envios(pedido_id, paqueteria, guia, estado, direccion_id, fecha_envio, fecha_entrega) VALUES (?,?,?,?,?,?,?)",
            (pid, "Estafeta", guia, estado, 1 if pid == 1002 else None, _hace(9), ent),
        )
    c.execute("INSERT INTO pedido_eventos(pedido_id, estado, detalle, fecha) VALUES (1002, 'ENVIADO', 'Entregado a Estafeta', ?)", (_hace(9),))
    c.execute("INSERT INTO pedido_eventos(pedido_id, estado, detalle, fecha) VALUES (1003, 'ENTREGADO', 'Entregado al cliente', ?)", (_hace(40),))
