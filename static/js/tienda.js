'use strict'
/* Tienda: catálogo con filtros laterales, ficha de producto, carrito y checkout (con o sin cuenta). */

// ------------------------------------------------------------- carrito ----
// El carrito vive en el navegador para que también funcione sin cuenta; el servidor
// recalcula precios y stock al crear el pedido (/api/checkout/pedido).
const LLAVE_CARRITO = 'gc:carrito'
function carritoLocal() {
  try { const c = JSON.parse(localStorage.getItem(LLAVE_CARRITO)); return Array.isArray(c) ? c : [] } catch { return [] }
}
function guardarCarrito(c) { try { localStorage.setItem(LLAVE_CARRITO, JSON.stringify(c)) } catch { /* sin almacenamiento */ } }
const claveLinea = (sku, v) => sku + '|' + JSON.stringify(v || {})
const etiquetaVariante = (v) => Object.entries(v || {}).map(([k, x]) => `${k}: ${x}`).join(' · ')
const productoPorSku = (sku) => estado.catalogo?.productos.find((p) => p.codigo === sku)
const subtotalCarrito = (c) => c.reduce((a, l) => a + l.precio * l.qty, 0)

function agregarAlCarrito(p, variante = {}, qty = 1) {
  const c = carritoLocal()
  const clave = claveLinea(p.codigo, variante)
  const linea = c.find((l) => l.clave === clave)
  const total = (linea?.qty || 0) + qty
  if (total > p.stock) { aviso('warning', 'Sin existencias suficientes', `Solo quedan ${p.stock} de ${p.nombre}.`); return false }
  if (linea) linea.qty = total
  else c.push({ clave, sku: p.codigo, nombre: p.nombre, precio: p.precio, foto: p.fotos[0]?.ruta || '', qty, variante })
  guardarCarrito(c); contarCarrito()
  return true
}

// ---------------------------------------------------------- catálogo ----
const filtros = { q: '', cats: new Set(), marcas: new Set(), min: '', max: '', soloDisp: false, orden: 'rel' }
const norm = (t) => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function filtrar(ps) {
  const q = norm(filtros.q).trim()
  const lista = ps.filter((p) =>
    (!q || norm(`${p.nombre} ${p.marca} ${p.categoria} ${p.descripcion}`).includes(q)) &&
    (!filtros.cats.size || filtros.cats.has(p.categoriaId)) &&
    (!filtros.marcas.size || filtros.marcas.has(p.marca)) &&
    (filtros.min === '' || p.precio >= Number(filtros.min)) &&
    (filtros.max === '' || p.precio <= Number(filtros.max)) &&
    (!filtros.soloDisp || p.stock > 0))
  const orden = { 'precio-asc': (a, b) => a.precio - b.precio, 'precio-desc': (a, b) => b.precio - a.precio, nombre: (a, b) => a.nombre.localeCompare(b.nombre) }[filtros.orden]
  return orden ? lista.sort(orden) : lista
}

function tarjetaProducto(p) {
  const agotado = p.stock < 1
  const etiqueta = agotado ? ['Agotado', 'agotado'] : p.etiqueta ? [p.etiqueta, p.etiquetaDestacada ? 'dest' : ''] : null
  const [f1, f2] = p.fotos
  return `<article class="tarjeta producto ${agotado ? 'sin-stock' : ''}">
    ${etiqueta ? `<span class="etiqueta ${etiqueta[1]}">${esc(etiqueta[0])}</span>` : ''}
    <a class="foto" href="#/producto/${p.id}" aria-label="Ver ${esc(p.nombre)}">
      <img src="${esc(f1?.ruta || '')}" alt="${esc(f1?.textoAlternativo || p.nombre)}" loading="lazy">
      ${f2 ? `<img src="${esc(f2.ruta)}" alt="" loading="lazy">` : ''}</a>
    <div class="info">
      <span class="marca-prod">${esc(p.marca)} · ${esc(p.categoria)}</span>
      <h3>${esc(p.nombre)}</h3><span class="suave">${esc(p.descripcion)}</span>
      <div class="precio">${dinero(p.precio)}${p.precioAnterior ? `<s>${dinero(p.precioAnterior)}</s>` : ''}</div>
      <span class="suave">${agotado ? 'Sin existencias' : p.stock <= 5 ? `Últimas ${p.stock} piezas` : 'Disponible'}</span>
      ${agotado ? `<form class="aviso-stock" data-form="aviso" data-id="${p.id}"><input type="email" name="email" required placeholder="Tu correo" aria-label="Correo para avisarte de ${esc(p.nombre)}"><button class="boton boton-sec boton-peq">Avisarme</button></form>
        <button class="boton boton-peq" disabled style="margin-top:.4rem">Agotado</button>`
        : `<div class="fila" style="margin-top:auto;padding-top:.6rem">${Object.keys(p.variantes).length
          ? `<a class="boton boton-peq" href="#/producto/${p.id}">Elegir opciones</a>`
          : `<button class="boton boton-peq" data-acc="agregar" data-id="${p.id}">Agregar</button>`}
          <a class="boton boton-sec boton-peq" href="#/producto/${p.id}">Ver detalle</a></div>`}
    </div></article>`
}

