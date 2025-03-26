// Extract YouTube video ID from URL
function getYoutubeIdFromUrl(url) {
  const regExp =
    /^.*((youtu.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*).*/;
  const match = url.match(regExp);
  return match && match[7].length === 11 ? match[7] : false;
}

// Load the YouTube IFrame Player API
var tag = document.createElement("script");
tag.src = "https://www.youtube.com/iframe_api";
var firstScriptTag = document.getElementsByTagName("script")[0];
firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

var player;

function onYouTubeIframeAPIReady() {
  console.log("YouTube IFrame API is ready");
  // Get the video ID from the URL passed in the template

  const videoId = getYoutubeIdFromUrl(window.videoUrl);

  if (!videoId) {
    document.getElementById("player").innerHTML = "Invalid YouTube URL";
    return;
  }

  player = new YT.Player("player", {
    videoId: videoId,
    playerVars: {
      autoplay: 1,
      mute: 1,
      controls: 0,
      showinfo: 0,
      rel: 0,
      modestbranding: 1,
      loop: 1,
      playlist: videoId, // Required for looping
    },
    events: {
      onReady: onPlayerReady,
      onStateChange: onPlayerStateChange,
    },
  });
}

function onPlayerReady(event) {
  console.log("Player is ready");
  event.target.playVideo();
}

function onPlayerStateChange(event) {
  console.log("Player state changed: ", event.data);

  // If video ends, restart it (for backup looping)
  if (event.data === YT.PlayerState.ENDED) {
    player.playVideo();
  }
}
