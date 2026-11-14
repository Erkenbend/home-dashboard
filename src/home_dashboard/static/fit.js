/*
 * Fit widgets to the display: hide the least important rows until a widget's content fits
 * without scrolling. ES5 only (old Android WebViews).
 *
 * Markup contract (set by the widget templates):
 *   [data-fit]           a widget container with a fixed height (CSS: overflow hidden)
 *   [data-fit-priority]  a row that may be hidden; higher numbers go first, ties from the bottom.
 *                        Rows without the attribute are always shown.
 *   [data-fit-group]     a container (e.g. a day) that is hidden once all its rows are hidden
 */
(function () {
  "use strict";

  function overflows(widget) {
    return widget.scrollHeight > widget.clientHeight + 1;
  }

  function closestGroup(element, widget) {
    var node = element.parentNode;
    while (node && node !== widget) {
      if (node.hasAttribute && node.hasAttribute("data-fit-group")) {
        return node;
      }
      node = node.parentNode;
    }
    return null;
  }

  function allHidden(group) {
    var rows = group.querySelectorAll("[data-fit-priority]");
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].style.display !== "none") {
        return false;
      }
    }
    return rows.length > 0;
  }

  function fit(widget) {
    var rows = widget.querySelectorAll("[data-fit-priority]");
    var groups = widget.querySelectorAll("[data-fit-group]");
    var candidates = [];
    var i;
    for (i = 0; i < groups.length; i++) {
      groups[i].style.display = "";
    }
    for (i = 0; i < rows.length; i++) {
      rows[i].style.display = "";
      candidates.push({
        row: rows[i],
        priority: parseInt(rows[i].getAttribute("data-fit-priority"), 10) || 0,
        index: i
      });
    }
    candidates.sort(function (a, b) {
      return b.priority - a.priority || b.index - a.index;
    });
    for (i = 0; i < candidates.length && overflows(widget); i++) {
      var row = candidates[i].row;
      row.style.display = "none";
      var group = closestGroup(row, widget);
      if (group && allHidden(group)) {
        group.style.display = "none";
      }
    }
  }

  function fitAll() {
    var widgets = document.querySelectorAll("[data-fit]");
    for (var i = 0; i < widgets.length; i++) {
      fit(widgets[i]);
    }
  }

  window.dashboardFit = fitAll;

  document.addEventListener("DOMContentLoaded", fitAll);
  window.addEventListener("load", fitAll);
  window.addEventListener("resize", fitAll);
  window.addEventListener("orientationchange", fitAll);
  // HTMX replaced a widget's content (polling); the clock does not change the layout height.
  // afterSwap fires in the same task as the swap, so the browser never paints the unfitted
  // content (afterSettle comes only after htmx's settle delay, a timeout: visible flicker).
  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.target;
    if (target && target.hasAttribute && target.hasAttribute("data-fit")) {
      fit(target);
    }
  });
})();
