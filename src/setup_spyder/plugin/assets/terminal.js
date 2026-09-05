/* Glue between xterm.js and the Python side of the AI Terminal.
 *
 * Everything is local to the page: the transport is Qt's QWebChannel, exposed
 * by the host as `qt.webChannelTransport`. The Python object registered as
 * `bridge` offers:
 *
 *   slots    send_input(text)  resize(rows, cols)  ready(rows, cols)  bell()
 *   signals  sig_output(text)  sig_clear(reset)  sig_options(json)  sig_focus()
 */
(function () {
  "use strict";

  var options = window.AI_TERMINAL_OPTIONS || {};
  var container = document.getElementById("terminal");

  var term = new Terminal({
    cursorBlink: true,
    cursorStyle: "block",
    scrollback: options.scrollback || 5000,
    fontFamily: options.fontFamily || "monospace",
    fontSize: options.fontSize || 13,
    lineHeight: options.lineHeight || 1.15,
    theme: options.theme || {},
    allowProposedApi: false,
    convertEol: false,
    windowsMode: !!options.windowsMode,
  });
  var fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(container);

  var bridge = null;
  var fitFrame = null;

  function applyPageTheme(theme) {
    if (theme.background) {
      document.body.style.background = theme.background;
      container.style.setProperty("--terminal-background", theme.background);
    }
    container.style.setProperty("--terminal-scrollbar",
      theme.selectionBackground || theme.foreground || "currentColor");
  }

  applyPageTheme(options.theme || {});

  // Diagnostics hook (used by tests and by the Python side); not an API.
  window.aiTerminal = { term: term, fit: fit };
  window.addEventListener("error", function (event) {
    if (bridge) { bridge.log("error: " + event.message); }
  });

  function doFit() {
    if (!container.clientWidth || !container.clientHeight) { return; }
    try {
      fit.fit();
    } catch (err) {
      /* the container may not be laid out yet */
    }
  }

  // Dock resizing can emit several events in one frame. Keep PTY geometry
  // in step with the rendered terminal without repeating layout work.
  function scheduleFit() {
    if (fitFrame !== null) { return; }
    fitFrame = window.requestAnimationFrame(function () {
      fitFrame = null;
      doFit();
    });
  }

  function applyOptions(json) {
    var next;
    try {
      next = JSON.parse(json);
    } catch (err) {
      return;
    }
    if (next.fontFamily) { term.options.fontFamily = next.fontFamily; }
    if (next.fontSize) { term.options.fontSize = next.fontSize; }
    if (next.lineHeight) { term.options.lineHeight = next.lineHeight; }
    if (next.theme) { term.options.theme = next.theme; }
    if (next.scrollback) { term.options.scrollback = next.scrollback; }
    if (next.theme) { applyPageTheme(next.theme); }
    scheduleFit();
    if (document.fonts) { document.fonts.ready.then(scheduleFit); }
  }

  // Ctrl+Shift+C copies the selection; Ctrl+C itself must reach the child as
  // \x03. Paste keeps the browser behaviour (Ctrl+V, Shift+Insert, context
  // menu), which xterm.js routes through onData.
  term.attachCustomKeyEventHandler(function (event) {
    if (event.type === "keydown" && event.ctrlKey && event.shiftKey &&
        (event.key === "C" || event.key === "c")) {
      if (term.hasSelection()) {
        document.execCommand("copy");
      }
      return false;
    }
    return true;
  });

  new QWebChannel(qt.webChannelTransport, function (channel) {
    bridge = channel.objects.bridge;

    bridge.sig_output.connect(function (text) {
      term.write(text);
    });
    bridge.sig_clear.connect(function (reset) {
      if (reset) {
        term.reset();
      } else {
        term.clear();
      }
    });
    bridge.sig_options.connect(applyOptions);
    bridge.sig_focus.connect(function () {
      term.focus();
    });

    term.onData(function (data) {
      bridge.send_input(data);
    });
    term.onResize(function (size) {
      bridge.resize(size.rows, size.cols);
    });
    term.onBell(function () {
      bridge.bell();
    });

    doFit();
    bridge.ready(term.rows, term.cols);
  });

  window.addEventListener("resize", scheduleFit);
  document.addEventListener("visibilitychange", scheduleFit);
  if (window.ResizeObserver) {
    new ResizeObserver(scheduleFit).observe(container);
  }
  if (document.fonts) {
    document.fonts.ready.then(scheduleFit);
    document.fonts.addEventListener("loadingdone", scheduleFit);
  }
  container.addEventListener("mousedown", function () {
    term.focus();
  });
})();
