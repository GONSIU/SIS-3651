(function () {
  "use strict";
  if (window.pagoQrIniciado) return;
  window.pagoQrIniciado = true;

  
  var ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  var PATRON = /^QR-[A-Z0-9]{8}$/; // igual que PATRON_REFERENCIA en apps/ventas/qr.py

  function nuevaReferencia() {
    var bytes = new Uint8Array(8);
    window.crypto.getRandomValues(bytes);
    var texto = "QR-";
    bytes.forEach(function (b) { texto += ALFABETO[b % ALFABETO.length]; });
    return texto;
  }

  function iniciar(bloque) {
    var metodo = document.getElementById(bloque.dataset.metodo);
    var referencia = document.getElementById(bloque.dataset.referencia);
    var imagen = bloque.querySelector("[data-qr-imagen]");
    var detalle = bloque.querySelector("[data-qr-detalle]");
    if (!metodo || !referencia) return;
    var campoMonto = bloque.dataset.montoCampo && document.getElementById(bloque.dataset.montoCampo);
    var textoMonto = bloque.dataset.montoTexto && document.getElementById(bloque.dataset.montoTexto);
    var espera;

    function monto() {
      var valor = bloque.dataset.monto || "";
      if (campoMonto) valor = campoMonto.value;
      // "Bs 22.50" -> "22.50"
      if (textoMonto) valor = textoMonto.textContent.replace(/[^0-9.]/g, "");
      var numero = parseFloat(valor);
      return numero > 0 ? numero.toFixed(2) : null;
    }

    function actualizar() {
      if (metodo.value !== "qr") {
        bloque.classList.add("hidden");
        referencia.readOnly = false;
  
        if (PATRON.test(referencia.value)) referencia.value = "";
        return;
      }
      bloque.classList.remove("hidden");
      // Se conserva si ya es de QR (por ejemplo, al volver con errores del formulario).
      if (!PATRON.test(referencia.value)) referencia.value = nuevaReferencia();
      // La referencia guardada debe ser la que lleva el QR.
      referencia.readOnly = true;
      var valor = monto();
      if (!valor) {
        imagen.classList.add("hidden");
        detalle.textContent = "Ingresa el monto para generar el QR.";
        return;
      }
      var url = bloque.dataset.url + "?monto=" + encodeURIComponent(valor) + "&ref=" + encodeURIComponent(referencia.value);
      if (imagen.getAttribute("src") !== url) imagen.setAttribute("src", url);
      imagen.classList.remove("hidden");
      detalle.textContent = "Bs " + valor + " - referencia " + referencia.value;
    }

    function actualizarLuego() {
      clearTimeout(espera);
      espera = setTimeout(actualizar, 300);
    }

    metodo.addEventListener("change", actualizar);
    if (campoMonto) campoMonto.addEventListener("input", actualizarLuego);
    // El total de la encomienda lo recalcula otro script: se observa su texto.
    if (textoMonto) new MutationObserver(actualizarLuego).observe(textoMonto, { childList: true, characterData: true, subtree: true });
    actualizar();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-pago-qr]").forEach(iniciar);
  });
})();
