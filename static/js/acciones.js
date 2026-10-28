'use strict'
/* Acciones (clics), formularios y arranque del portal. */

const num = (v) => (v === '' || v == null ? undefined : Number(v))

const lineaTiempo = (h) => `<ul class="tiempo">${h.map((e) => `<li><strong>${esc(e.estado)}</strong> <span class="suave">${esc(e.detalle)} · ${fecha(e.fecha)}</span></li>`).join('')}</ul>`

// ================================================================ clics ====
const acciones = {
  'cerrar-modal': cerrarModal,
  ir: (d) => { location.hash = d.ruta },
  categoria: (d) => { sessionStorage.setItem('cat', d.id); recargar() },

  async agregar(d) {
    const p = estado.catalogo.productos.find((x) => x.id === Number(d.id))
    if (p && agregarAlCarrito(p)) aviso('success', 'Agregado al carrito', p.nombre)
  },
  foto(d) {
    $('#foto-principal').src = d.ruta
    document.querySelectorAll('.miniaturas button').forEach((b) => b.classList.toggle('activo', b.dataset.ruta === d.ruta))
  },
  quitar(d) { guardarCarrito(carritoLocal().filter((l) => l.clave !== d.clave)); contarCarrito(); recargar() },
  'limpiar-filtros'() {
    Object.assign(filtros, { q: '', min: '', max: '', soloDisp: false }); filtros.cats.clear(); filtros.marcas.clear()
    $('#buscador').value = ''; pintarFiltros(); pintarRejilla()
  },
  imprimir() { window.print() },
  async 'confirmar-oxxo'(d) { await api(`/checkout/oxxo/${d.id}/confirmar`, { metodo: 'POST', cuerpo: {} }); aviso('success', 'Pago OXXO confirmado', `Pedido #${d.id}`); recargar() },

  async logout() {
    await api('/autenticacion/cerrar-sesion', { metodo: 'POST' })
    await cargarSesion(); location.hash = '#/tienda'; recargar()
    aviso('info', 'Sesión cerrada')
  },

  async borrar(d) { if (confirm('¿Eliminar este registro?')) { await api(`/${d.tipo}/${d.id}`, { metodo: 'DELETE' }); recargar() } },
  async predeterminar(d) { await api(`/metodos-pago/${d.id}/predeterminado`, { metodo: 'PUT', cuerpo: {} }); recargar() },

  async seguimiento(d) {
    const s = await api('/seguimiento-pedidos/pedidos/' + d.id)
    modal(`<h2>Pedido #${s.id}</h2><p>${pastilla(s.estado, tipoEstado(s.estadoCodigo))} · ${esc(s.cliente)}</p>
      ${s.envio ? `<p class="suave">${esc(s.envio.paqueteria)} · guía <strong>${esc(s.envio.guia)}</strong></p>` : ''}${lineaTiempo(s.historial)}
      <button class="boton" data-acc="cerrar-modal">Cerrar</button>`)
  },

  async 'pagar-pedido'(d) {
    const tarjetas = await api('/metodos-pago')
    const t = tarjetas.find((x) => x.predeterminado) || tarjetas[0]
    if (!t) { aviso('warning', 'Falta una tarjeta', 'Agrega una tarjeta para pagar.'); location.hash = '#/cuenta/tarjetas'; return }
    await api('/procesamiento-pagos/pagar', { metodo: 'POST', cuerpo: { pedidoId: Number(d.id), metodoPagoId: t.id } })
    aviso('success', 'Pago aprobado', `Pedido #${d.id} pagado con ${t.marca} ···· ${t.ultimos4}.`); recargar()
  },

  async facturar(d) {
    const f = await api('/facturacion', { metodo: 'POST', cuerpo: { pedidoId: Number(d.id) } })
    aviso('success', 'Factura emitida', f.folio); recargar()
  },
  async 'ver-factura'(d) {
    const f = await api('/facturacion/pedido/' + d.id)
    modal(`<h2>Factura ${esc(f.folio)}</h2><table><tr><td>Receptor</td><td>${esc(f.razonSocial)}</td></tr><tr><td>RFC</td><td>${esc(f.rfc)}</td></tr>
      <tr><td>C.P. fiscal</td><td>${esc(f.codigoPostal)}</td></tr><tr><td>Uso CFDI</td><td>${esc(f.usoCfdi)}</td></tr><tr><td>Subtotal</td><td>${dinero(f.subtotal)}</td></tr>
      <tr><td>IVA</td><td>${dinero(f.iva)}</td></tr><tr><td><strong>Total</strong></td><td><strong>${dinero(f.total)}</strong></td></tr><tr><td>Fecha</td><td>${fecha(f.fecha)}</td></tr></table>
      <button class="boton" data-acc="cerrar-modal">Cerrar</button>`)
  },

  async devolver(d) {
    const [p, m] = await Promise.all([api('/pedidos/' + d.id), api('/devoluciones/motivos')])
    modal(`<h2>Devolver artículo · pedido #${p.id}</h2><form data-form="devolucion" data-pedido="${p.id}">
      <label for="dv-s">Artículo</label><select id="dv-s" name="sku">${p.items.map((i) => `<option value="${esc(i.sku)}">${esc(i.nombre)} (×${i.cantidad})</option>`).join('')}</select>
      <label for="dv-c">Cantidad</label><input id="dv-c" name="cantidad" type="number" min="1" value="1" required>
      <label for="dv-m">Motivo</label><select id="dv-m" name="motivo">${m.motivos.map((x) => `<option>${esc(x)}</option>`).join('')}</select>
      <label for="dv-o">Comentario</label><textarea id="dv-o" name="comentario" rows="2"></textarea>
      <p class="suave">Plazo: ${m.diasMaximos} días desde la entrega.</p>
      <div class="fila"><button class="boton">Solicitar devolución</button><button type="button" class="boton boton-sec" data-acc="cerrar-modal">Cancelar</button></div></form>`)
  },

  // ---- administración
  async 'lista-empaque'(d) {
    let l
    try { l = await api('/lista-empaque/' + d.id) } catch (e) {
      if (e.status !== 404) throw e
      l = await api('/lista-empaque', { metodo: 'POST', cuerpo: { pedidoId: Number(d.id) } }); recargar()
    }
    const dst = l.destino
    modal(`<h2>Lista de empaque ${esc(l.folio)}</h2><p>Pedido #${l.pedidoId} · ${esc(l.cliente)}</p>
      <p class="suave">${dst ? `${esc(dst.calle)} ${esc(dst.numero || '')}, ${esc(dst.colonia || '')} ${esc(dst.ciudad)}, ${esc(dst.estado)} ${esc(dst.codigoPostal || '')}` : 'Sin dirección'}</p>
      <table><thead><tr><th>SKU</th><th>Artículo</th><th>Ubicación</th><th>Cant.</th></tr></thead><tbody>${l.articulos.map((a) => `<tr><td>${esc(a.sku)}</td><td>${esc(a.nombre)}</td><td>${esc(a.ubicacion)}</td><td>${a.cantidad}</td></tr>`).join('')}</tbody></table>
      <p><strong>${l.totalPiezas} piezas</strong></p><div class="fila"><button class="boton" data-acc="imprimir">Imprimir / guardar PDF</button><button class="boton boton-sec" data-acc="cerrar-modal">Cerrar</button></div>`)
  },
  async entregar(d) {
    const e = await api('/envios/pedido/' + d.id)
    await api(`/envios/${e.id}/estado`, { metodo: 'PUT', cuerpo: { estado: 'ENTREGADO' } })
    aviso('success', 'Pedido entregado', `Pedido #${d.id}`); recargar()
  },
  async 'resolver-dev'(d) { await api(`/devoluciones/${d.id}/resolucion`, { metodo: 'PUT', cuerpo: { aprobar: d.aprobar === '1' } }); recargar() },
  async reembolso(d) { await api(`/reembolsos/${d.id}/${d.op}`, { metodo: 'POST', cuerpo: {} }); aviso('info', 'Reembolso', `${d.id}: ${d.op}`); recargar() },
  async 'borrar-producto'(d) { if (confirm(`¿Eliminar el producto ${d.id}?`)) { await api('/inventarios/productos/' + encodeURIComponent(d.id), { metodo: 'DELETE' }); recargar() } },
}

