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
    console.log("Received message3", event.data);
    window.location.reload();
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

const reloadContentWindow = (contentUrl) => {
  console.log("Reloading content window with", contentUrl);
  contentUrl = contentUrl || `{{content_url}}`;

  //update the div with id content_url
  document.getElementById("content_url").innerText = contentUrl;

  // Close existing window if open
  if (contentWindow && !contentWindow.closed) {
    contentWindow.close();
  }
  // Open the new window with updated URL
  contentWindow = window.open(contentUrl, "contentWindow");
};

connect();
setTimeout(() => {
  reloadContentWindow(window.content_url);
}, 1000);
