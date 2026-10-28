'use strict'
/* Vistas de administración: almacén, pedidos, devoluciones, reembolsos, inventario, finanzas, sistema. */

const tabla = (cabeceras, filas) => `<div class="tabla-scroll"><table><thead><tr>${cabeceras.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead>
  <tbody>${filas.join('') || `<tr><td colspan="${cabeceras.length}" class="suave">Sin registros.</td></tr>`}</tbody></table></div>`

// --------------------------------------------------------------- panel ----
vistas['#/admin/panel'] = async (main) => {
  const [hoy, res, pedidos] = await Promise.all([api('/inventarios/ventas-hoy'), api('/inventarios/resumen'), api('/pedidos')])
  const abiertos = pedidos.filter((p) => ['CREADO', 'PAGADO', 'EN_PICKING', 'PICKING_COMPLETO', 'EMPACADO'].includes(p.estado))
  main.innerHTML = `<div class="fila entre"><h1>Panel de control</h1><a class="boton" href="/api/inventarios/pendientes.csv" download>Descargar pedidos pendientes (CSV)</a></div>
    <div class="kpis"><div class="kpi"><b>${dinero(hoy.total)}</b><span>Ventas de hoy</span></div><div class="kpi"><b>${hoy.pedidos}</b><span>Pedidos de hoy</span></div>
      <div class="kpi"><b>${hoy.pendientes}</b><span>Por enviar</span></div><div class="kpi"><b>${res.lowProducts}</b><span>Modelos con stock bajo</span></div></div>
    <section class="tarjeta"><h2>Pedidos abiertos <span class="suave">(${abiertos.length})</span></h2>${tabla(['#', 'Fecha', 'Cliente', 'Pago', 'Estado', 'Total', ''], abiertos.map((p) => `<tr><td>${p.id}</td><td>${fecha(p.fecha)}</td>
      <td>${esc(p.cliente_nombre)}<br><span class="suave">${esc(p.cliente_email)}${p.usuario_id ? '' : ' · invitado'}</span></td><td>${esc(p.metodo_pago || '—')}</td>
      <td>${pastilla(p.estado === 'CREADO' ? 'Pendiente de pago' : p.estado === 'ENVIADO' ? 'Enviado' : 'En preparación', p.estado === 'CREADO' ? 'aviso' : 'ok')}</td><td>${dinero(p.total)}</td>
      <td class="fila">${p.estado === 'CREADO' && p.metodo_pago === 'OXXO' ? `<button class="boton boton-peq" data-acc="confirmar-oxxo" data-id="${p.id}">Confirmar pago OXXO</button>` : ''}
        ${p.estado !== 'CREADO' ? `<button class="boton boton-sec boton-peq" data-acc="lista-empaque" data-id="${p.id}">Lista de empaque</button>` : ''}</td></tr>`))}
      <p class="suave" style="margin-top:.8rem">Avanza cada pedido (picking → empaque → envío) desde <a href="#/admin/almacen">Almacén</a>.</p></section>`
}

