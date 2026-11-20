// Repository links appear only when the repository is public (decision 0015). The API URL and the repository name
// come from the page (config/site.json banner.repo_api, repo_url). A list of repositories (GitHub lists only public
// ones, and answers 200 either way, so a private repository leaves no failed request in the console) or a single
// repository is accepted. No answer, an error or a private repository: the links stay hidden.
(function () {
  var host = document.querySelector("[data-repo-api]");
  if (!host || !window.fetch) return;
  var name = (host.getAttribute("data-repo-name") || "").toLowerCase();

  function listed(data) {
    var repos = Array.isArray(data) ? data : [data];
    return repos.some(function (r) {
      return r && !r["private"] && String(r.full_name || "").toLowerCase() === name;
    });
  }

  fetch(host.getAttribute("data-repo-api"), {
    headers: { Accept: "application/vnd.github+json" },
    credentials: "omit",
    referrerPolicy: "no-referrer"
  }).then(function (res) {
    return res.status === 200 ? res.json() : null;
  }).then(function (data) {
    if (!data || !listed(data)) return;
    var gated = document.querySelectorAll("[data-repo-link]");
    for (var i = 0; i < gated.length; i++) gated[i].hidden = false;
  }).catch(function () {});
})();