document.addEventListener('click', (ev) => {
  const el = ev.target.closest('[data-acc]')
  if (!el || !acciones[el.dataset.acc]) return
  ev.preventDefault()
  intentar(() => acciones[el.dataset.acc](el.dataset))
})

// Filtros del catálogo, buscador y controles del checkout (cambian la pantalla sin recargarla).
function alternar(conjunto, valor, on) { on ? conjunto.add(valor) : conjunto.delete(valor) }
document.addEventListener('change', (ev) => {
  const el = ev.target
  const f = el.dataset.filtro
  if (f) {
    if (f === 'cat') alternar(filtros.cats, Number(el.value), el.checked)
    else if (f === 'marca') alternar(filtros.marcas, el.value, el.checked)
    else if (f === 'disp') filtros.soloDisp = el.checked
    else if (f === 'orden') filtros.orden = el.value
    else return
    pintarRejilla()
    return
  }
  switch (el.dataset.accChange) {
    case 'qty': {
      const c = carritoLocal(), l = c.find((x) => x.clave === el.dataset.clave)
      const p = l && productoPorSku(l.sku)
      if (l) l.qty = Math.max(1, Math.min(Number(el.value) || 1, p ? p.stock : 99))
      guardarCarrito(c); contarCarrito(); recargar()
      break
    }
    case 'metodo': {
      const tarjeta = el.value === 'stripe'
      $('#pago-tarjeta').hidden = !tarjeta; $('#pago-otro').hidden = tarjeta
      $('#pago-otro').textContent = el.value === 'oxxo' ? 'Al confirmar te damos una referencia para pagar en cualquier OXXO.' : 'Pago simulado de Mercado Pago en modo de pruebas.'
      $('#t-n').required = $('#t-v').required = $('#t-c').required = tarjeta
      break
    }
    case 'crear':
      $('#campo-pass').hidden = !el.checked; $('#c-p').required = el.checked
      break
  }
})
document.addEventListener('input', (ev) => {
  const el = ev.target
  if (el.id === 'buscador') {
    filtros.q = el.value
    if ((location.hash || '#/tienda').startsWith('#/tienda')) { if ($('#rejilla')) pintarRejilla() } else location.hash = '#/tienda'
  } else if (el.dataset.filtro === 'min' || el.dataset.filtro === 'max') {
    filtros[el.dataset.filtro] = el.value; pintarRejilla()
  } else if (el.dataset.accInput === 'cp') {
    el.value = el.value.replace(/\D/g, ''); cotizarEnvio(el.value)
  }
})

