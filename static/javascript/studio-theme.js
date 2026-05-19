/* studio-theme.js — minimal dark/light toggle for the Studio redesign.
 *
 * Reads/writes localStorage["studio-theme"] ∈ {"dark","light"}.
 * Applies the choice by adding/removing `class="light"` on <html>.
 * Default is dark.
 *
 * Wire up the toggle by giving any element id="studio-theme-toggle";
 * clicking it flips the theme. The script writes a 🌙/☀ glyph into
 * the element so callers don't have to.
 */

(function () {
  const KEY = "studio-theme";

  function current() {
    return document.documentElement.classList.contains("light") ? "light" : "dark";
  }

  function apply(theme) {
    const html = document.documentElement;
    if (theme === "light") html.classList.add("light");
    else html.classList.remove("light");
    try {
      localStorage.setItem(KEY, theme);
    } catch (_) { /* private browsing or storage off — ignore */ }
    paintToggle();
  }

  function paintToggle() {
    const el = document.getElementById("studio-theme-toggle");
    if (!el) return;
    el.textContent = current() === "dark" ? "☀" : "☾";
    el.setAttribute(
      "title",
      current() === "dark" ? "Switch to light mode" : "Switch to dark mode"
    );
  }

  function toggle() {
    apply(current() === "dark" ? "light" : "dark");
  }

  function init() {
    let saved;
    try { saved = localStorage.getItem(KEY); } catch (_) { saved = null; }
    apply(saved === "light" ? "light" : "dark");
    const el = document.getElementById("studio-theme-toggle");
    if (el) el.addEventListener("click", toggle);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Public hook so future pages can drive the toggle programmatically.
  window.StudioTheme = { apply, toggle, current };
})();
