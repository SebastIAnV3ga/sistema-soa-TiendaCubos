'use strict'
/* Vistas del cliente: pedidos, seguimiento, devoluciones y reembolsos. */

vistas['#/pedidos'] = async (main) => {
  if (!estado.usuario) { main.innerHTML = vacio('Inicia sesión para consultar tu historial de pedidos.'); return }
  let lista
  try { lista = await api('/historial-pedidos') } catch (e) {
    main.innerHTML = `<h1>Mis pedidos</h1>${vacio('No pudimos cargar tu historial. Intenta actualizar la página.')}`
    throw e
  }
  const estados = [...new Set(lista.map((p) => p.estado).filter(Boolean))].sort()
  const buscar = (selector) => main.querySelector(selector)
  main.innerHTML = `
    <div class="historial-cabecera"><div><p class="marca-prod">TU CUENTA · GESE CUBES</p><h1>Mis pedidos</h1><p class="suave">Consulta tus compras, revisa el envío y vuelve a tus facturas.</p></div><a class="boton boton-sec" href="#/tienda">Seguir comprando</a></div>
    <div class="historial-resumen" id="resumen-pedidos"></div>
    <div class="historial-filtros">
      <input id="buscar-pedido" type="search" placeholder="Buscar por número o producto…" aria-label="Buscar pedidos">
      <select id="filtro-estado" aria-label="Filtrar por estado"><option value="">Todos los estados</option>${estados.map((e) => `<option value="${esc(e)}">${esc(e)}</option>`).join('')}</select>
      <label>Desde <input id="fecha-desde" type="date" aria-label="Fecha inicial"></label>
      <label>Hasta <input id="fecha-hasta" type="date" aria-label="Fecha final"></label>
      <button id="limpiar-fechas" class="boton boton-sec" type="button">Limpiar fechas</button>
    </div>
    <p id="error-historial" class="suave" role="alert" hidden></p>
    <p id="conteo-pedidos" class="suave" aria-live="polite"></p><section id="lista-pedidos"></section>`

  let consultaFechas = 0
  const render = () => {
    const q = norm(buscar('#buscar-pedido').value).trim()
    const estadoFiltro = buscar('#filtro-estado').value
    const filtrados = lista.filter((p) => (!estadoFiltro || p.estado === estadoFiltro) &&
      (!q || norm([p.id, ...(p.items || []).map((i) => i.nombre), p.envio?.guia, p.factura].join(' ')).includes(q)))
    const totalGastado = lista.filter((p) => !['CANCELADO', 'RECHAZADO', 'FALLIDO'].includes(p.estado)).reduce((a, p) => a + Number(p.total || 0), 0)
    buscar('#resumen-pedidos').innerHTML = `<div class="historial-kpi"><span>Pedidos registrados</span><strong>${lista.length}</strong></div><div class="historial-kpi"><span>Compras acumuladas*</span><strong>${dinero(totalGastado)}</strong></div><div class="historial-kpi"><span>En proceso</span><strong>${lista.filter((p) => !['ENTREGADO', 'COMPLETADO', 'CANCELADO', 'RECHAZADO'].includes(p.estado)).length}</strong></div>`
    buscar('#conteo-pedidos').textContent = `Mostrando ${filtrados.length} de ${lista.length} pedidos`
    buscar('#lista-pedidos').innerHTML = filtrados.length ? filtrados.map((p) => `
      <article class="tarjeta pedido-historico"><div class="fila entre"><div><span class="suave">PEDIDO</span><h2>#${p.id}</h2></div>${pastilla(p.etiqueta || p.estado, tipoEstado(p.estado))}</div>
        <div class="pedido-meta"><span>📅 ${fecha(p.fecha)}</span><span>${p.envio ? `🚚 ${esc(p.envio.paqueteria || 'Envío')} · Guía ${esc(p.envio.guia || 'pendiente')}` : '📦 Envío pendiente de asignar'}</span>${p.factura ? `<span>🧾 Factura ${esc(p.factura)}</span>` : ''}</div>
        <ul class="pedido-items">${(p.items || []).map((i) => `<li>${esc(i.nombre)} × ${i.cantidad} <span class="suave">· ${dinero(i.precioUnitario)}</span></li>`).join('') || '<li class="suave">No hay artículos para mostrar.</li>'}</ul>
        <div class="fila entre"><div><span class="suave">Total del pedido</span><div class="precio">${dinero(p.total)}</div></div><div class="fila" style="flex-wrap:wrap;justify-content:flex-end">
          <button class="boton boton-sec boton-peq" data-acc="seguimiento" data-id="${p.id}">Seguimiento</button>
          ${p.estado === 'CREADO' ? `<button class="boton boton-peq" data-acc="pagar-pedido" data-id="${p.id}">Pagar</button>` : ''}
          ${p.estado !== 'CREADO' && !p.factura ? `<button class="boton boton-sec boton-peq" data-acc="facturar" data-id="${p.id}">Solicitar factura</button>` : ''}
          ${p.factura ? `<button class="boton boton-sec boton-peq" data-acc="ver-factura" data-id="${p.id}">Ver factura</button>` : ''}
          ${p.estado === 'ENTREGADO' ? `<button class="boton boton-sec boton-peq" data-acc="devolver" data-id="${p.id}">Devolver</button>` : ''}
        </div></div></article>`).join('') : vacio(lista.length ? 'No hay pedidos que coincidan con tu búsqueda.' : 'Aún no tienes pedidos. Cuando hagas tu primera compra, aparecerá aquí.')
  }
  const cargarFechas = async () => {
    const consulta = ++consultaFechas
    const params = new URLSearchParams()
    if (buscar('#fecha-desde').value) params.set('desde', buscar('#fecha-desde').value)
    if (buscar('#fecha-hasta').value) params.set('hasta', buscar('#fecha-hasta').value)
    const query = params.toString()
    try {
      const pedidos = await api(`/historial-pedidos${query ? `?${query}` : ''}`)
      if (consulta !== consultaFechas) return
      lista = pedidos
      buscar('#error-historial').hidden = true
      render()
    } catch (e) {
      if (consulta !== consultaFechas) return
      const error = buscar('#error-historial')
      error.textContent = e.message
      error.hidden = false
    }
  }
  buscar('#buscar-pedido').addEventListener('input', render)
  buscar('#filtro-estado').addEventListener('change', render)
  buscar('#fecha-desde').addEventListener('change', cargarFechas)
  buscar('#fecha-hasta').addEventListener('change', cargarFechas)
  buscar('#limpiar-fechas').addEventListener('click', () => {
    buscar('#fecha-desde').value = ''
    buscar('#fecha-hasta').value = ''
    cargarFechas()
  })
  render()
}

