document.addEventListener("DOMContentLoaded", function () {
  // Create WebSocket connection
  const isSecure = window.location.protocol === "https:";
  const wsProtocol = isSecure ? "wss" : "ws";

  const wsUrl = `${wsProtocol}://${window.location.host}/ws-screen-status`;
  const socket = new WebSocket(wsUrl);

  // Connection opened
  socket.addEventListener("open", (event) => {
    console.log("Connected to WebSocket server");
  });

  // Listen for messages
  socket.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "screen_status_update") {
      updateScreenStatus(data.screen_id, data.connected, data.client_host);
    }
  });

  // Connection closed
  socket.addEventListener("close", (event) => {
    console.log("Disconnected from WebSocket server");
    // Attempt to reconnect after 5 seconds
    setTimeout(() => {
      console.log("Attempting to reconnect...");
      window.location.reload();
    }, 5000);
  });

  // Connection error
  socket.addEventListener("error", (event) => {
    console.error("WebSocket error:", event);
  });

  // Function to update screen status in the UI
  function updateScreenStatus(screenId, isConnected, clientHost) {
    const notConnectedEl = document.getElementById("screen_not_connected_" + screenId);
    const connectedEl = document.getElementById("screen_connected_" + screenId);
    const hostEl = document.getElementById("screen_host_" + screenId);
    if (isConnected) {
      if (notConnectedEl) notConnectedEl.style.display = "none";
      document
        .getElementById("update_screen_section_" + screenId)
        .classList.remove("hidden");
      document.getElementById("update_section_" + screenId).style.display =
        "block";
      if (connectedEl) {
        connectedEl.style.display = "inline";
        if (clientHost) {
          const sshHref =
            "/admin/ssh.bat?host=" + encodeURIComponent(clientHost);
          const tip =
            "Download a .bat to open CMD with `wsl ssh screen@" +
            clientHost +
            "` (password: screen)";
          connectedEl.innerHTML =
            'Connected <span id="screen_host_' + screenId + '">(' + clientHost + ')</span>' +
            ' <a href="' + sshHref + '" download class="ml-1 text-blue-700 text-xs select-all hover:underline" title="' + tip + '">ssh screen@' + clientHost + '</a>';
        } else {
          connectedEl.innerHTML = 'Connected <span id="screen_host_' + screenId + '"></span>';
        }
      }
    } else {
      if (notConnectedEl) notConnectedEl.style.display = "inline";
      document
        .getElementById("update_screen_section_" + screenId)
        .classList.add("hidden");
      if (connectedEl) connectedEl.style.display = "none";
      if (hostEl) hostEl.textContent = "";
    }
  }
});