function pintarRejilla() {
  const lista = filtrar(estado.catalogo.productos)
  $('#rejilla').innerHTML = lista.map(tarjetaProducto).join('') || vacio('Ningún cubo coincide con tus filtros.')
  $('#conteo').textContent = `${lista.length} de ${estado.catalogo.productos.length} cubos`
}

function pintarFiltros() {
  const { categorias, productos } = estado.catalogo
  const marcas = [...new Set(productos.map((p) => p.marca))].filter(Boolean).sort()
  const cuenta = (fn) => productos.filter(fn).length
  const lat = $('#lateral')
  lat.hidden = false
  lat.innerHTML = `<h3>Categoría</h3><div class="filtro-lista" role="group" aria-label="Categoría">
      ${categorias.map((c) => `<label class="opcion"><input type="checkbox" data-filtro="cat" value="${c.id}" ${filtros.cats.has(c.id) ? 'checked' : ''}>${esc(c.nombre)}<span class="n">${cuenta((p) => p.categoriaId === c.id)}</span></label>`).join('')}</div>
    <h3>Marca</h3><div class="filtro-lista" role="group" aria-label="Marca">
      ${marcas.map((m) => `<label class="opcion"><input type="checkbox" data-filtro="marca" value="${esc(m)}" ${filtros.marcas.has(m) ? 'checked' : ''}>${esc(m)}<span class="n">${cuenta((p) => p.marca === m)}</span></label>`).join('')}</div>
    <h3>Precio (MXN)</h3><div class="rango">
      <input type="number" min="0" inputmode="numeric" placeholder="Mín." data-filtro="min" value="${esc(filtros.min)}" aria-label="Precio mínimo">
      <input type="number" min="0" inputmode="numeric" placeholder="Máx." data-filtro="max" value="${esc(filtros.max)}" aria-label="Precio máximo"></div>
    <h3>Disponibilidad</h3><label class="opcion"><input type="checkbox" data-filtro="disp" ${filtros.soloDisp ? 'checked' : ''}>Solo con existencias</label>
    <button class="boton boton-sec boton-peq limpiar" data-acc="limpiar-filtros">Limpiar filtros</button>`
}

