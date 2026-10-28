"""Registro de los servicios del sistema."""
from servicios import (autenticacion, carrito, catalogo, checkout, datos_facturacion, detalle_productos, devoluciones,
                       direcciones, envios, facturacion, historial_pedidos, inspeccion_devoluciones,
                       inventarios, lista_empaque, metodos_pago, notificaciones, packing, pedidos, perfil,
                       picking, procesamiento_pagos, reembolsos, registro, seguimiento_pedidos)

# (n.º, nombre, módulo, responsable del servicio original o None si es nuevo)
SERVICIOS = [
    (1, "Registro de Usuarios", registro, "Jesús"),
    (2, "Autenticación", autenticacion, "Aldo"),
    (3, "Gestión de Perfil", perfil, None),
    (4, "Catálogo de Productos", catalogo, "Marcela"),
    (5, "Detalle de Productos", detalle_productos, "Jesús Cervantes"),
    (6, "Carrito de Compras", carrito, "Yuriana"),
    (7, "Direcciones de Envío", direcciones, "Osmar"),
    (8, "Datos de Facturación", datos_facturacion, None),
    (9, "Métodos de Pago", metodos_pago, None),
    (10, "Procesamiento de Pagos", procesamiento_pagos, "Eric"),
    (11, "Gestión de Pedidos", pedidos, "Elidor"),
    (12, "Historial de Pedidos", historial_pedidos, "SebastianLopezVega · servicio-historial-pedidos"),
    (13, "Seguimiento de Pedidos", seguimiento_pedidos, "Rebecca"),
    (14, "Facturación", facturacion, None),
    (15, "Gestión de Inventarios", inventarios, "Eduardo"),
    (16, "Lista de Empaque", lista_empaque, None),
    (17, "Picking", picking, "Evelyn"),
    (18, "Packing", packing, "Irasema"),
    (19, "Gestión de Envíos", envios, None),
    (20, "Notificaciones", notificaciones, "Jorge Ernesto"),
    (21, "Gestión de Devoluciones", devoluciones, None),
    (22, "Inspección de Devoluciones", inspeccion_devoluciones, None),
    (23, "Reembolsos", reembolsos, "Alan Zavala"),
    (24, "Checkout (invitado y pasarelas)", checkout, None),
]


def registrar(app):
    for _n, _nombre, modulo, _autor in SERVICIOS:
        app.register_blueprint(modulo.bp)
