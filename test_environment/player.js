/**
 * Toggle play/pause for the VoiceSync audio player.
 *
 * @param {HTMLButtonElement} btn The button element that was clicked.
 */
function vsToggle(btn) {
    const container = btn.closest('.voicesync-player');
    if (!container) return;

    const audio = container.querySelector('.vs-audio-element');
    const timeSpan = container.querySelector('.vs-time');
    if (!audio || !timeSpan) return;

    // Lazy load the audio source if not already set
    if (!audio.src || audio.src === "") {
        const dataSrc = container.getAttribute('data-src');
        if (dataSrc) {
            audio.src = dataSrc;
        }
    }

    // Toggle playback according to the requirements
    if (!audio.paused) {
        audio.pause();
        btn.innerHTML = "⏸ Duraklat";
    } else {
        audio.play();
        btn.innerHTML = "▶ Yazıyı Dinle";
    }

    // Update time status dynamically
    audio.ontimeupdate = function() {
        const current = audio.currentTime;
        const mins = Math.floor(current / 60);
        const secs = Math.floor(current % 60);
        timeSpan.innerHTML = mins + ":" + (secs < 10 ? "0" : "") + secs;
    };

    // Reset when audio finishes playing
    audio.onended = function() {
        btn.innerHTML = "▶ Yazıyı Dinle";
        timeSpan.innerHTML = "0:00";
    };
}