// ------------------------------------------------------------- almacén ----
vistas['#/admin/almacen'] = async (main) => {
  const [pedidos, picking] = await Promise.all([api('/pedidos'), api('/picking/pedidos')])
  const pk = Object.fromEntries(picking.map((p) => [p.id, p]))
  const por = (...es) => pedidos.filter((p) => es.includes(p.estado))
  const lista = (titulo, items, fn) => `<section><h2>${titulo} <span class="suave">(${items.length})</span></h2>${items.map(fn).join('') || vacio('Nada pendiente.')}</section>`
  const cab = (p) => `<div class="fila entre"><strong>Pedido #${p.id}</strong>${pastilla(p.etiqueta, tipoEstado(p.estado))}</div><span class="suave">${esc(p.cliente_nombre)}</span>`
  main.innerHTML = `<h1>Almacén</h1><p class="suave">Flujo: picking → lista de empaque → packing → envío → entrega.</p><div class="dos">
    ${lista('1 · Picking', por('PAGADO', 'EN_PICKING'), (p) => `<div class="tarjeta">${cab(p)}${(pk[p.id]?.productos || []).map((i) => `
      <form class="fila entre" data-form="recogida" data-pedido="${p.id}" style="margin-top:.5rem"><span style="flex:1 1 140px">${esc(i.nombre)} <span class="suave">· ${esc(i.ubicacion)} · ${i.cantidad_recogida}/${i.cantidad_solicitada}</span></span>
      ${i.cantidad_recogida < i.cantidad_solicitada ? `<span class="fila"><input type="hidden" name="sku" value="${esc(i.sku)}"><input type="number" name="cantidad" min="1" max="${i.cantidad_solicitada - i.cantidad_recogida}" value="${i.cantidad_solicitada - i.cantidad_recogida}" style="width:70px" aria-label="Cantidad recogida de ${esc(i.nombre)}"><button class="boton boton-peq">Recoger</button></span>` : pastilla('Listo', 'ok')}</form>`).join('')}</div>`)}
    ${lista('2 · Lista de empaque y packing', por('PICKING_COMPLETO'), (p) => `<div class="tarjeta">${cab(p)}
      <div class="fila"><button class="boton boton-sec boton-peq" data-acc="lista-empaque" data-id="${p.id}">Ver / generar lista de empaque</button></div>
      <form data-form="packing" data-pedido="${p.id}"><div class="campos"><div><label>Tipo de empaque</label><select name="tipoEmpaque"><option>Caja de cartón</option><option>Caja reforzada</option><option>Sobre acolchado</option></select></div>
      <div><label>Peso (kg)</label><input type="number" step="0.1" min="0.1" name="peso" required></div></div><label>Observaciones</label><input name="observaciones" placeholder="Frágil, etc.">
      <p><button class="boton boton-peq">Registrar empaque</button></p></form></div>`)}
    ${lista('3 · Envío', por('EMPACADO'), (p) => `<div class="tarjeta">${cab(p)}<form class="fila" data-form="envio" data-pedido="${p.id}">
      <select name="paqueteria" aria-label="Paquetería">${['Estafeta', 'DHL', 'FedEx', 'Paquetexpress', 'Redpack'].map((x) => `<option>${x}</option>`).join('')}</select><button class="boton boton-peq">Enviar</button></form></div>`)}
    ${lista('4 · En camino', por('ENVIADO'), (p) => `<div class="tarjeta">${cab(p)}<div class="fila" style="margin-top:.5rem"><button class="boton boton-peq" data-acc="entregar" data-id="${p.id}">Marcar entregado</button></div></div>`)}
  </div>`
}

// -------------------------------------------------------------- pedidos ----
vistas['#/admin/pedidos'] = async (main) => {
  const ps = await api('/pedidos')
  main.innerHTML = `<h1>Pedidos</h1>` + tabla(['#', 'Fecha', 'Cliente', 'Estado', 'Total', 'Reembolsado', ''], ps.map((p) => `<tr><td>${p.id}</td><td>${fecha(p.fecha)}</td>
    <td>${esc(p.cliente_nombre)}<br><span class="suave">${esc(p.cliente_email)}</span></td><td>${pastilla(p.etiqueta, tipoEstado(p.estado))}</td><td>${dinero(p.total)}</td><td>${dinero(p.reembolsado)}</td>
    <td><button class="boton boton-sec boton-peq" data-acc="seguimiento" data-id="${p.id}">Seguimiento</button></td></tr>`))
}

