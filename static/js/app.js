/* Portal GESE CUBES · interfaz única para los servicios.
   Toda la información viene de la API (/api/...). El texto dinámico siempre se
   escapa con esc() antes de entrar al HTML. */
'use strict'

// ------------------------------------------------------------ utilidades ----
const $ = (s, r = document) => r.querySelector(s)
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const dinero = (n) => Number(n || 0).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })
const fecha = (iso) => (iso ? new Date(iso).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' }) : '—')

async function api(ruta, { metodo = 'GET', cuerpo } = {}) {
  const r = await fetch('/api' + ruta, {
    method: metodo,
    credentials: 'same-origin',
    headers: cuerpo !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
  })
  const texto = await r.text()
  let datos = null
  try { datos = texto ? JSON.parse(texto) : null } catch { /* sin cuerpo JSON */ }
  if (!r.ok) {
    const e = new Error(datos?.error || datos?.mensaje || datos?.detail || `Error ${r.status}`)
    e.status = r.status
    e.datos = datos
    throw e
  }
  return datos
}

const estado = { usuario: null, catalogo: null, ultimaCompra: null, vistos: new Set(), temporizador: null }
const esAdmin = () => estado.usuario?.rol === 'admin'

const POS = 'bottom-right'
function aviso(tipo, titulo, mensaje) { Notify.show({ title: titulo, message: mensaje || '', type: tipo, position: POS }) }
async function intentar(fn) {
  try { return await fn() } catch (e) { aviso('error', 'No se pudo completar', e.message); return undefined }
}
function formulario(form) {
  const d = {}
  new FormData(form).forEach((v, k) => { d[k] = v })
  return d
}
const pastilla = (txt, tipo = '') => `<span class="pastilla ${tipo}">${esc(txt)}</span>`
const tipoEstado = (e) => (['ENTREGADO', 'COMPLETADO', 'CERRADA', 'PAGADO', 'APROBADA', 'APROBADO', 'EMITIDA', 'succeeded'].includes(e) ? 'ok'
  : ['RECHAZADO', 'RECHAZADA', 'FALLIDO', 'CANCELADO', 'SIN_REEMBOLSO', 'declined'].includes(e) ? 'mal'
  : ['EN_REVISION', 'CREADO', 'SOLICITADA', 'INCIDENCIA'].includes(e) ? 'aviso' : '')
const vacio = (txt) => `<div class="aviso-vacio">${esc(txt)}</div>`

function modal(html) {
  const m = $('#modal')
  m.innerHTML = `<div class="caja" role="dialog" aria-modal="true">${html}</div>`
  m.hidden = false
  m.onclick = (e) => { if (e.target === m) cerrarModal() }
  const b = m.querySelector('button, input, select'); if (b) b.focus()
}
function cerrarModal() { $('#modal').hidden = true; $('#modal').innerHTML = '' }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') cerrarModal() })

// -------------------------------------------------------------- sesión ----
async function cargarSesion() {
  try { estado.usuario = (await api('/autenticacion/validar-sesion')).datos } catch { estado.usuario = null }
  const btn = $('#btn-cuenta')
  btn.textContent = estado.usuario ? estado.usuario.nombres : 'Entrar'
  $('#btn-campana').hidden = !estado.usuario
  pintarNav()
  await contarCarrito()
  sondearNotificaciones(true)
}

async function contarCarrito() {
  const n = carritoLocal().reduce((a, l) => a + l.qty, 0)
  const c = $('#contador-carrito'); c.textContent = n; c.hidden = n === 0
}

// -------------------------------------------------------- navegación ----
const NAV = [['#/tienda', 'Tienda'], ['#/pedidos', 'Mis pedidos'], ['#/devoluciones', 'Devoluciones'], ['#/cuenta', 'Mi cuenta']]
const ADMIN = [
  ['Operación', [['#/admin/panel', 'Panel de control'], ['#/admin/almacen', 'Almacén'], ['#/admin/pedidos', 'Pedidos'], ['#/admin/devoluciones', 'Devoluciones'], ['#/admin/reembolsos', 'Reembolsos']]],
  ['Catálogo', [['#/admin/inventario', 'Productos e inventario']]],
  ['Finanzas', [['#/admin/facturas', 'Facturas y pagos']]],
  ['Sistema', [['#/admin/notificaciones', 'Notificaciones']]],
]

function pintarNav() {
  const ruta = location.hash || '#/tienda'
  const items = estado.usuario ? NAV : [NAV[0]]
  $('#nav-principal').innerHTML = items.map(([h, t]) => `<a href="${h}" class="${ruta.startsWith(h) ? 'activo' : ''}">${esc(t)}</a>`).join('') +
    (esAdmin() ? `<a href="#/admin/panel" class="${ruta.startsWith('#/admin') ? 'activo' : ''}">Administración</a>` : '')
  const lat = $('#lateral')
  lat.hidden = !(esAdmin() && ruta.startsWith('#/admin'))
  lat.innerHTML = lat.hidden ? '' : ADMIN.map(([g, links]) => `<h3>${esc(g)}</h3>` +
    links.map(([h, t]) => `<a href="${h}" class="${ruta === h ? 'activo' : ''}">${esc(t)}</a>`).join('')).join('')
}

const vistas = {}
let contadorRender = 0
async function enrutar() {
  clearInterval(estado.temporizador)
  const miRender = ++contadorRender
  const ruta = location.hash || '#/tienda'
  pintarNav()
  const main = $('#vista')
  const clave = Object.keys(vistas).find((k) => ruta === k || ruta.startsWith(k + '/')) || '#/tienda'
  if (clave.startsWith('#/admin') && !esAdmin()) {
    main.innerHTML = vacio('Esta sección es solo para personal autorizado.')
    return
  }
  // Se dibuja en un contenedor aparte y solo se muestra si sigue siendo la
  // navegación más reciente (evita que una vista lenta pise a la nueva).
  const buffer = document.createElement('div')
  try { await vistas[clave](buffer, ruta) } catch (e) { buffer.innerHTML = vacio(e.message) }
  if (miRender !== contadorRender) return
  main.replaceChildren(...buffer.childNodes)
  vistas[clave].despues?.()
  main.focus({ preventScroll: true })
}
function refrescarCada(ms, fn) { clearInterval(estado.temporizador); estado.temporizador = setInterval(fn, ms) }
const recargar = () => enrutar()

// ---------------------------------------------------------- notificaciones ----
async function sondearNotificaciones(primera = false) {
  if (!estado.usuario) return
  try {
    const lista = await api(`/notificaciones?noLeidas=1&canal=APP&usuarioId=${estado.usuario.id}`)
    const c = $('#contador'); c.textContent = lista.length; c.hidden = lista.length === 0
    lista.slice().reverse().forEach((n) => {
      if (!estado.vistos.has(n.id)) {
        estado.vistos.add(n.id)
        if (!primera || lista.length <= 3) aviso(n.tipo, n.asunto, n.mensaje)
      }
    })
  } catch { /* sin sesión o sin red */ }
}
setInterval(sondearNotificaciones, 8000)
$('#btn-campana').addEventListener('click', async () => {
  const lista = await intentar(() => api(`/notificaciones?canal=APP&usuarioId=${estado.usuario.id}`))
  if (!lista) return
  modal(`<h2>Notificaciones</h2>${lista.length ? lista.slice(0, 30).map((n) => `<div class="tarjeta"><strong>${esc(n.asunto)}</strong>
    <p>${esc(n.mensaje)}</p><span class="suave">${fecha(n.fecha)}</span></div>`).join('') : vacio('Sin notificaciones.')}
    <div class="fila"><button class="boton" data-acc="cerrar-modal">Cerrar</button></div>`)
  await api('/notificaciones/marcar-leidas', { metodo: 'POST', cuerpo: {} }).catch(() => {})
  sondearNotificaciones()
})

// =============================================================== CUENTA ====
vistas['#/cuenta'] = async (main, ruta) => {
  if (!estado.usuario) {
    main.innerHTML = `<h1>Mi cuenta</h1><div class="dos">
      <form class="tarjeta" data-form="login"><h2>Iniciar sesión</h2>
        <label for="l-correo">Correo</label><input id="l-correo" name="correo" type="email" required autocomplete="username">
        <label for="l-pass">Contraseña</label><input id="l-pass" name="contrasena" type="password" required autocomplete="current-password">
        <p><button class="boton">Entrar</button></p>
        <p class="suave">Demo: ana@correo.com / Cliente123! · Admin: admin@gesecubes.mx / Admin123!</p></form>
      <form class="tarjeta" data-form="registro"><h2>Crear cuenta</h2>
        <label for="r-nombre">Nombre</label><input id="r-nombre" name="nombre" required>
        <label for="r-apellidos">Apellidos</label><input id="r-apellidos" name="apellidos">
        <label for="r-email">Correo</label><input id="r-email" name="email" type="email" required autocomplete="email">
        <label for="r-pass">Contraseña (mínimo 8 caracteres)</label><input id="r-pass" name="password" type="password" minlength="8" required autocomplete="new-password">
        <p><button class="boton">Registrarme</button></p></form></div>`
    return
  }
  const seccion = ruta.split('/')[2] || 'perfil'
  const tabs = [['perfil', 'Perfil'], ['direcciones', 'Direcciones'], ['facturacion', 'Facturación'], ['tarjetas', 'Tarjetas']]
  const uid = estado.usuario.id
  let cuerpo = ''
  if (seccion === 'perfil') {
    const p = await api('/perfil')
    cuerpo = `<form class="tarjeta" data-form="perfil"><h2>Mis datos</h2><div class="campos">
      <div><label for="p-n">Nombre</label><input id="p-n" name="nombre" value="${esc(p.nombre)}" required></div>
      <div><label for="p-a">Apellidos</label><input id="p-a" name="apellidos" value="${esc(p.apellidos)}"></div>
      <div><label for="p-t">Teléfono</label><input id="p-t" name="telefono" value="${esc(p.telefono)}"></div>
      <div><label for="p-f">Fecha de nacimiento</label><input id="p-f" name="fechaNacimiento" type="date" value="${esc(p.fechaNacimiento)}"></div></div>
      <label for="p-pr">Preferencias</label><textarea id="p-pr" name="preferencias" rows="2">${esc(p.preferencias)}</textarea>
      <p class="suave">Correo: ${esc(p.email)} · Cliente desde ${fecha(p.fechaRegistro)}</p>
      <button class="boton">Guardar</button> <button type="button" class="boton boton-sec" data-acc="logout">Cerrar sesión</button></form>`
  } else if (seccion === 'direcciones') {
    const ds = await api('/direcciones?usuarioId=' + uid)
    cuerpo = `<div class="dos"><section>${ds.map((d) => `<div class="tarjeta"><strong>${esc(d.calle)} ${esc(d.numero || '')}</strong><br>${esc(d.colonia || '')} ${esc(d.ciudad)}, ${esc(d.estado)} ${esc(d.codigoPostal || '')}
      <p class="suave">${esc(d.referencia || '')}</p></div>`).join('') || vacio('Sin direcciones guardadas.')}</section>
      <form class="tarjeta" data-form="direccion"><h2>Nueva dirección</h2><div class="campos">
      <div><label for="d-c">Calle</label><input id="d-c" name="calle" required></div><div><label for="d-n">Número</label><input id="d-n" name="numero"></div>
      <div><label for="d-co">Colonia</label><input id="d-co" name="colonia"></div><div><label for="d-ci">Ciudad</label><input id="d-ci" name="ciudad" required></div>
      <div><label for="d-e">Estado</label><input id="d-e" name="estado" required></div><div><label for="d-cp">C.P.</label><input id="d-cp" name="codigoPostal" inputmode="numeric"></div></div>
      <label for="d-r">Referencia</label><input id="d-r" name="referencia"><p><button class="boton">Guardar dirección</button></p></form></div>`
  } else if (seccion === 'facturacion') {
    const fs = await api('/datos-facturacion')
    cuerpo = `<div class="dos"><section>${fs.map((f) => `<div class="tarjeta fila entre"><div><strong>${esc(f.razonSocial)}</strong> ${f.predeterminado ? pastilla('Predeterminado', 'ok') : ''}<br>
      RFC ${esc(f.rfc)} · C.P. ${esc(f.codigoPostal)} · ${esc(f.usoCfdi)}</div><button class="boton boton-peligro boton-peq" data-acc="borrar" data-tipo="datos-facturacion" data-id="${f.id}">Eliminar</button></div>`).join('') || vacio('Sin datos fiscales.')}</section>
      <form class="tarjeta" data-form="fiscal"><h2>Datos fiscales</h2>
      <label for="f-r">RFC</label><input id="f-r" name="rfc" required maxlength="13" style="text-transform:uppercase">
      <label for="f-s">Razón social</label><input id="f-s" name="razonSocial" required><div class="campos">
      <div><label for="f-cp">C.P.</label><input id="f-cp" name="codigoPostal" required inputmode="numeric" maxlength="5"></div>
      <div><label for="f-rg">Régimen fiscal</label><input id="f-rg" name="regimenFiscal"></div>
      <div><label for="f-u">Uso de CFDI</label><input id="f-u" name="usoCfdi" value="G03"></div></div>
      <p><button class="boton">Guardar</button></p></form></div>`
  } else {
    const ts = await api('/metodos-pago')
    cuerpo = `<div class="dos"><section>${ts.map((t) => `<div class="tarjeta fila entre"><div><strong>${esc(t.marca)} ···· ${esc(t.ultimos4)}</strong> ${t.predeterminado ? pastilla('Predeterminada', 'ok') : ''}<br>
      <span class="suave">${esc(t.titular)} · vence ${String(t.venceMes).padStart(2, '0')}/${t.venceAnio}</span></div>
      <div class="fila">${t.predeterminado ? '' : `<button class="boton boton-sec boton-peq" data-acc="predeterminar" data-id="${t.id}">Predeterminar</button>`}
      <button class="boton boton-peligro boton-peq" data-acc="borrar" data-tipo="metodos-pago" data-id="${t.id}">Eliminar</button></div></div>`).join('') || vacio('Sin tarjetas guardadas.')}</section>
      <form class="tarjeta" data-form="tarjeta"><h2>Nueva tarjeta</h2>
      <label for="t-n">Número</label><input id="t-n" name="numero" inputmode="numeric" autocomplete="cc-number" required>
      <label for="t-t">Titular</label><input id="t-t" name="titular" autocomplete="cc-name" required><div class="campos">
      <div><label for="t-m">Mes</label><input id="t-m" name="venceMes" type="number" min="1" max="12" required></div>
      <div><label for="t-a">Año</label><input id="t-a" name="venceAnio" type="number" min="2024" required></div></div>
      <p class="suave">Solo se guardan la marca y los últimos 4 dígitos. Prueba: 4242 4242 4242 4242 (aprobada) o 4000 0000 0000 0002 (rechazada).</p>
      <button class="boton">Guardar tarjeta</button></form></div>`
  }
  main.innerHTML = `<h1>Mi cuenta</h1><div class="pestanas">${tabs.map(([k, t]) => `<button class="${seccion === k ? 'activo' : ''}" data-acc="ir" data-ruta="#/cuenta/${k}">${t}</button>`).join('')}</div>${cuerpo}`
}
