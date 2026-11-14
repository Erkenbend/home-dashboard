/*
 * Offline indicator: when the tablet cannot reach the server, the page stays as it is and the clock
 * and countdowns freeze. Make that visible instead of silently showing stale data. ES5 only.
 *
 * Every HTMX poll reports the connection state: a request that fails on the network or times out
 * sets `offline` on <body>, any response from the server clears it. HTMX keeps polling meanwhile,
 * so the dashboard recovers on its own.
 *
 * Markup contract (index.html):
 *   [data-offline-since]  filled with the last clock time shown, i.e. the last successful update
 */
(function () {
  "use strict";

  // Longer than the slowest widget request (upstream fetches with a 10 s timeout each),
  // short enough that a hanging connection is noticed
  htmx.config.timeout = 30000;

  var offline = false;

  function setOffline(value) {
    if (value === offline) {
      return;
    }
    offline = value;
    if (offline) {
      var clock = document.querySelector(".clock-time");
      var since = document.querySelector("[data-offline-since]");
      if (clock && since) {
        since.textContent = clock.textContent;
      }
      document.body.className += " offline";
    } else {
      document.body.className = document.body.className.replace(/\s*\boffline\b/g, "");
    }
  }

  document.addEventListener("htmx:sendError", function () {
    setOffline(true);
  });
  document.addEventListener("htmx:timeout", function () {
    setOffline(true);
  });
  document.addEventListener("htmx:afterOnLoad", function () {
    setOffline(false);
  });
})();