// --------------------------------------------------------- devoluciones ----
vistas['#/admin/devoluciones'] = async (main) => {
  const ds = await api('/devoluciones')
  main.innerHTML = `<h1>Devoluciones e inspección</h1>` + (ds.map((d) => `<div class="tarjeta"><div class="fila entre"><strong>#${d.id} · ${esc(d.nombre)} × ${d.cantidad}</strong>${pastilla(d.estado, tipoEstado(d.estado))}</div>
    <span class="suave">Pedido #${d.pedidoId} · ${esc(d.motivo)} · ${fecha(d.creado)}${d.comentario ? ' · «' + esc(d.comentario) + '»' : ''}${d.reembolsoId ? ' · ' + esc(d.reembolsoId) : ''}</span>
    ${d.estado === 'SOLICITADA' ? `<div class="fila" style="margin-top:.6rem"><button class="boton boton-peq" data-acc="resolver-dev" data-id="${d.id}" data-aprobar="1">Aprobar</button>
      <button class="boton boton-peligro boton-peq" data-acc="resolver-dev" data-id="${d.id}" data-aprobar="0">Rechazar</button></div>` : ''}
    ${d.estado === 'APROBADA' ? `<form class="fila" style="margin-top:.6rem" data-form="inspeccion" data-id="${d.id}"><select name="resultado" aria-label="Resultado de inspección">
      <option value="APTO">Apto (reingresa al inventario)</option><option value="DEFECTUOSO">Defectuoso (no reingresa)</option><option value="NO_PROCEDE">No procede (sin reembolso)</option></select>
      <input name="observaciones" placeholder="Observaciones" style="flex:1;min-width:160px"><button class="boton boton-peq">Registrar inspección</button></form>` : ''}</div>`).join('') || vacio('Sin devoluciones.'))
}

