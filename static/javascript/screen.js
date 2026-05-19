let ws = null;
let connected = false;
let isConnecting = false;
let timer = null;
let contentWindow = null;

const connect = () => {
  if (isConnecting) {
    return;
  }
  isConnecting = true;
  connected = false;

  if (ws) {
    ws.onclose = null;
    ws.close();
  }

  ws = new WebSocket(window.ws_url);

  ws.onmessage = (event) => {
    console.log("Received WS message", event.data);

    // Server may include the screen's CURRENT content_url so we don't reuse
    // a stale window.contentUrl from when the frame first loaded. If absent,
    // fall back to the cached URL (backward-compatible with older payloads).
    let serverUrl = null;
    try {
      const msg = JSON.parse(event.data);
      if (msg && msg.content_url) serverUrl = msg.content_url;
    } catch (_) { /* not JSON — ignore */ }

    if (serverUrl) {
      // Resolve to absolute if it's a path
      if (serverUrl.startsWith("http://") || serverUrl.startsWith("https://")) {
        window.contentUrl = serverUrl;
      } else {
        window.contentUrl = window.location.origin + (serverUrl.startsWith("/") ? "" : "/") + serverUrl;
      }
    }

    const returnTo = encodeURIComponent(window.contentUrl || window.location.href);
    const updatingUrl = "/updating?return_to=" + returnTo;

    // Try the kept popup reference first, then re-acquire by window name.
    let popup = contentWindow && !contentWindow.closed ? contentWindow : null;
    if (!popup) {
      try {
        popup = window.open("", "contentWindow");
        if (popup && popup.location.href === "about:blank") {
          popup.close();
          popup = null;
        }
      } catch (e) {
        popup = null;
      }
    }

    if (popup && !popup.closed) {
      popup.location = updatingUrl;
    } else {
      window.location = updatingUrl;
    }
  };

  ws.onopen = () => {
    console.log("Connected to websocket server");
    connected = true;
    isConnecting = false;
    document
      .getElementById("connection_status_true")
      .classList.remove("hidden");
    document.getElementById("connection_status_false").classList.add("hidden");

    //hide connect button
    document.getElementById("connect_button").classList.add("hidden");

    //show update button
    document.getElementById("update_button").classList.remove("hidden");

    // clear the timer
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  };

  ws.onclose = () => {
    connected = false;
    isConnecting = false;
    document
      .getElementById("connection_status_false")
      .classList.remove("hidden");
    document.getElementById("connection_status_true").classList.add("hidden");

    //show connect button
    document.getElementById("connect_button").classList.remove("hidden");

    //hide update button
    document.getElementById("update_button").classList.add("hidden");

    // try to reconnect every 5 seconds, but only if there's no timer already
    if (!timer) {
      timer = setInterval(() => {
        if (!connected && !isConnecting) {
          connect();
        }
      }, 5000);
    }
  };
  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
    isConnecting = false;
  };
};

const reloadContentWindow = () => {
  console.log("Reloading content window with", window.contentUrl);

  //update the div with id content_url
  document.getElementById("content_url").innerText = window.contentUrl;

  // Close existing window if open
  if (contentWindow && !contentWindow.closed) {
    contentWindow.close();
  }
  // Open the new window with updated URL
  contentWindow = window.open(window.contentUrl, "contentWindow");
};

connect();

setTimeout(() => {
  console.log("Reloading content window after 1 second");
  console.log("Content URL:", window.contentUrl);
  reloadContentWindow();
}, 1000);
