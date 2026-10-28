# GESE CUBES · Tienda en línea de cubos Rubik (sistema SOA en Python)

Sistema completo con los **24 servicios** del proyecto, unificado en **Python (Flask)** con un solo diseño.
Los 14 servicios que ya existían en GitHub se portaron a Python conservando su lógica, rutas, validaciones y
mensajes; los 9 que faltaban se crearon desde cero con las mismas convenciones.

## Cómo ejecutarlo

Requiere Python 3.10 o superior.

```bash
pip install -r requirements.txt     # solo instala Flask
python app.py                       # abre http://127.0.0.1:5001
```

En Windows: doble clic a `iniciar.bat`. Las pruebas automáticas: `python -m unittest discover -s tests -v`.

**Usuarios de demostración** (se crean la primera vez; cámbialos antes de publicar el sistema):

| Rol | Correo | Contraseña |
|---|---|---|
| Cliente | `ana@correo.com` | `Cliente123!` |
| Administrador | `admin@gesecubes.mx` | `Admin123!` |

La base de datos (SQLite) se crea sola en `datos/sistema.db`. Para empezar de cero, borra la carpeta `datos/`.

## Módulos de la tienda

Los módulos internos se integran en `servicios/` y no se muestran en una lista enumerada en el portal.
El historial de pedidos está integrado con las compras de la tienda; permite buscar por número o producto,
filtrar por estado y consultar pedidos entre fechas. Está basado en el
[repositorio de Historial de Pedidos](https://github.com/SebastIAnV3ga/servicio-historial-pedidos).

## Flujo de negocio

```
Catálogo (filtros y búsqueda) → Ficha con variantes → Carrito → Checkout (con o sin cuenta; Stripe, Mercado Pago u OXXO)
   → o bien Registro → Login → Catálogo/Detalle → Carrito → Pedido (descuenta inventario) → Pago → Factura
   → Picking → Lista de empaque → Packing → Envío → Entrega
   → Devolución → Inspección → Reembolso → Notificaciones (toast en el portal)
```

Cada hito del pedido deja un evento (Seguimiento/Historial) y avisa al cliente mediante Notificaciones.

## Estructura

```
app.py                 Aplicación Flask: registra los servicios y sirve el portal
core/                  Base de datos, esquema, datos de ejemplo, seguridad (JWT/hash), utilidades y bus de eventos
servicios/             Un módulo por servicio
static/                Portal web (diseño unificado): index.html, css/, js/, img/
tests/test_flujo.py    Prueba de punta a punta (9 pruebas)
```

## Qué cambió respecto a los repositorios originales

Se pidió convertir todo a Python y cambiar solo el diseño. La **lógica de negocio, rutas, validaciones y mensajes se
mantuvieron**; lo que sí tuvo que cambiar para que los 23 servicios funcionen juntos:

- **Una sola base de datos SQLite** reemplaza SQL Server, las listas en memoria y las bases SQLite separadas. Hay **un único maestro de productos**: el SKU de Pedidos/Inventarios es el `codigo` del catálogo, y el stock se descuenta en un solo lugar. Los datos de ejemplo se sustituyeron por el catálogo de cubos de GESE CUBES.
- **Un solo proceso** en lugar de 14 servidores en puertos distintos (varios usaban el mismo puerto 3000). Los servicios se llaman entre sí como módulos Python, no por HTTP. Si más adelante quieres separarlos, cada `Blueprint` puede moverse a su propia app.
- **Autenticación** usa el servicio de Registro como «tienda» de usuarios (antes consultaba una URL externa). Conserva los verificadores `texto`, `bcrypt`, `sha256`, `sha512` y añade `scrypt` (por defecto; no requiere paquetes extra). El JWT HS256 se implementa con la biblioteca estándar.
- **Registro**: la contraseña ahora requiere al menos 8 caracteres y el correo se valida.
- **Carrito**: el nombre y el precio de cada artículo salen del catálogo, no de lo que envíe el cliente (evita manipular precios); también se valida el stock.
- **Pagos**: funciona con Stripe si defines `STRIPE_SECRET_KEY` (y `pip install stripe`); sin llaves usa un modo simulado (las tarjetas terminadas en `0002` se rechazan). Se añadió `POST /pagar`, que cobra un pedido del sistema.
- **Seguimiento, Picking y Packing** leen los pedidos reales en vez de datos fijos de ejemplo.
- **Reembolsos**: mismas reglas (30 días, aprobación manual desde \$20,000, 10 % de falla simulada de la pasarela, reintentos). Los eventos viajan por un bus interno y Notificaciones los atiende como antes. La transmisión en vivo (SSE) de la interfaz original se sustituyó por consulta periódica.
- **Notificaciones**: el componente Toast se conserva sin cambios de lógica (`static/js/notify.js`); solo se quitó su página de demostración. Ahora también hay un servicio que guarda los avisos por usuario.
- **Permisos**: las rutas de operación (picking, packing, envíos, inventario, resolución de devoluciones, reembolsos) requieren rol administrador; los datos de un cliente (pedidos, direcciones, carrito, tarjetas, facturas) solo los ve ese cliente. Direcciones y Carrito eran abiertos en los repositorios originales; ahora exigen sesión.
- El navegador necesita JavaScript para el portal (y para el Toast); el servidor es 100 % Python.

## Rediseño GESE CUBES (según ANGELITA_RUBIK_FINAL.pdf)

- **Diseño** de escritorio con fondo oscuro y los seis colores del cubo como acentos (`static/css/estilo.css`).
- **Catálogo**: filtros laterales fijos (categoría, marca, precio, solo disponibles) y buscador con autocompletado; todo actualiza la rejilla al instante en el navegador.
- **Ficha**: galería, selector de variantes (Base: Stickerless/Negro, Versión: Estándar/Magnético).
- **Agotados**: etiqueta, botón desactivado y aviso por correo (`POST /api/catalogo/avisos-stock`); al reabastecer se registra una notificación EMAIL.
- **Checkout** a dos columnas, compra como invitado y cuenta opcional al final. Envío por C.P. (`GET /api/checkout/cotizar-envio`), gratis con subtotal mayor a $800.
- **Pagos**: Stripe, Mercado Pago y ficha OXXO en **modo de pruebas simulado**: tarjeta 4242… aprueba, 4000 0000 0000 0002 rechaza. Con OXXO el administrador confirma el pago desde el Panel.
- **Panel de administración**: ventas del día, pedidos abiertos, tabla completa de productos (alta, baja, precio, existencias, fotos), descarga CSV de pendientes y lista de empaque imprimible.
- Las tarifas de envío son una tabla por zona de C.P. (origen Los Mochis), no una API real de paquetería; los avisos por correo se guardan como notificaciones, no hay SMTP.
- El catálogo de ejemplo no incluye fotos de 1x1 ni 4x4: esas categorías aparecen vacías hasta que se den de alta modelos.

## Variables de entorno (opcionales)

| Variable | Para qué |
|---|---|
| `PORT`, `HOST` | Puerto y dirección (por defecto 5001 y 127.0.0.1) |
| `SECRET_KEY` | Clave para firmar sesiones (si no, se genera una y se guarda en `datos/secret.key`) |
| `MODO_CONTRASENA` | `scrypt` (defecto), `bcrypt`, `sha256`, `sha512`, `texto` |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` | Cobros reales con Stripe |
| `TASA_FALLA`, `REEMBOLSO_LATENCIA_MS` | Simulación de la pasarela de reembolsos |
| `SOA_DB` | Ruta alternativa de la base de datos |

## Antes de publicarlo en internet

Está listo para desarrollo y demostración. Para producción: cambia las contraseñas demo, usa HTTPS (y `secure=True` en la cookie de sesión), un servidor como `waitress` o `gunicorn`, y sustituye los métodos de pago simulados por Stripe real.


## Mejoras de esta versión

- Las imágenes del catálogo permanecen fijas al pasar el cursor: se desactivó el cambio a la segunda foto y el zoom por hover.
- La sección **Mis pedidos** muestra un resumen de compras, permite buscar por número de pedido/producto/guía/factura y filtrar por estado.
- El servicio 12 (**Historial de Pedidos**) queda identificado con el repositorio de origen de SebastianLopezVega y continúa protegido por sesión: cada cliente consulta únicamente sus pedidos; el administrador puede consultar todos o filtrar por usuario.
