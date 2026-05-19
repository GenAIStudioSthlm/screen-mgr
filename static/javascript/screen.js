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

    // The server includes the screen's CURRENT content_url so we don't reuse
    // a stale window.contentUrl from when the frame first loaded.
    let serverUrl = null;
    try {
      const msg = JSON.parse(event.data);
      if (msg && msg.content_url) serverUrl = msg.content_url;
    } catch (_) { /* not JSON — ignore */ }

    let newUrl = window.contentUrl;
    if (serverUrl) {
      if (serverUrl.startsWith("http://") || serverUrl.startsWith("https://")) {
        newUrl = serverUrl;
      } else {
        newUrl = window.location.origin + (serverUrl.startsWith("/") ? "" : "/") + serverUrl;
      }
    }

    // If the content URL actually changed (e.g. scene swap, content edit) we
    // need a full FRAME reload so screen.html re-renders with the new
    // window.contentUrl AND we pick up any new screen.js too. Trying to
    // navigate the popup alone leaves the frame stuck on the old data.
    if (newUrl !== window.contentUrl) {
      console.log("content URL changed; reloading frame", { from: window.contentUrl, to: newUrl });
      window.location.reload();
      return;
    }

    // Same content — pure refresh. Use the /updating popup-dance for a
    // visible "Updating" beat then bounce back.
    const returnTo = encodeURIComponent(newUrl || window.location.href);
    const updatingUrl = "/updating?return_to=" + returnTo;

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