vistas['#/tienda'] = async (main) => {
  estado.catalogo = await api('/catalogo')
  $('#sugerencias').innerHTML = estado.catalogo.productos.map((p) => `<option value="${esc(p.nombre)}">`).join('')
  $('#buscador').value = filtros.q
  main.innerHTML = `
    <div class="portada" style="background-image:url('${esc(estado.catalogo.portada || '')}')"><div>
      <h1>Tu próximo récord empieza con un <em>buen cubo</em></h1>
      <p>De 2x2 a Megaminx, de las mejores marcas: GAN, MoYu y QiYi.</p>
      <div class="beneficios"><span>Envío gratis desde $800</span><span>Stripe · Mercado Pago · OXXO</span><span>Compra sin registrarte</span></div></div></div>
    <div class="barra-lista"><h2 id="conteo" style="margin:0" aria-live="polite"></h2>
      <label class="fila" style="margin:0">Ordenar
        <select data-filtro="orden" style="width:auto">${[['rel', 'Relevancia'], ['precio-asc', 'Precio: menor a mayor'], ['precio-desc', 'Precio: mayor a menor'], ['nombre', 'Nombre']]
          .map(([v, t]) => `<option value="${v}" ${filtros.orden === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label></div>
    <div class="rejilla" id="rejilla"></div>`
}
// enrutar() lo llama cuando la vista ya está en pantalla (el panel lateral y la rejilla viven en el documento).
vistas['#/tienda'].despues = () => { pintarFiltros(); pintarRejilla() }

// --------------------------------------------------------------- ficha ----
vistas['#/producto'] = async (main, ruta) => {
  estado.catalogo ||= await api('/catalogo')
  const p = estado.catalogo.productos.find((x) => x.id === Number(ruta.split('/')[2]))
  if (!p) { main.innerHTML = vacio('Este cubo ya no está disponible.') + '<p style="text-align:center"><a class="boton" href="#/tienda">Volver a la tienda</a></p>'; return }
  const agotado = p.stock < 1
  const opciones = Object.entries(p.variantes)
  main.innerHTML = `
    <p class="migas"><a href="#/tienda">Tienda</a> / ${esc(p.categoria)} / ${esc(p.nombre)}</p>
    <div class="ficha"><div class="galeria">
      <div class="principal"><img id="foto-principal" src="${esc(p.fotos[0]?.ruta || '')}" alt="${esc(p.fotos[0]?.textoAlternativo || p.nombre)}"></div>
      <div class="miniaturas">${p.fotos.map((f, i) => `<button class="${i ? '' : 'activo'}" data-acc="foto" data-ruta="${esc(f.ruta)}" aria-label="Foto ${i + 1} de ${esc(p.nombre)}"><img src="${esc(f.ruta)}" alt=""></button>`).join('')}</div></div>
    <div><span class="marca-prod" style="color:var(--amarillo)">${esc(p.marca)}</span><h1>${esc(p.nombre)}</h1>
      <div class="precio">${dinero(p.precio)}${p.precioAnterior ? `<s>${dinero(p.precioAnterior)}</s>` : ''}</div>
      <p>${esc(p.descripcion)}</p>
      <form data-form="ficha" data-id="${p.id}">
        ${opciones.map(([k, vs]) => `<label for="v-${esc(k)}">${esc(k)}</label><select id="v-${esc(k)}" name="${esc(k)}" ${agotado ? 'disabled' : ''}>${vs.map((v) => `<option>${esc(v)}</option>`).join('')}</select>`).join('')}
        <label for="f-qty">Cantidad</label><input id="f-qty" name="qty" type="number" min="1" max="${Math.max(p.stock, 1)}" value="1" style="width:100px" ${agotado ? 'disabled' : ''}>
        <p class="suave">${agotado ? 'Sin existencias por ahora.' : p.stock <= 5 ? `Últimas ${p.stock} piezas.` : `${p.stock} disponibles.`}</p>
        <button class="boton boton-grande" ${agotado ? 'disabled' : ''}>${agotado ? 'Agotado' : 'Agregar al carrito'}</button></form>
      ${agotado ? `<form class="tarjeta aviso-stock" data-form="aviso" data-id="${p.id}" style="margin-top:1rem;flex-direction:column;align-items:stretch"><strong>Avísame cuando vuelva</strong>
        <input type="email" name="email" required placeholder="tucorreo@ejemplo.com" aria-label="Tu correo"><button class="boton boton-sec">Recibir aviso</button></form>` : ''}
      <table class="datos"><tr><td>Código</td><td>${esc(p.codigo)}</td></tr><tr><td>Categoría</td><td>${esc(p.categoria)}</td></tr><tr><td>Marca</td><td>${esc(p.marca)}</td></tr></table>
      <div class="garantias"><div>Envío gratis desde $800</div><div>Pago seguro</div><div>Compra sin cuenta</div></div></div></div>`
}

// ------------------------------------------------------------- carrito ----
vistas['#/carrito'] = async (main) => {
  estado.catalogo ||= await api('/catalogo')
  const c = carritoLocal()
  if (!c.length) { main.innerHTML = `<h1>Tu carrito</h1>${vacio('Tu carrito está vacío.')}<p style="text-align:center"><a class="boton" href="#/tienda">Ir a la tienda</a></p>`; return }
  const sub = subtotalCarrito(c)
  main.innerHTML = `<h1>Tu carrito</h1><div class="checkout"><section class="tarjeta">${lineasResumen(c, true)}</section>
    <aside class="tarjeta resumen">${totalesHtml(sub, null)}<a class="boton boton-grande" href="#/checkout" style="margin-top:1rem">Continuar con la compra</a>
      <p class="suave" style="text-align:center;margin-top:.6rem">No necesitas cuenta para comprar.</p></aside></div>`
}

function lineasResumen(c, editable) {
  return c.map((l) => `<div class="linea-resumen"><img src="${esc(l.foto)}" alt="">
    <div><strong>${esc(l.nombre)}</strong>${Object.keys(l.variante).length ? `<br><span class="suave">${esc(etiquetaVariante(l.variante))}</span>` : ''}
      <div class="cant">${editable ? `<input type="number" min="1" value="${l.qty}" data-acc-change="qty" data-clave="${esc(l.clave)}" aria-label="Cantidad de ${esc(l.nombre)}">
        <button class="boton boton-peligro boton-peq" data-acc="quitar" data-clave="${esc(l.clave)}">Quitar</button>` : `<span class="suave">Cantidad: ${l.qty}</span>`}</div></div>
    <strong>${dinero(l.precio * l.qty)}</strong></div>`).join('')
}

function totalesHtml(sub, envio) {
  const iva = Math.round(sub * 16) / 100
  const falta = 800 - sub
  return `<h3>Totales</h3><table class="totales"><tr><td>Subtotal</td><td>${dinero(sub)}</td></tr><tr><td>IVA 16 %</td><td>${dinero(iva)}</td></tr>
    <tr><td>Envío</td><td id="t-envio">${envio === null ? 'Se calcula con tu C.P.' : envio.costo === 0 ? '<span style="color:var(--ok)">Gratis</span>' : dinero(envio.costo)}</td></tr>
    <tr class="final"><td>Total</td><td id="t-total">${envio === null ? dinero(sub + iva) : dinero(sub + iva + envio.costo)}</td></tr></table>
    ${sub > 800 ? '<p class="suave" style="color:var(--ok)">Tu envío es gratis.</p>' : `<div class="barra-envio" aria-hidden="true"><i style="width:${Math.min(100, sub / 8)}%"></i></div><p class="suave">Te faltan ${dinero(falta + 0.01)} para envío gratis.</p>`}`
}

// ------------------------------------------------------------ checkout ----
let cotizacion = null
vistas['#/checkout'] = async (main) => {
  estado.catalogo ||= await api('/catalogo')
  const c = carritoLocal()
  if (!c.length) { location.hash = '#/carrito'; return }
  cotizacion = null
  let u = {}
  if (estado.usuario) {
    const [d] = await api('/direcciones?usuarioId=' + estado.usuario.id).catch(() => [])
    u = { nombre: `${estado.usuario.nombres || ''}`, email: estado.usuario.email || '', ...(d ? { calle: d.calle, numero: d.numero, colonia: d.colonia, ciudad: d.ciudad, estado: d.estado, codigoPostal: d.codigoPostal } : {}) }
  }
  const v = (k) => esc(u[k] || '')
  main.innerHTML = `<h1>Finalizar compra</h1><div class="checkout">
    <form data-form="checkout" id="form-checkout">
      <section class="tarjeta"><h2>1 · Datos de envío</h2>
        <div class="campos"><div><label for="c-n">Nombre completo</label><input id="c-n" name="nombre" required value="${v('nombre')}" autocomplete="name"></div>
          <div><label for="c-e">Correo</label><input id="c-e" name="email" type="email" required value="${v('email')}" autocomplete="email"></div>
          <div><label for="c-t">Teléfono</label><input id="c-t" name="telefono" inputmode="tel" autocomplete="tel"></div></div>
        <div class="campos"><div style="grid-column:span 2"><label for="c-c">Calle</label><input id="c-c" name="calle" required value="${v('calle')}" autocomplete="address-line1"></div>
          <div><label for="c-nu">Número</label><input id="c-nu" name="numero" value="${v('numero')}"></div>
          <div><label for="c-co">Colonia</label><input id="c-co" name="colonia" value="${v('colonia')}"></div>
          <div><label for="c-ci">Ciudad</label><input id="c-ci" name="ciudad" required value="${v('ciudad')}" autocomplete="address-level2"></div>
          <div><label for="c-es">Estado</label><input id="c-es" name="estado" required value="${v('estado')}" autocomplete="address-level1"></div>
          <div><label for="c-cp">Código postal</label><input id="c-cp" name="codigoPostal" required inputmode="numeric" maxlength="5" pattern="\\d{5}" value="${v('codigoPostal')}" data-acc-input="cp" autocomplete="postal-code"></div></div>
        <p class="suave" id="info-envio" aria-live="polite">Escribe tu C.P. para cotizar el envío.</p></section>
      <section class="tarjeta"><h2>2 · Método de pago</h2><div class="metodos" role="radiogroup" aria-label="Método de pago">
        <label class="metodo"><input type="radio" name="metodo" value="stripe" checked data-acc-change="metodo"><span>Tarjeta de crédito o débito<small>Procesado con Stripe</small></span></label>
        <label class="metodo"><input type="radio" name="metodo" value="mercadopago" data-acc-change="metodo"><span>Mercado Pago<small>Pago rápido con tu cuenta</small></span></label>
        <label class="metodo"><input type="radio" name="metodo" value="oxxo" data-acc-change="metodo"><span>Efectivo en OXXO<small>Generamos tu ficha de pago</small></span></label></div>
        <div id="pago-tarjeta"><div class="campos"><div style="grid-column:span 2"><label for="t-n">Número de tarjeta</label><input id="t-n" name="tarjeta" required inputmode="numeric" autocomplete="cc-number" placeholder="4242 4242 4242 4242"></div>
          <div><label for="t-v">Vence (MM/AA)</label><input id="t-v" name="vence" required autocomplete="cc-exp" placeholder="12/30"></div>
          <div><label for="t-c">CVC</label><input id="t-c" name="cvc" required inputmode="numeric" maxlength="4" autocomplete="cc-csc"></div></div>
          <p class="suave">Modo de pruebas: 4242 4242 4242 4242 aprueba; 4000 0000 0000 0002 se rechaza.</p></div>
        <p class="suave" id="pago-otro" hidden>Pago simulado en modo de pruebas.</p></section>
      ${estado.usuario ? '' : `<section class="tarjeta"><label class="opcion" style="margin:0"><input type="checkbox" name="crear" data-acc-change="crear">Crear una cuenta con estos datos para ver mi historial y guardar mi dirección (opcional)</label>
        <div id="campo-pass" hidden><label for="c-p">Contraseña (mínimo 8 caracteres)</label><input id="c-p" name="password" type="password" minlength="8" autocomplete="new-password"></div></section>`}
      <button class="boton boton-grande" id="btn-pagar">Pagar</button></form>
    <aside class="tarjeta resumen" id="resumen">${resumenCheckout(c)}</aside></div>`
}

function resumenCheckout(c) {
  return `<h2>Tu pedido</h2>${lineasResumen(c, false)}${totalesHtml(subtotalCarrito(c), cotizacion)}<a href="#/carrito" class="suave">Editar carrito</a>`
}

async function cotizarEnvio(cp) {
  const info = $('#info-envio'), c = carritoLocal()
  if (!/^\d{5}$/.test(cp)) { cotizacion = null; if (info) info.textContent = 'Escribe tu C.P. de 5 dígitos para cotizar el envío.'; $('#resumen').innerHTML = resumenCheckout(c); return }
  try {
    cotizacion = await api(`/checkout/cotizar-envio?cp=${cp}&subtotal=${subtotalCarrito(c)}`)
    info.textContent = `Zona ${cotizacion.zona} · entrega en ${cotizacion.dias} días hábiles${cotizacion.gratis ? ' · envío gratis' : ''}.`
  } catch (e) { cotizacion = null; info.textContent = e.message }
  $('#resumen').innerHTML = resumenCheckout(c)
}

// -------------------------------------------------------- confirmación ----
vistas['#/gracias'] = async (main) => {
  const r = estado.ultimaCompra
  if (!r) { location.hash = '#/tienda'; return }
  const p = r.pedido
  main.innerHTML = `<div class="tarjeta" style="max-width:720px;margin:0 auto">
    <h1>${r.metodo === 'oxxo' ? 'Pedido registrado' : '¡Gracias por tu compra!'}</h1>
    <p>Pedido <strong>#${p.id}</strong> · ${dinero(p.total)} · enviaremos la confirmación a <strong>${esc(p.cliente_email)}</strong>.</p>
    ${r.oxxo ? `<div class="ficha-oxxo"><span class="suave">Referencia de pago en OXXO</span><strong>${esc(r.oxxo.referencia.replace(/(\d{4})(?=\d)/g, '$1 '))}</strong>
      <span>Paga ${dinero(r.oxxo.monto)} en cualquier OXXO antes de ${esc(r.oxxo.vigencia)}. Tu pedido se prepara al recibir el pago.</span></div>` : `<p>${pastilla('Pago aprobado', 'ok')}</p>`}
    ${r.cuentaCreada ? '<p>Creamos tu cuenta: ya puedes ver tu historial en «Mis pedidos».</p>' : ''}
    ${lineasResumen(p.items.map((i) => ({ foto: productoPorSku(i.sku)?.fotos[0]?.ruta || '', nombre: i.nombre, variante: {}, qty: i.cantidad, precio: i.precioUnitario })), false)}
    <div class="fila" style="margin-top:1rem"><a class="boton" href="#/tienda">Seguir comprando</a>${estado.usuario ? '<a class="boton boton-sec" href="#/pedidos">Mis pedidos</a>' : ''}</div></div>`
}
