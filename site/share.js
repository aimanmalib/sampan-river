// Share the page: the phone's own share sheet when the browser has one, otherwise a small panel with copy link and
// links to X, WhatsApp and Telegram (built by tools/site.py from config/site.json). No third party script.
(function () {
  var root = document.querySelector("[data-share]");
  if (!root) return;
  var button = root.querySelector(".share-btn");
  var panel = root.querySelector(".share-panel");
  var copy = root.querySelector(".share-copy");
  var link = root.querySelector(".share-url");
  var status = root.querySelector(".share-status");
  var url = root.getAttribute("data-url");
  var copyLabel = copy.textContent;
  var resetMs = parseInt(copy.getAttribute("data-reset-ms"), 10) || 0;
  var timer = null;

  function setOpen(open) {
    panel.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function say(text, copyText) {
    status.textContent = text;
    copy.textContent = copyText;
    clearTimeout(timer);
    if (resetMs > 0) {
      timer = setTimeout(function () { status.textContent = ""; copy.textContent = copyLabel; }, resetMs);
    }
  }

  function selectLink() {
    var range = document.createRange();
    range.selectNodeContents(link);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function copyFailed() {
    selectLink();
    say(copy.getAttribute("data-fail"), copyLabel);
  }

  button.addEventListener("click", function () {
    if (navigator.share) {
      navigator.share({
        title: root.getAttribute("data-title"),
        text: root.getAttribute("data-text"),
        url: url
      }).catch(function (err) {
        // Closing the sheet is not an error; anything else falls back to the panel.
        if (!err || err.name !== "AbortError") setOpen(true);
      });
      return;
    }
    setOpen(panel.hidden);
  });

  copy.addEventListener("click", function () {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(function () {
        var done = copy.getAttribute("data-done");
        say(done, done);
      }, copyFailed);
    } else {
      copyFailed();
    }
  });
})();
