/* ==========================================================
   PARTE 1: EL SISTEMA DE NOTIFICACIONES

   Cómo usarlo desde cualquier parte de tu código:

     Notify.success("Título", "Mensaje");
     Notify.error("Título", "Mensaje");
     Notify.warning("Título", "Mensaje");
     Notify.info("Título", "Mensaje");

   O con todas las opciones:

     Notify.show({
       title: "Título",
       message: "Mensaje",
       type: "success",          // success | error | warning | info
       duration: 5000,           // milisegundos (0 = no se cierra solo)
       position: "top-right",    // top/bottom + left/center/right
       actions: [{ label: "Deshacer", onClick: () => console.log("hecho") }]
     });

     Notify.clear();             // cierra todas
   ========================================================== */

const Notify = (() => {
    const MAXIMO = 5
    const contenedores = {}

    const ICONOS = {
        success: '<path d="M4 12.5l5 5L20 6.5"/>',
        error: '<path d="M6 6l12 12M18 6L6 18"/>',
        warning: '<path d="M12 5v9M12 19v.01"/>',
        info: '<path d="M12 11v7M12 6v.01"/>',
    }

    function crearIcono(tipo) {
        return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
            aria-hidden="true">${ICONOS[tipo]}</svg>`
    }

    function obtenerContenedor(posicion) {
        if (!contenedores[posicion]) {
            const caja = document.createElement('div')
            caja.className = 'ntf-stack'
            caja.dataset.pos = posicion
            caja.setAttribute('aria-live', 'polite') // lectores de pantalla
            document.body.appendChild(caja)
            contenedores[posicion] = caja
        }
        return contenedores[posicion]
    }

    /* ---------- MOSTRAR UNA NOTIFICACIÓN ---------- */
    function show(opciones = {}) {
        const {
            title = '',
            message = '',
            type = 'info',
            duration = 5000,
            position = 'top-right',
            actions = [],
        } = opciones

        const contenedor = obtenerContenedor(position)

        const activas = contenedor.querySelectorAll('.ntf-wrap:not(.saliendo)')
        if (activas.length >= MAXIMO) activas[0].cerrar()

        const wrap = document.createElement('div') // caja que colapsa al salir
        wrap.className = 'ntf-wrap'

        const inner = document.createElement('div')
        inner.className = 'ntf-inner'

        const tarjeta = document.createElement('div') // la notificación en sí
        tarjeta.className = 'ntf ' + type
        tarjeta.setAttribute('role', type === 'error' ? 'alert' : 'status')
        tarjeta.tabIndex = 0

        const icono = document.createElement('div')
        icono.className = 'ntf-icono'
        icono.innerHTML = crearIcono(type)

        const texto = document.createElement('div')
        texto.className = 'ntf-texto'

        if (title) {
            const t = document.createElement('div')
            t.className = 'ntf-titulo'
            t.textContent = title // textContent evita inyección de HTML
            texto.appendChild(t)
        }

        if (message) {
            const m = document.createElement('div')
            m.className = 'ntf-mensaje'
            m.textContent = message
            texto.appendChild(m)
        }

        if (actions.length > 0) {
            const cajaAcciones = document.createElement('div')
            cajaAcciones.className = 'ntf-acciones'

            actions.forEach((accion) => {
                const boton = document.createElement('button')
                boton.type = 'button'
                boton.textContent = accion.label
                boton.addEventListener('click', () => {
                    if (accion.onClick) accion.onClick()
                    cerrar()
                })
                cajaAcciones.appendChild(boton)
            })

            texto.appendChild(cajaAcciones)
        }

        const botonX = document.createElement('button')
        botonX.type = 'button'
        botonX.className = 'ntf-cerrar'
        botonX.setAttribute('aria-label', 'Cerrar notificación')
        botonX.innerHTML =
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" ' +
            'stroke="currentColor" stroke-width="2.5" stroke-linecap="round">' +
            '<path d="M6 6l12 12M18 6L6 18"/></svg>'
        botonX.addEventListener('click', () => cerrar())

        tarjeta.append(icono, texto, botonX)

        if (duration > 0) {
            const barra = document.createElement('div')
            barra.className = 'ntf-barra'

            const relleno = document.createElement('i')
            relleno.style.animationDuration = duration + 'ms'
            // Cuando la barra termina de vaciarse, cerramos
            relleno.addEventListener('animationend', () => cerrar())

            barra.appendChild(relleno)
            tarjeta.appendChild(barra)
        }

        inner.appendChild(tarjeta)
        wrap.appendChild(inner)
        contenedor.appendChild(wrap)

        tarjeta.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') cerrar()
        })

        let inicioX = 0
        let distancia = 0
        let arrastrando = false

        tarjeta.addEventListener('pointerdown', (e) => {
            if (e.target.closest('button')) return // no arrastrar desde un botón
            arrastrando = true
            inicioX = e.clientX
            distancia = 0
            tarjeta.classList.remove('regresando')
            tarjeta.classList.add('arrastrando')
            tarjeta.setPointerCapture(e.pointerId)
        })

        tarjeta.addEventListener('pointermove', (e) => {
            if (!arrastrando) return
            distancia = e.clientX - inicioX

            tarjeta.style.transform = `translateX(${distancia}px) rotate(${distancia / 40}deg)`
            tarjeta.style.opacity = Math.max(0.25, 1 - Math.abs(distancia) / 260)
        })

        function soltar() {
            if (!arrastrando) return
            arrastrando = false
            tarjeta.classList.remove('arrastrando')

            if (Math.abs(distancia) > 90) {
                // Arrastró lo suficiente: la lanzamos fuera de la pantalla
                tarjeta.classList.add('lanzada')
                tarjeta.style.transform = `translateX(${distancia > 0 ? 420 : -420}px)`
                tarjeta.style.opacity = 0
                cerrar()
            } else {
                // No llegó: vuelve a su lugar con efecto resorte
                tarjeta.classList.add('regresando')
                tarjeta.style.transform = ''
                tarjeta.style.opacity = ''
            }
        }
        tarjeta.addEventListener('pointerup', soltar)
        tarjeta.addEventListener('pointercancel', soltar)

        /* ---------- CERRAR CON ANIMACIÓN ---------- */
        let yaCerrada = false

        function cerrar() {
            if (yaCerrada) return
            yaCerrada = true

            wrap.classList.add('saliendo')

            let quitada = false
            const quitar = () => {
                if (quitada) return
                quitada = true
                wrap.remove()
            }
            wrap.addEventListener('transitionend', (e) => {
                if (e.target === wrap) quitar()
            })
            setTimeout(quitar, 600)
        }

        wrap.cerrar = cerrar // guardamos la función para usarla desde fuera

        return { close: cerrar }
    }

    /* ---------- FUNCIONES DE AYUDA ---------- */

    function clear() {
        document.querySelectorAll('.ntf-wrap:not(.saliendo)').forEach((w) => w.cerrar())
    }

    function atajo(tipo) {
        return (title, message, extra = {}) => show({ title, message, type: tipo, ...extra })
    }

    return {
        show,
        clear,
        success: atajo('success'),
        error: atajo('error'),
        warning: atajo('warning'),
        info: atajo('info'),
    }
})()

