"""Prueba de punta a punta: compra completa, operación de almacén, devolución y reembolso.

    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import time
import unittest

# Entorno aislado y reembolsos instantáneos, antes de importar la aplicación.
_dir = tempfile.mkdtemp()
os.environ["SOA_DB"] = os.path.join(_dir, "prueba.db")
os.environ["SECRET_KEY"] = "clave-solo-para-pruebas"
os.environ["TASA_FALLA"] = "0"
os.environ["REEMBOLSO_LATENCIA_MS"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

app = create_app()


def esperar(fn, intentos=60):
    for _ in range(intentos):
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    return None


class Flujo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anon = app.test_client()
        cls.admin = app.test_client()
        cls.cli = app.test_client()
        r = cls.admin.post("/api/autenticacion/iniciar-sesion",
                           json={"correo": "admin@gesecubes.mx", "contrasena": "Admin123!"})
        assert r.status_code == 200, r.json

    # ------------------------------------------------- registro y sesión ----
    def test_01_registro_y_sesion(self):
        r = self.anon.post("/api/registro", json={"nombre": "Luis"})
        self.assertEqual(r.status_code, 400)
        r = self.anon.post("/api/registro", json={"nombre": "Luis", "email": "luis@correo.com", "password": "Segura123"})
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("password", str(r.json))
        r = self.anon.post("/api/registro", json={"nombre": "Luis", "email": "luis@correo.com", "password": "Segura123"})
        self.assertEqual(r.status_code, 409)

        self.assertEqual(self.anon.get("/api/autenticacion/validar-sesion").status_code, 401)
        r = self.anon.post("/api/autenticacion/iniciar-sesion", json={"correo": "luis@correo.com", "contrasena": "mala"})
        self.assertEqual(r.status_code, 401)
        r = self.anon.post("/api/autenticacion/iniciar-sesion", json={"correo": "luis@correo.com", "contrasena": "Segura123"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("HttpOnly", r.headers["Set-Cookie"])
        self.assertEqual(self.anon.get("/api/autenticacion/validar-sesion").json["datos"]["nombres"], "Luis")
        self.anon.post("/api/autenticacion/cerrar-sesion")
        self.assertEqual(self.anon.get("/api/autenticacion/validar-sesion").status_code, 401)

    def test_02_validacion_login(self):
        r = self.anon.post("/api/autenticacion/iniciar-sesion", json={"correo": "no-es-correo"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("contrasena", r.json["mensaje"])

    # ------------------------------------------------ catálogo y detalle ----
    def test_03_catalogo_y_detalle(self):
        cat = self.anon.get("/api/catalogo").json
        self.assertEqual(len(cat["productos"]), 16)
        self.assertEqual(cat["portada"], "/img/cubos/3x3-clasico.jpg")
        d = self.anon.get("/api/detalle-productos/1").json["producto"]
        self.assertEqual(d["proveedor"], "Cubos MX")
        self.assertEqual(self.anon.get("/api/detalle-productos/999").status_code, 404)

    def test_03b_privacidad(self):
        self.assertEqual(self.anon.get("/api/direcciones?usuarioId=2").status_code, 401)
        self.assertEqual(self.anon.post("/api/carritos?clienteId=2").status_code, 401)
        ana = app.test_client()
        ana.post("/api/autenticacion/iniciar-sesion", json={"correo": "ana@correo.com", "contrasena": "Cliente123!"})
        self.assertEqual(len(ana.get("/api/direcciones").json), 1)
        otro = app.test_client()
        otro.post("/api/registro", json={"nombre": "Pepe", "email": "pepe@correo.com", "password": "Segura123"})
        otro.post("/api/autenticacion/iniciar-sesion", json={"correo": "pepe@correo.com", "contrasena": "Segura123"})
        self.assertEqual(otro.get("/api/direcciones?usuarioId=2").json, [], "no ve direcciones ajenas")
        self.assertEqual(otro.get("/api/direcciones/1").status_code, 404)
        self.assertEqual(otro.put("/api/direcciones/1", json={"usuarioId": 2, "calle": "x", "ciudad": "y", "estado": "z"}).status_code, 404)
        self.assertEqual(otro.post("/api/direcciones", json={"usuarioId": 2, "calle": "x", "ciudad": "y", "estado": "z"}).status_code, 403)
        self.assertEqual(otro.post("/api/carritos?clienteId=2").status_code, 403)
        c = ana.post("/api/carritos?clienteId=2").json["id"]
        self.assertEqual(otro.get(f"/api/carritos/{c}").status_code, 404)
        self.assertEqual(otro.delete(f"/api/carritos/{c}/items").status_code, 404)

    # ----------------------------------------- permisos de operación ----
    def test_04_permisos(self):
        self.assertEqual(self.anon.post("/api/inventarios/movimientos", json={}).status_code, 401)
        self.cli.post("/api/registro", json={"nombre": "Marta", "email": "marta@correo.com", "password": "Segura123"})
        self.cli.post("/api/autenticacion/iniciar-sesion", json={"correo": "marta@correo.com", "contrasena": "Segura123"})
        self.assertEqual(self.cli.get("/api/picking/pedidos").status_code, 403)
        self.assertEqual(self.cli.get("/api/pedidos").status_code, 403)

    # ----------------------------------------------------- compra completa ----
    def test_05_compra_y_entrega_completa(self):
        cli, admin = self.cli, self.admin
        cli.post("/api/autenticacion/iniciar-sesion", json={"correo": "marta@correo.com", "contrasena": "Segura123"})
        uid = cli.get("/api/autenticacion/validar-sesion").json["datos"]["id"]

        # Perfil, dirección, facturación y tarjeta
        self.assertEqual(cli.put("/api/perfil", json={"nombre": "Marta", "telefono": "6691234567"}).json["telefono"], "6691234567")
        r = cli.post("/api/direcciones", json={"usuarioId": uid, "calle": "Reforma", "numero": "5", "ciudad": "Culiacán", "estado": "Sinaloa", "codigoPostal": "80000"})
        self.assertEqual(r.status_code, 200)
        dir_id = r.json["id"]
        self.assertEqual(cli.post("/api/direcciones", json={"usuarioId": uid, "calle": "", "ciudad": "x", "estado": "y"}).status_code, 400)
        self.assertEqual(cli.post("/api/datos-facturacion", json={"rfc": "MALRFC", "razonSocial": "X", "codigoPostal": "80000"}).status_code, 400)
        r = cli.post("/api/datos-facturacion", json={"rfc": "XAXX010101000", "razonSocial": "Marta Pérez", "codigoPostal": "80000", "regimenFiscal": "612"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(cli.post("/api/metodos-pago", json={"numero": "1234 5678 9012 3456", "titular": "M", "venceMes": 1, "venceAnio": 2099}).status_code, 400)
        r = cli.post("/api/metodos-pago", json={"numero": "4242 4242 4242 4242", "titular": "Marta Pérez", "venceMes": 12, "venceAnio": 2099})
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("4242424242424242", str(r.json))
        tarjeta_ok = r.json["id"]
        r = cli.post("/api/metodos-pago", json={"numero": "4000 0000 0000 0002", "titular": "Marta", "venceMes": 12, "venceAnio": 2099})
        tarjeta_mala = r.json["id"]

        # Carrito
        carrito = cli.post(f"/api/carritos?clienteId={uid}").json["id"]
        r = cli.post(f"/api/carritos/{carrito}/items", json={"productoId": 2, "cantidad": 2, "precioUnitario": 0.01})
        self.assertEqual(r.json["items"][0]["precioUnitario"], 320.0, "el precio sale del catálogo, no del cliente")
        r = cli.post(f"/api/carritos/{carrito}/items", json={"productoId": 2, "cantidad": 1})
        self.assertEqual(r.json["items"][0]["cantidad"], 3)
        self.assertEqual(cli.post(f"/api/carritos/{carrito}/items", json={"productoId": 2, "cantidad": 0}).status_code, 400)
        self.assertEqual(cli.post(f"/api/carritos/{carrito}/items", json={"productoId": 7, "cantidad": 99}).status_code, 409)
        r = cli.put(f"/api/carritos/{carrito}/items/2", json=2)  # cuerpo entero, como el servicio original
        self.assertEqual(r.json["subtotal"], 640.0)
        self.assertEqual(r.json["total"], 742.4)
        stock_antes = self.anon.get("/api/detalle-productos/2").json["producto"]["stock"]

        # Pedido desde el carrito
        r = cli.post("/api/pedidos/desde-carrito", json={"carritoId": carrito, "direccionId": dir_id})
        self.assertEqual(r.status_code, 201, r.json)
        pid = r.json["id"]
        self.assertEqual(r.json["total"], 742.4)
        self.assertEqual(self.anon.get("/api/detalle-productos/2").json["producto"]["stock"], stock_antes - 2)
        self.assertEqual(cli.get(f"/api/carritos/{carrito}").json["estado"], "Confirmado")

        # Pago: tarjeta rechazada, luego aprobada
        r = cli.post("/api/procesamiento-pagos/pagar", json={"pedidoId": pid, "metodoPagoId": tarjeta_mala})
        self.assertEqual(r.status_code, 402)
        r = cli.post("/api/procesamiento-pagos/pagar", json={"pedidoId": pid, "metodoPagoId": tarjeta_ok})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(cli.post("/api/procesamiento-pagos/pagar", json={"pedidoId": pid, "metodoPagoId": tarjeta_ok}).status_code, 409)
        self.assertEqual(cli.get(f"/api/seguimiento-pedidos/pedidos/{pid}").json["estado"], "En preparación")

        # Factura
        r = cli.post("/api/facturacion", json={"pedidoId": pid})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json["total"], 742.4)
        self.assertEqual(cli.post("/api/facturacion", json={"pedidoId": pid}).status_code, 409)

        # Picking
        lista = admin.get("/api/picking/pedidos").json
        self.assertIn(pid, [p["id"] for p in lista])
        self.assertEqual(admin.post(f"/api/picking/pedidos/{pid}/recogidas", json={"sku": "CB-002", "cantidad": 5}).status_code, 400)
        self.assertEqual(admin.post(f"/api/picking/pedidos/{pid}/recogidas", json={"sku": "NOEXISTE", "cantidad": 1}).status_code, 404)
        self.assertEqual(admin.post(f"/api/picking/pedidos/{pid}/recogidas", json={"sku": "CB-002", "cantidad": "1"}).status_code, 422)
        self.assertEqual(admin.post(f"/api/lista-empaque", json={"pedidoId": pid}).status_code, 409, "aún sin picking completo")
        r = admin.post(f"/api/picking/pedidos/{pid}/recogidas", json={"sku": "CB-002", "cantidad": 1})
        self.assertEqual(r.json["estado"], "EN_PROCESO")
        r = admin.post(f"/api/picking/pedidos/{pid}/recogidas", json={"sku": "CB-002", "cantidad": 1})
        self.assertEqual(r.json["estado"], "COMPLETADO")

        # Lista de empaque, packing y envío
        self.assertEqual(admin.post("/api/packing", json={"pedidoId": pid, "tipoEmpaque": "Caja", "peso": 2}).status_code, 409, "falta lista de empaque")
        r = admin.post("/api/lista-empaque", json={"pedidoId": pid})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json["totalPiezas"], 2)
        self.assertEqual(admin.post("/api/packing", json={"pedidoId": pid}).status_code, 400)
        r = admin.post("/api/packing", json={"pedidoId": pid, "tipoEmpaque": "Caja de cartón", "peso": 1.8, "observaciones": "Frágil"})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json["packing"]["listoParaEnvio"])
        r = admin.post("/api/envios", json={"pedidoId": pid, "paqueteria": "Estafeta"})
        self.assertEqual(r.status_code, 201, r.json)
        envio = r.json["id"]
        self.assertEqual(cli.get(f"/api/seguimiento-pedidos/pedidos/{pid}").json["estado"], "En camino")
        self.assertEqual(admin.put(f"/api/envios/{envio}/estado", json={"estado": "ENTREGADO"}).status_code, 200)
        seg = cli.get(f"/api/seguimiento-pedidos/pedidos/{pid}").json
        self.assertEqual(seg["estado"], "Entregado")
        self.assertTrue(len(seg["historial"]) >= 7)

        # Devolución -> inspección -> reembolso
        self.assertEqual(cli.post("/api/devoluciones", json={"pedidoId": pid, "sku": "CB-002", "cantidad": 5, "motivo": "NO_COINCIDE"}).status_code, 409)
        self.assertEqual(cli.post("/api/devoluciones", json={"pedidoId": pid, "sku": "CB-002", "cantidad": 1, "motivo": "ME_ABURRI"}).status_code, 400)
        r = cli.post("/api/devoluciones", json={"pedidoId": pid, "sku": "CB-002", "cantidad": 1, "motivo": "NO_COINCIDE", "comentario": "Color distinto"})
        self.assertEqual(r.status_code, 201, r.json)
        dev = r.json["id"]
        self.assertEqual(admin.post("/api/inspeccion-devoluciones", json={"devolucionId": dev, "resultado": "APTO"}).status_code, 409, "debe estar aprobada")
        self.assertEqual(cli.put(f"/api/devoluciones/{dev}/resolucion", json={"aprobar": True}).status_code, 403)
        self.assertEqual(admin.put(f"/api/devoluciones/{dev}/resolucion", json={"aprobar": True}).json["estado"], "APROBADA")
        stock_previo = self.anon.get("/api/detalle-productos/2").json["producto"]["stock"]
        r = admin.post("/api/inspeccion-devoluciones", json={"devolucionId": dev, "resultado": "APTO", "observaciones": "Sin daños"})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json["reembolso"]["monto"], 371.2)
        self.assertEqual(self.anon.get("/api/detalle-productos/2").json["producto"]["stock"], stock_previo + 1, "la pieza regresó al inventario")

        ree = r.json["reembolso"]["id"]
        completado = esperar(lambda: cli.get(f"/api/reembolsos/{ree}").json["estado"] == "COMPLETADO")
        self.assertTrue(completado, "el reembolso debe completarse")
        self.assertEqual(cli.get(f"/api/devoluciones/{dev}").json["estado"], "CERRADA")

        # Notificaciones del cliente (las que muestra el Toast)
        notifs = cli.get("/api/notificaciones").json
        asuntos = [n["asunto"] for n in notifs]
        self.assertTrue(any("Pago confirmado" in a for a in asuntos))
        self.assertTrue(any("completado" in a for a in asuntos))
        self.assertTrue(all(n["canal"] == "APP" for n in notifs))
        self.assertGreater(cli.post("/api/notificaciones/marcar-leidas").json["marcadas"], 0)

        # Historial
        h = cli.get("/api/historial-pedidos").json
        self.assertEqual(h[0]["id"], pid)
        self.assertEqual(h[0]["factura"][:2], "F-")
        dia = h[0]["fecha"][:10]
        filtrado = cli.get(f"/api/historial-pedidos?desde={dia}&hasta={dia}").json
        self.assertTrue(any(p["id"] == pid for p in filtrado))
        self.assertEqual(cli.get("/api/historial-pedidos?desde=2026-02-30").status_code, 400)
        self.assertEqual(cli.get("/api/historial-pedidos?desde=2026-10-27&hasta=2026-10-26").status_code, 400)

    # ---------------------------------------------------- stock y pedidos ----
    def test_06_stock_insuficiente_y_verificar(self):
        r = self.anon.post("/api/pedidos/verificar", json={"items": [{"sku": "CB-011", "qty": 50}]})
        self.assertFalse(r.json["ok"])
        self.assertEqual(r.json["lineas"][0]["faltante"], 48)
        self.assertEqual(self.anon.post("/api/pedidos/verificar", json={"items": []}).status_code, 400)
        self.assertEqual(self.anon.post("/api/pedidos/verificar", json={"items": [{"sku": "ZZZ", "qty": 1}]}).status_code, 404)
        c = app.test_client()
        c.post("/api/autenticacion/iniciar-sesion", json={"correo": "ana@correo.com", "contrasena": "Cliente123!"})
        r = c.post("/api/pedidos", json={"items": [{"sku": "CB-011", "qty": 50}]})
        self.assertEqual(r.status_code, 409)
        self.assertIn("lineas", r.json)
        self.assertEqual(self.anon.get("/api/detalle-productos/11").json["producto"]["stock"], 2, "no se descontó nada")

    # ------------------------------------------------------- inventarios ----
    def test_07_inventarios(self):
        a = self.admin
        self.assertEqual(a.get("/api/inventarios/resumen").json["totalProducts"], 16)
        r = a.post("/api/inventarios/movimientos", json={"productId": "CB-008", "type": "venta", "quantity": 99})
        self.assertEqual(r.status_code, 409)
        r = a.post("/api/inventarios/movimientos", json={"productId": "CB-008", "type": "compra", "quantity": 5})
        self.assertEqual(r.json["result"], 8)
        self.assertEqual(a.post("/api/inventarios/productos", json={"id": "cb-099", "name": "Nuevo", "stock": 1, "min": 1}).status_code, 201)
        self.assertEqual(a.post("/api/inventarios/productos", json={"id": "CB-099", "name": "Nuevo", "stock": 1, "min": 1}).status_code, 409)
        self.assertEqual(a.delete("/api/inventarios/productos/CB-099").status_code, 204)

    # ------------------------------------------------------ reembolsos ----
    def test_08_reglas_de_reembolso(self):
        a = self.admin
        # Pedido demo 1003: entregado hace 45 días -> fuera de la ventana de 30 días
        r = a.post("/api/reembolsos", json={"pedidoId": 1003, "motivo": "NO_COINCIDE"})
        self.assertEqual(r.status_code, 202)
        rid = r.json["id"]
        fin = esperar(lambda: a.get(f"/api/reembolsos/{rid}").json["estado"] == "RECHAZADO")
        self.assertTrue(fin)
        self.assertIn("Fuera de la ventana", a.get(f"/api/reembolsos/{rid}").json["historial"][-1]["detalle"])
        # Pedido sin pago
        self.assertEqual(a.post("/api/reembolsos", json={"pedidoId": 99999}).status_code, 404)

    def test_09_servicios_no_listados(self):
        self.assertEqual(self.anon.get("/api/servicios").status_code, 404)
        self.assertEqual(self.anon.get("/api/salud").json, {"estado": "ok"})

    # ------------------------------------------- checkout, avisos y admin ----
    def test_10_checkout_invitado(self):
        a = self.anon
        self.assertEqual(a.get("/api/checkout/cotizar-envio?cp=81200&subtotal=500").json["costo"], 79)
        self.assertEqual(a.get("/api/checkout/cotizar-envio?cp=81200&subtotal=801").json["costo"], 0)
        self.assertEqual(a.get("/api/checkout/cotizar-envio?cp=12").status_code, 400)
        envio = {"nombre": "Invitado Uno", "email": "inv@correo.com", "calle": "Calle 1", "ciudad": "Mochis",
                 "estado": "Sinaloa", "codigoPostal": "81200"}
        base = {"items": [{"sku": "CB-007", "qty": 2, "variante": {"Base": "Negro", "Versión": "Estándar"}}], "envio": envio}
        stock = lambda: self.admin.get("/api/detalle-productos/7").json["producto"]["stock"]
        antes = stock()
        r = a.post("/api/checkout/pedido", json={**base, "metodo": "stripe", "tarjeta": {"numero": "4000 0000 0000 0002", "cvc": "123"}})
        self.assertEqual(r.status_code, 402)
        self.assertEqual(stock(), antes, "tarjeta rechazada no toca el inventario")
        self.assertEqual(a.post("/api/checkout/pedido", json={**base, "items": [{"sku": "CB-007", "qty": 1, "variante": {"Base": "Rojo"}}],
                                                              "metodo": "oxxo"}).status_code, 400)
        r = a.post("/api/checkout/pedido", json={**base, "metodo": "stripe", "tarjeta": {"numero": "4242 4242 4242 4242", "cvc": "123"}})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json["pedido"]["estado"], "PAGADO")
        self.assertEqual(r.json["pedido"]["costo_envio"], 79)
        self.assertEqual(r.json["pedido"]["items"][0]["variante"], "Base: Negro · Versión: Estándar")
        self.assertEqual(stock(), antes - 2)
        pid = r.json["pedido"]["id"]
        self.assertEqual(a.get(f"/api/checkout/pedido/{pid}?email=otro@correo.com").status_code, 404)
        self.assertEqual(a.get(f"/api/checkout/pedido/{pid}?email=inv@correo.com").status_code, 200)
        r = a.post("/api/checkout/pedido", json={**base, "metodo": "oxxo"})
        self.assertEqual(len(r.json["oxxo"]["referencia"]), 14)
        self.assertEqual(r.json["pedido"]["estado"], "CREADO")
        self.assertEqual(a.post(f"/api/checkout/oxxo/{r.json['pedido']['id']}/confirmar").status_code, 401)
        self.assertEqual(self.admin.post(f"/api/checkout/oxxo/{r.json['pedido']['id']}/confirmar").status_code, 200)
        r = a.post("/api/checkout/pedido", json={**base, "metodo": "mercadopago", "crearCuenta": {"password": "Segura123"}})
        self.assertTrue(r.json["cuentaCreada"])

    def test_11_aviso_de_stock_y_panel(self):
        a, adm = self.anon, self.admin
        self.assertEqual(a.post("/api/catalogo/avisos-stock", json={"productoId": 1, "email": "x@correo.com"}).status_code, 409, "hay stock")
        self.assertEqual(a.post("/api/catalogo/avisos-stock", json={"productoId": 5, "email": "malo"}).status_code, 400)
        self.assertEqual(a.post("/api/catalogo/avisos-stock", json={"productoId": 5, "email": "x@correo.com"}).status_code, 201)
        self.assertEqual(a.put("/api/inventarios/productos/CB-005", json={"price": 1}).status_code, 401)
        r = adm.put("/api/inventarios/productos/CB-005", json={"price": 399, "stock": 6, "fotos": ["/img/cubos/mario.jpg"]})
        self.assertEqual(r.status_code, 200, r.json)
        avisos = [n for n in adm.get("/api/notificaciones").json if n["destinatario"] == "x@correo.com"]
        self.assertEqual(len(avisos), 1, "al reabastecer se avisa por correo")
        self.assertEqual(adm.put("/api/inventarios/productos/CB-005", json={"fotos": ["javascript:x"]}).status_code, 400)
        self.assertIn("pendientes", adm.get("/api/inventarios/ventas-hoy").json)
        csv = adm.get("/api/inventarios/pendientes.csv")
        self.assertIn("text/csv", csv.mimetype)
        self.assertEqual(a.get("/api/inventarios/pendientes.csv").status_code, 401)


if __name__ == "__main__":
    unittest.main()