// ----------------------------------------------------------- reembolsos ----
vistas['#/admin/reembolsos'] = async (main) => {
  const [rs, ps, reglas] = await Promise.all([api('/reembolsos'), api('/reembolsos/pedidos'), api('/reembolsos/reglas')])
  main.innerHTML = `<h1>Reembolsos</h1><p class="suave">Ventana: ${reglas.DIAS_MAXIMOS} días · aprobación automática hasta ${dinero(reglas.MONTO_AUTO_APROBACION)}.</p><div class="dos">
    <section>${rs.map((r) => `<div class="tarjeta"><div class="fila entre"><strong>${esc(r.id)} · ${dinero(r.monto)}</strong>${pastilla(r.estado, tipoEstado(r.estado))}</div>
      <span class="suave">Pedido #${r.pedidoId} · ${esc(r.motivo)} · intentos ${r.intentos}${r.transaccionId ? ' · ' + esc(r.transaccionId) : ''}</span>
      <ul class="tiempo">${r.historial.map((h) => `<li><strong>${esc(h.estado)}</strong> <span class="suave">${esc(h.detalle)}</span></li>`).join('')}</ul>
      ${r.estado === 'EN_REVISION' ? `<div class="fila"><button class="boton boton-peq" data-acc="reembolso" data-op="aprobar" data-id="${r.id}">Aprobar</button><button class="boton boton-peligro boton-peq" data-acc="reembolso" data-op="rechazar" data-id="${r.id}">Rechazar</button></div>` : ''}
      ${r.estado === 'FALLIDO' ? `<button class="boton boton-peq" data-acc="reembolso" data-op="reintentar" data-id="${r.id}">Reintentar</button>` : ''}</div>`).join('') || vacio('Sin reembolsos.')}</section>
    <form class="tarjeta" data-form="reembolso"><h2>Nuevo reembolso</h2><label for="rb-p">Pedido</label>
      <select id="rb-p" name="pedidoId" required>${ps.map((p) => `<option value="${p.id}">#${p.id} · ${esc(p.cliente)} · pendiente ${dinero(p.total - p.reembolsado)}</option>`).join('')}</select>
      <label for="rb-m">Monto (vacío = total disponible)</label><input id="rb-m" name="monto" type="number" step="0.01" min="0.01">
      <label for="rb-mo">Motivo</label><select id="rb-mo" name="motivo">${reglas.MOTIVOS_VALIDOS.map((m) => `<option>${esc(m)}</option>`).join('')}</select>
      <label for="rb-c">Comentario</label><input id="rb-c" name="comentario">
      <label><input type="checkbox" name="forzarFalla" style="width:auto"> Simular falla de la pasarela (para probar el reintento)</label>
      <p><button class="boton">Solicitar reembolso</button></p></form></div>`
  refrescarCada(3000, async () => {
    if (!(location.hash || '').startsWith('#/admin/reembolsos') || document.activeElement?.closest('form')) return
    const sc = window.scrollY; await vistas['#/admin/reembolsos']($('#vista')); window.scrollTo(0, sc)
  })
}

// ------------------------------------------------------------ inventario ----
const CATEGORIAS = ['1x1', '2x2', '3x3', '4x4', '5x5+', 'Otras formas']
vistas['#/admin/inventario'] = async (main) => {
  const [res, prods, movs] = await Promise.all([api('/inventarios/resumen'), api('/inventarios/productos'), api('/inventarios/movimientos')])
  const fotoDe = (p) => (p.fotos || '').split('\n')[0]
  main.innerHTML = `<h1>Productos e inventario</h1><div class="kpis" style="grid-template-columns:repeat(3,1fr)">
    <div class="kpi"><b>${res.totalProducts}</b><span>Modelos</span></div><div class="kpi"><b>${res.totalUnits}</b><span>Unidades en existencia</span></div>
    <div class="kpi"><b>${res.lowProducts}</b><span>Con stock bajo</span></div></div>
    <section class="tarjeta"><h2>Catálogo completo</h2><p class="suave">Edita precio, existencias y fotos (rutas separadas por coma) y pulsa Guardar en la fila. Con precio 0 el modelo se oculta.</p>
    ${tabla(['', 'SKU', 'Nombre', 'Marca', 'Categoría', 'Precio', 'Stock', 'Mín.', 'Fotos', ''], prods.map((p) => `<tr>
      <td><img class="mini" src="${esc(fotoDe(p))}" alt=""></td><td style="white-space:nowrap">${esc(p.id)}</td>
      <td><input form="fp-${esc(p.id)}" name="name" style="min-width:200px" value="${esc(p.name)}" aria-label="Nombre de ${esc(p.id)}" required></td>
      <td><select form="fp-${esc(p.id)}" name="marca" aria-label="Marca de ${esc(p.id)}">${['GAN', 'MoYu', 'QiYi', p.marca].filter((m, i, a) => m && a.indexOf(m) === i).map((m) => `<option ${m === p.marca ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select></td>
      <td><select form="fp-${esc(p.id)}" name="categoria" aria-label="Categoría de ${esc(p.id)}">${CATEGORIAS.map((c) => `<option ${c === p.categoria ? 'selected' : ''}>${c}</option>`).join('')}</select></td>
      <td><input form="fp-${esc(p.id)}" name="price" type="number" min="0" step="0.01" value="${p.price}" style="width:90px" aria-label="Precio de ${esc(p.id)}"></td>
      <td><input form="fp-${esc(p.id)}" name="stock" type="number" min="0" value="${p.stock}" style="width:75px" aria-label="Existencias de ${esc(p.id)}">${p.stock === 0 ? '<br>' + pastilla('Agotado', 'mal') : p.stock <= p.min ? '<br>' + pastilla('Bajo', 'aviso') : ''}</td>
      <td><input form="fp-${esc(p.id)}" name="min" type="number" min="0" value="${p.min}" style="width:65px" aria-label="Mínimo de ${esc(p.id)}"></td>
      <td><input form="fp-${esc(p.id)}" name="fotos" value="${esc((p.fotos || '').split('\n').join(', '))}" style="min-width:200px" aria-label="Fotos de ${esc(p.id)}"></td>
      <td class="fila"><button class="boton boton-peq" form="fp-${esc(p.id)}">Guardar</button><button class="boton boton-peligro boton-peq" data-acc="borrar-producto" data-id="${esc(p.id)}">Baja</button></td></tr>`))}
    ${prods.map((p) => `<form id="fp-${esc(p.id)}" data-form="editar-producto" data-id="${esc(p.id)}" hidden></form>`).join('')}</section>
    <div class="dos"><form class="tarjeta" data-form="producto"><h2>Alta de modelo</h2><div class="campos">
      <div><label for="n-i">SKU</label><input id="n-i" name="id" required></div><div><label for="n-n">Nombre</label><input id="n-n" name="name" required></div>
      <div><label for="n-ma">Marca</label><select id="n-ma" name="marca"><option>GAN</option><option>MoYu</option><option>QiYi</option></select></div>
      <div><label for="n-c">Categoría</label><select id="n-c" name="categoria">${CATEGORIAS.map((c) => `<option>${c}</option>`).join('')}</select></div>
      <div><label for="n-s">Stock</label><input id="n-s" name="stock" type="number" min="0" value="0" required></div><div><label for="n-m">Mínimo</label><input id="n-m" name="min" type="number" min="0" value="0" required></div>
      <div><label for="n-p">Precio de venta</label><input id="n-p" name="price" type="number" min="0" step="0.01" value="0"></div></div>
      <p class="suave">Con precio 0 el producto queda oculto. Agrega las fotos después, en la tabla.</p><button class="boton">Crear producto</button></form>
    <form class="tarjeta" data-form="movimiento"><h2>Registrar movimiento</h2>
      <label for="m-p">Producto</label><select id="m-p" name="productId">${prods.map((p) => `<option value="${esc(p.id)}">${esc(p.id)} · ${esc(p.name)}</option>`).join('')}</select>
      <div class="campos"><div><label for="m-t">Tipo</label><select id="m-t" name="type"><option value="compra">Compra (entrada)</option><option value="venta">Venta (salida)</option></select></div>
      <div><label for="m-q">Cantidad</label><input id="m-q" name="quantity" type="number" min="1" value="1" required></div></div><p><button class="boton">Registrar</button></p></form></div>
    <section class="tarjeta"><h2>Últimos movimientos</h2>${tabla(['Fecha', 'Producto', 'Tipo', 'Cant.', 'Stock', 'Referencia'], movs.slice(0, 25).map((m) => `<tr><td>${fecha(m.date)}</td><td>${esc(m.product)}</td>
      <td>${pastilla(m.type, m.type === 'venta' ? 'aviso' : 'ok')}</td><td>${m.qty}</td><td>${m.result}</td><td>${esc(m.referencia)}</td></tr>`))}</section>`
}

// ------------------------------------------------------------- finanzas ----
vistas['#/admin/facturas'] = async (main) => {
  const [fs, pagos] = await Promise.all([api('/facturacion'), api('/procesamiento-pagos/pagos')])
  main.innerHTML = `<h1>Facturas y pagos</h1><section class="tarjeta"><h2>Facturas</h2>${tabla(['Folio', 'Pedido', 'Receptor', 'RFC', 'Subtotal', 'IVA', 'Total', 'Fecha'],
    fs.map((f) => `<tr><td>${esc(f.folio)}</td><td>#${f.pedidoId}</td><td>${esc(f.razonSocial)}</td><td>${esc(f.rfc)}</td><td>${dinero(f.subtotal)}</td><td>${dinero(f.iva)}</td><td>${dinero(f.total)}</td><td>${fecha(f.fecha)}</td></tr>`))}</section>
    <section class="tarjeta"><h2>Pagos</h2>${tabla(['#', 'Pedido', 'Monto', 'Método', 'Estado', 'Fecha'], pagos.map((p) => `<tr><td>${p.id}</td><td>#${p.pedido_id}</td><td>${dinero(p.monto)}</td><td>${esc(p.metodo)}</td><td>${pastilla(p.estado, tipoEstado(p.estado))}</td><td>${fecha(p.fecha)}</td></tr>`))}</section>`
}

// --------------------------------------------------------------- sistema ----
vistas['#/admin/notificaciones'] = async (main) => {
  const ns = await api('/notificaciones')
  main.innerHTML = `<h1>Notificaciones</h1><div class="dos"><section class="tarjeta"><h2>Registro de envíos</h2>${tabla(['Fecha', 'Canal', 'Destino', 'Asunto'], ns.slice(0, 60).map((n) => `<tr><td>${fecha(n.fecha)}</td><td>${pastilla(n.canal)}</td><td>${esc(n.destinatario)}</td><td>${esc(n.asunto)}</td></tr>`))}</section>
    <form class="tarjeta" data-form="notificar"><h2>Enviar aviso a un usuario</h2><label for="nt-u">ID de usuario</label><input id="nt-u" name="usuarioId" type="number" min="1" required>
    <label for="nt-t">Tipo</label><select id="nt-t" name="tipo"><option value="info">Información</option><option value="success">Éxito</option><option value="warning">Advertencia</option><option value="error">Error</option></select>
    <label for="nt-a">Asunto</label><input id="nt-a" name="asunto" required><label for="nt-m">Mensaje</label><textarea id="nt-m" name="mensaje" rows="3" required></textarea>
    <p><button class="boton">Enviar</button></p></form></div>`
}
