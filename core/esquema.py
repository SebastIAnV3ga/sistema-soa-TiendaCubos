"""Esquema de la base de datos (SQLite). Un bloque por servicio."""

ESQUEMA = """
-- 1/2/3. Usuarios, autenticación y perfil -------------------------------
CREATE TABLE IF NOT EXISTS usuarios(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  apellidos TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  rol TEXT NOT NULL DEFAULT 'cliente',
  fecha_registro TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS perfiles(
  usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
  telefono TEXT NOT NULL DEFAULT '',
  fecha_nacimiento TEXT NOT NULL DEFAULT '',
  preferencias TEXT NOT NULL DEFAULT '',
  actualizado TEXT NOT NULL
);

-- 4/5/15. Catálogo, detalle e inventario (un único maestro de productos) --
CREATE TABLE IF NOT EXISTS categorias(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS proveedores(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS unidades_medida(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS productos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT NOT NULL UNIQUE,              -- SKU / id de inventario
  categoria_id INTEGER NOT NULL REFERENCES categorias(id),
  proveedor_id INTEGER REFERENCES proveedores(id),
  unidad_id INTEGER REFERENCES unidades_medida(id),
  nombre TEXT NOT NULL,
  descripcion TEXT NOT NULL DEFAULT '',
  precio REAL NOT NULL CHECK (precio >= 0),
  precio_anterior REAL,
  precio_compra REAL NOT NULL DEFAULT 0,
  marca TEXT NOT NULL DEFAULT '',
  variantes TEXT NOT NULL DEFAULT '{}',   -- JSON {"Base": ["Stickerless", "Negro"]}
  etiqueta TEXT,
  etiqueta_destacada INTEGER NOT NULL DEFAULT 0,
  activo INTEGER NOT NULL DEFAULT 1,
  stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
  ubicacion TEXT NOT NULL DEFAULT '',
  fecha_registro TEXT NOT NULL,
  actualizado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fotos_producto(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
  ruta TEXT NOT NULL,
  texto_alternativo TEXT NOT NULL DEFAULT '',
  orden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS configuracion(
  clave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS avisos_stock(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  fecha TEXT NOT NULL,
  notificado INTEGER NOT NULL DEFAULT 0,
  UNIQUE (producto_id, email)
);
CREATE TABLE IF NOT EXISTS movimientos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  producto_id INTEGER REFERENCES productos(id) ON DELETE SET NULL,
  producto_nombre TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('compra','venta','devolucion')),
  cantidad INTEGER NOT NULL CHECK (cantidad > 0),
  stock_despues INTEGER NOT NULL CHECK (stock_despues >= 0),
  referencia TEXT NOT NULL DEFAULT '',
  fecha TEXT NOT NULL
);

-- 6. Carrito -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carritos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL,
  estado TEXT NOT NULL DEFAULT 'Activo'
);
CREATE TABLE IF NOT EXISTS carrito_items(
  carrito_id INTEGER NOT NULL REFERENCES carritos(id) ON DELETE CASCADE,
  producto_id INTEGER NOT NULL,
  nombre_producto TEXT NOT NULL,
  precio_unitario REAL NOT NULL,
  cantidad INTEGER NOT NULL,
  PRIMARY KEY (carrito_id, producto_id)
);

-- 7. Direcciones de envío, 8. datos de facturación, 9. métodos de pago ----
CREATE TABLE IF NOT EXISTS direcciones(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL,
  calle TEXT NOT NULL,
  numero TEXT, colonia TEXT,
  ciudad TEXT NOT NULL,
  estado TEXT NOT NULL,
  codigo_postal TEXT, referencia TEXT,
  fecha_creacion TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS datos_facturacion(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL,
  rfc TEXT NOT NULL,
  razon_social TEXT NOT NULL,
  regimen_fiscal TEXT NOT NULL DEFAULT '',
  codigo_postal TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  uso_cfdi TEXT NOT NULL DEFAULT 'G03',
  predeterminado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS metodos_pago(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL,
  marca TEXT NOT NULL,
  ultimos4 TEXT NOT NULL,
  titular TEXT NOT NULL,
  vence_mes INTEGER NOT NULL,
  vence_anio INTEGER NOT NULL,
  predeterminado INTEGER NOT NULL DEFAULT 0,
  creado TEXT NOT NULL
);

-- 10/11/12/13. Pedidos, pagos, historial y seguimiento -------------------
CREATE TABLE IF NOT EXISTS pedidos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER,
  cliente_nombre TEXT NOT NULL DEFAULT '',
  cliente_email TEXT NOT NULL DEFAULT '',
  cliente_telefono TEXT NOT NULL DEFAULT '',
  fecha TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'CREADO',
  subtotal REAL NOT NULL DEFAULT 0,
  impuestos REAL NOT NULL DEFAULT 0,
  total REAL NOT NULL DEFAULT 0,
  direccion_id INTEGER,
  metodo_pago TEXT NOT NULL DEFAULT '',
  reembolsado REAL NOT NULL DEFAULT 0,
  costo_envio REAL NOT NULL DEFAULT 0,
  envio_json TEXT NOT NULL DEFAULT ''     -- destino del invitado (sin cuenta)
);
CREATE TABLE IF NOT EXISTS pedido_items(
  pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
  sku TEXT NOT NULL,
  nombre TEXT NOT NULL,
  cantidad INTEGER NOT NULL,
  precio_unitario REAL NOT NULL DEFAULT 0,
  variante TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pedido_eventos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
  estado TEXT NOT NULL,
  detalle TEXT NOT NULL DEFAULT '',
  fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pagos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL,
  monto REAL NOT NULL,
  moneda TEXT NOT NULL DEFAULT 'mxn',
  estado TEXT NOT NULL,
  referencia TEXT NOT NULL DEFAULT '',
  metodo TEXT NOT NULL DEFAULT '',
  fecha TEXT NOT NULL
);

-- 14. Facturación ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS facturas(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  folio TEXT NOT NULL UNIQUE,
  pedido_id INTEGER NOT NULL UNIQUE,
  usuario_id INTEGER,
  rfc TEXT NOT NULL,
  razon_social TEXT NOT NULL,
  regimen_fiscal TEXT NOT NULL DEFAULT '',
  codigo_postal TEXT NOT NULL,
  uso_cfdi TEXT NOT NULL DEFAULT 'G03',
  subtotal REAL NOT NULL,
  iva REAL NOT NULL,
  total REAL NOT NULL,
  estado TEXT NOT NULL DEFAULT 'EMITIDA',
  fecha TEXT NOT NULL
);

-- 16/17/18/19. Lista de empaque, picking, packing y envíos ---------------
CREATE TABLE IF NOT EXISTS picking_items(
  pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
  sku TEXT NOT NULL,
  nombre TEXT NOT NULL,
  ubicacion TEXT NOT NULL DEFAULT '',
  cantidad_solicitada INTEGER NOT NULL,
  cantidad_recogida INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (pedido_id, sku)
);
CREATE TABLE IF NOT EXISTS listas_empaque(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  folio TEXT NOT NULL UNIQUE,
  pedido_id INTEGER NOT NULL UNIQUE,
  fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS packing(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL UNIQUE,
  tipo_empaque TEXT NOT NULL,
  peso REAL NOT NULL,
  observaciones TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL DEFAULT 'EMPACADO',
  listo_para_envio INTEGER NOT NULL DEFAULT 1,
  fecha_empaque TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS envios(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL UNIQUE,
  paqueteria TEXT NOT NULL,
  guia TEXT NOT NULL UNIQUE,
  estado TEXT NOT NULL,
  direccion_id INTEGER,
  fecha_envio TEXT NOT NULL,
  fecha_entrega TEXT
);

-- 20. Notificaciones --------------------------------------------------------
CREATE TABLE IF NOT EXISTS notificaciones(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER,
  evento TEXT NOT NULL,
  referencia TEXT NOT NULL DEFAULT '',
  canal TEXT NOT NULL,
  destinatario TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL DEFAULT 'info',
  asunto TEXT NOT NULL,
  mensaje TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'ENVIADA',
  leida INTEGER NOT NULL DEFAULT 0,
  fecha TEXT NOT NULL
);

-- 21/22/23. Devoluciones, inspección y reembolsos --------------------------
CREATE TABLE IF NOT EXISTS devoluciones(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL,
  usuario_id INTEGER,
  sku TEXT NOT NULL,
  nombre TEXT NOT NULL,
  cantidad INTEGER NOT NULL,
  motivo TEXT NOT NULL,
  comentario TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL DEFAULT 'SOLICITADA',
  reembolso_id TEXT,
  creado TEXT NOT NULL,
  actualizado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inspecciones(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  devolucion_id INTEGER NOT NULL UNIQUE REFERENCES devoluciones(id),
  resultado TEXT NOT NULL,
  observaciones TEXT NOT NULL DEFAULT '',
  inspector TEXT NOT NULL DEFAULT '',
  fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reembolsos(
  id TEXT PRIMARY KEY,
  pedido_id INTEGER NOT NULL,
  cliente_id INTEGER,
  monto REAL NOT NULL,
  metodo_pago TEXT NOT NULL,
  motivo TEXT NOT NULL,
  comentario TEXT NOT NULL DEFAULT '',
  estado TEXT,
  transaccion_id TEXT,
  intentos INTEGER NOT NULL DEFAULT 0,
  creado TEXT NOT NULL,
  actualizado TEXT,
  historial TEXT NOT NULL DEFAULT '[]',
  forzar_falla INTEGER NOT NULL DEFAULT 0,
  devolucion_id INTEGER
);
"""