// ========================================================= formularios ====
const formularios = {
  async login(d) {
    const r = await api('/autenticacion/iniciar-sesion', { metodo: 'POST', cuerpo: d })
    await cargarSesion(); aviso('success', 'Bienvenido', r.mensaje); location.hash = esAdmin() ? '#/admin/panel' : '#/tienda'; recargar()
  },
  async registro(d) {
    await api('/registro', { metodo: 'POST', cuerpo: d })
    await api('/autenticacion/iniciar-sesion', { metodo: 'POST', cuerpo: { correo: d.email, contrasena: d.password } })
    await cargarSesion(); aviso('success', 'Cuenta creada', 'Ya puedes comprar.'); location.hash = '#/tienda'; recargar()
  },
  async perfil(d) { await api('/perfil', { metodo: 'PUT', cuerpo: d }); await cargarSesion(); aviso('success', 'Perfil actualizado'); recargar() },
  async direccion(d) {
    await api('/direcciones', { metodo: 'POST', cuerpo: { ...d, usuarioId: estado.usuario.id } }); aviso('success', 'Dirección guardada'); recargar()
  },
  async fiscal(d) { await api('/datos-facturacion', { metodo: 'POST', cuerpo: d }); aviso('success', 'Datos fiscales guardados'); recargar() },
  async tarjeta(d) {
    await api('/metodos-pago', { metodo: 'POST', cuerpo: { ...d, venceMes: Number(d.venceMes), venceAnio: Number(d.venceAnio) } })
    aviso('success', 'Tarjeta guardada'); recargar()
  },
  async aviso(d, f) {
    const r = await api('/catalogo/avisos-stock', { metodo: 'POST', cuerpo: { productoId: Number(f.dataset.id), email: d.email } })
    aviso('success', 'Listo', r.mensaje); f.reset()
  },
  async ficha(d, f) {
    const p = estado.catalogo.productos.find((x) => x.id === Number(f.dataset.id))
    const { qty, ...variante } = d
    if (agregarAlCarrito(p, variante, Number(qty) || 1)) { aviso('success', 'Agregado al carrito', p.nombre); location.hash = '#/carrito' }
  },
  async checkout(d) {
    const c = carritoLocal()
    const cuerpo = {
      items: c.map((l) => ({ sku: l.sku, qty: l.qty, variante: l.variante })), metodo: d.metodo,
      envio: Object.fromEntries(['nombre', 'email', 'telefono', 'calle', 'numero', 'colonia', 'ciudad', 'estado', 'codigoPostal'].map((k) => [k, d[k] || ''])),
    }
    if (d.metodo === 'stripe') cuerpo.tarjeta = { numero: d.tarjeta, vence: d.vence, cvc: d.cvc }
    if (d.crear) cuerpo.crearCuenta = { password: d.password }
    const r = await api('/checkout/pedido', { metodo: 'POST', cuerpo })
    guardarCarrito([]); await contarCarrito()
    if (r.cuentaCreada) await api('/autenticacion/iniciar-sesion', { metodo: 'POST', cuerpo: { correo: d.email, contrasena: d.password } }).then(cargarSesion)
    estado.ultimaCompra = r
    location.hash = '#/gracias'; recargar()
  },
  async devolucion(d, f) {
    await api('/devoluciones', { metodo: 'POST', cuerpo: { pedidoId: Number(f.dataset.pedido), sku: d.sku, cantidad: Number(d.cantidad), motivo: d.motivo, comentario: d.comentario } })
    cerrarModal(); aviso('success', 'Devolución solicitada'); location.hash = '#/devoluciones'; recargar()
  },
  // ---- administración
  async recogida(d, f) {
    const r = await api(`/picking/pedidos/${f.dataset.pedido}/recogidas`, { metodo: 'POST', cuerpo: { sku: d.sku, cantidad: Number(d.cantidad) } })
    aviso('success', r.mensaje, `${r.sku}: faltan ${r.cantidad_pendiente}`); recargar()
  },
  async packing(d, f) {
    await api('/packing', { metodo: 'POST', cuerpo: { pedidoId: Number(f.dataset.pedido), tipoEmpaque: d.tipoEmpaque, peso: Number(d.peso), observaciones: d.observaciones } })
    aviso('success', 'Pedido empacado'); recargar()
  },
  async envio(d, f) {
    const e = await api('/envios', { metodo: 'POST', cuerpo: { pedidoId: Number(f.dataset.pedido), paqueteria: d.paqueteria } })
    aviso('success', 'Envío creado', `Guía ${e.guia}`); recargar()
  },
  async inspeccion(d, f) {
    const r = await api('/inspeccion-devoluciones', { metodo: 'POST', cuerpo: { devolucionId: Number(f.dataset.id), resultado: d.resultado, observaciones: d.observaciones } })
    aviso(r.advertencia ? 'warning' : 'success', 'Inspección registrada', r.advertencia || (r.reembolso ? `Reembolso ${r.reembolso.id} en proceso` : 'Sin reembolso')); recargar()
  },
  async reembolso(d) {
    const r = await api('/reembolsos', { metodo: 'POST', cuerpo: { pedidoId: Number(d.pedidoId), monto: num(d.monto), motivo: d.motivo, comentario: d.comentario, forzarFalla: !!d.forzarFalla } })
    aviso('info', 'Reembolso solicitado', r.id); recargar()
  },
  async movimiento(d) {
    const r = await api('/inventarios/movimientos', { metodo: 'POST', cuerpo: { productId: d.productId, type: d.type, quantity: Number(d.quantity) } })
    aviso('success', 'Movimiento registrado', `${r.product}: stock ${r.result}`); recargar()
  },
  async producto(d) {
    await api('/inventarios/productos', { metodo: 'POST', cuerpo: { id: d.id, name: d.name, marca: d.marca, categoria: d.categoria, stock: Number(d.stock), min: Number(d.min), price: Number(d.price || 0) } })
    aviso('success', 'Producto creado'); recargar()
  },
  async 'editar-producto'(d, f) {
    await api('/inventarios/productos/' + encodeURIComponent(f.dataset.id), { metodo: 'PUT', cuerpo: {
      name: d.name, marca: d.marca, categoria: d.categoria, price: Number(d.price), stock: Number(d.stock), min: Number(d.min),
      fotos: d.fotos.split(',').map((x) => x.trim()).filter(Boolean) } })
    aviso('success', 'Producto actualizado', f.dataset.id); recargar()
  },
  async notificar(d) {
    await api('/notificaciones', { metodo: 'POST', cuerpo: { ...d, usuarioId: Number(d.usuarioId) } }); aviso('success', 'Aviso enviado'); recargar()
  },
}

document.addEventListener('submit', (ev) => {
  const f = ev.target.closest('[data-form]')
  if (!f || !formularios[f.dataset.form]) return
  ev.preventDefault()
  const boton = f.querySelector('button:not([type])')
  if (boton) boton.disabled = true
  intentar(() => formularios[f.dataset.form](formulario(f), f)).finally(() => { if (boton) boton.disabled = false })
})

// ============================================================== arranque ====
window.addEventListener('hashchange', enrutar)
cargarSesion().then(enrutar)