vistas['#/devoluciones'] = async (main) => {
  if (!estado.usuario) { main.innerHTML = vacio('Inicia sesión para ver tus devoluciones.'); return }
  const [devs, rees] = await Promise.all([api('/devoluciones'), api('/reembolsos')])
  main.innerHTML = `<h1>Devoluciones y reembolsos</h1>
    <p class="suave">Para devolver un artículo entra a <a href="#/pedidos">Mis pedidos</a> y elige «Devolver» en un pedido entregado.</p>
    <div class="dos"><section><h2>Devoluciones</h2>${devs.map((d) => `<div class="tarjeta"><div class="fila entre"><strong>#${d.id} · ${esc(d.nombre)} × ${d.cantidad}</strong>${pastilla(d.estado, tipoEstado(d.estado))}</div>
      <span class="suave">Pedido #${d.pedidoId} · ${esc(d.motivo)}${d.reembolsoId ? ' · ' + esc(d.reembolsoId) : ''}</span></div>`).join('') || vacio('Sin devoluciones.')}</section>
    <section><h2>Reembolsos</h2>${rees.map((r) => `<div class="tarjeta"><div class="fila entre"><strong>${esc(r.id)} · ${dinero(r.monto)}</strong>${pastilla(r.estado, tipoEstado(r.estado))}</div>
      <span class="suave">Pedido #${r.pedidoId} · ${esc(r.historial.at(-1)?.detalle)}</span></div>`).join('') || vacio('Sin reembolsos.')}</section></div>`
  refrescarCada(4000, async () => {
    if (!(location.hash || '').startsWith('#/devoluciones')) return
    const sc = window.scrollY; await vistas['#/devoluciones']($('#vista')); window.scrollTo(0, sc)
  })
}
