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
      updateScreenStatus(data.screen_id, data.connected);
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
  function updateScreenStatus(screenId, isConnected) {
    // Add new status based on isConnected
    if (isConnected) {
      document.getElementById(
        "screen_not_connected_" + screenId
      ).style.display = "none";
      document
        .getElementById("update_screen_section_" + screenId)
        .classList.remove("hidden");

      // Also enable the update button for this screen
      document.getElementById("update_section_" + screenId).style.display =
        "block";
    } else {
      document.getElementById(
        "screen_not_connected_" + screenId
      ).style.display = "block";

      document
        .getElementById("update_screen_section_" + screenId)
        .classList.add("hidden");

      // Disable the update button for this screen
    }
  }
});
