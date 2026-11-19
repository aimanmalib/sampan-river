// Copy the prize address. Labels and the reset delay come from the page (site/lang/*.json, config/site.json).
(function () {
  var button = document.querySelector("[data-copy]");
  if (!button) return;
  var source = document.getElementById(button.getAttribute("data-copy"));
  var status = document.querySelector(".copy-status");
  var label = button.textContent;
  var resetMs = parseInt(button.getAttribute("data-reset-ms"), 10) || 0;
  var timer = null;

  function selectAddress() {
    var range = document.createRange();
    range.selectNodeContents(source);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function say(text, buttonText) {
    status.textContent = text;
    button.textContent = buttonText;
    clearTimeout(timer);
    if (resetMs > 0) {
      timer = setTimeout(function () { status.textContent = ""; button.textContent = label; }, resetMs);
    }
  }

  function failed() {
    selectAddress();
    say(button.getAttribute("data-fail"), label);
  }

  button.addEventListener("click", function () {
    var text = source.textContent.trim();
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () {
        var done = button.getAttribute("data-done");
        say(done, done);
      }, failed);
    } else {
      failed();
    }
  });
})();
