/* Copyright Advanced Software and AI Solutions LLC */
(function () {
  "use strict";

  var dropZone = document.getElementById("drop-zone");
  var fileInput = document.getElementById("file-input");
  var pagesInput = document.getElementById("pages-input");
  var forceOcr = document.getElementById("force-ocr");
  var uploadStatus = document.getElementById("upload-status");
  var progressSummary = document.getElementById("progress-summary");
  var pageList = document.getElementById("page-list");
  var resultText = document.getElementById("result-text");
  var copyBtn = document.getElementById("copy-btn");
  var copyLive = document.getElementById("copy-live");
  var copyVisible = document.getElementById("copy-visible");
  var healthBadge = document.getElementById("health-badge");
  var lmUrl = document.getElementById("lm-url");
  var modelId = document.getElementById("model-id");
  var modelSelect = document.getElementById("model-select");
  var listModelsBtn = document.getElementById("list-models-btn");
  var saveSettingsBtn = document.getElementById("save-settings-btn");
  var resetSettingsBtn = document.getElementById("reset-settings-btn");
  var settingsStatus = document.getElementById("settings-status");

  function setStatus(el, message, kind) {
    el.textContent = message || "";
    el.classList.remove("error", "ok");
    if (kind) {
      el.classList.add(kind);
    }
  }

  function api(path, options) {
    return fetch(path, options).then(async function (res) {
      var contentType = res.headers.get("content-type") || "";
      var body = null;
      if (contentType.indexOf("application/json") !== -1) {
        body = await res.json();
      } else {
        body = await res.text();
      }
      return { ok: res.ok, status: res.status, body: body, res: res };
    });
  }

  function refreshHealth() {
    return api("/api/health").then(function (result) {
      var body = result.body || {};
      var reachable = body.backend && body.backend.reachable;
      healthBadge.classList.remove("health-ok", "health-bad", "health-unknown");
      if (reachable) {
        healthBadge.classList.add("health-ok");
        var modelNote =
          body.model && body.model.available
            ? "Model available"
            : "Backend up (model not listed)";
        healthBadge.textContent = "Healthy: " + modelNote;
      } else {
        healthBadge.classList.add("health-bad");
        healthBadge.textContent = "LM Studio unreachable";
      }
    }).catch(function () {
      healthBadge.classList.remove("health-ok", "health-unknown");
      healthBadge.classList.add("health-bad");
      healthBadge.textContent = "Health check failed";
    });
  }

  function loadSettings() {
    return api("/api/settings").then(function (result) {
      if (!result.ok) {
        setStatus(settingsStatus, "Could not load settings.", "error");
        return;
      }
      lmUrl.value = result.body.lmstudioBaseUrl || "";
      modelId.value = result.body.modelId || "";
    });
  }

  function fillModelSelect(models) {
    modelSelect.innerHTML = "";
    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = models.length
      ? "Select a loaded model"
      : "No models returned";
    modelSelect.appendChild(placeholder);
    models.forEach(function (id) {
      var opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      modelSelect.appendChild(opt);
    });
  }

  listModelsBtn.addEventListener("click", function () {
    setStatus(settingsStatus, "Listing models...");
    api("/api/models")
      .then(function (result) {
        if (!result.ok) {
          var msg =
            (result.body && result.body.error && result.body.error.message) ||
            "Could not list models.";
          setStatus(settingsStatus, msg, "error");
          return;
        }
        fillModelSelect(result.body.models || []);
        setStatus(settingsStatus, "Models updated.", "ok");
      })
      .catch(function () {
        setStatus(settingsStatus, "Could not list models.", "error");
      });
  });

  modelSelect.addEventListener("change", function () {
    if (modelSelect.value) {
      modelId.value = modelSelect.value;
    }
  });

  saveSettingsBtn.addEventListener("click", function () {
    setStatus(settingsStatus, "Saving...");
    api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lmstudioBaseUrl: lmUrl.value,
        modelId: modelId.value,
      }),
    })
      .then(function (result) {
        if (!result.ok) {
          var msg =
            (result.body && result.body.error && result.body.error.message) ||
            "Save failed.";
          setStatus(settingsStatus, msg, "error");
          return;
        }
        lmUrl.value = result.body.lmstudioBaseUrl;
        modelId.value = result.body.modelId;
        setStatus(settingsStatus, "Settings saved.", "ok");
        refreshHealth();
      })
      .catch(function () {
        setStatus(settingsStatus, "Save failed.", "error");
      });
  });

  resetSettingsBtn.addEventListener("click", function () {
    setStatus(settingsStatus, "Resetting...");
    api("/api/settings", { method: "DELETE" })
      .then(function (result) {
        if (!result.ok) {
          setStatus(settingsStatus, "Reset failed.", "error");
          return;
        }
        lmUrl.value = result.body.lmstudioBaseUrl;
        modelId.value = result.body.modelId;
        setStatus(settingsStatus, "Defaults restored from .env.", "ok");
        refreshHealth();
      })
      .catch(function () {
        setStatus(settingsStatus, "Reset failed.", "error");
      });
  });

  function clearResults() {
    pageList.innerHTML = "";
    resultText.value = "";
    copyBtn.disabled = true;
    copyLive.textContent = "";
    copyVisible.textContent = "";
  }

  function addPageRow(event) {
    var li = document.createElement("li");
    var label = document.createElement("strong");
    label.textContent = "Page " + event.page;
    var tag = document.createElement("span");
    tag.className = "tag " + (event.error ? "error" : event.source);
    tag.textContent = event.error ? "error" : event.source;
    li.appendChild(label);
    li.appendChild(tag);
    if (event.error) {
      var err = document.createElement("span");
      err.textContent = event.error;
      li.appendChild(err);
    }
    pageList.appendChild(li);
  }

  function copyTextFallback(text) {
    resultText.focus();
    resultText.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    window.getSelection().removeAllRanges();
    return ok;
  }

  copyBtn.addEventListener("click", function () {
    var text = resultText.value;
    function announce(ok) {
      var msg = ok ? "Copied" : "Copy failed";
      copyLive.textContent = msg;
      copyVisible.textContent = msg;
      copyVisible.classList.toggle("ok", ok);
      copyVisible.classList.toggle("error", !ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          announce(true);
        },
        function () {
          announce(copyTextFallback(text));
        }
      );
    } else {
      announce(copyTextFallback(text));
    }
  });

  function processFile(file) {
    if (!file) {
      return;
    }
    clearResults();
    setStatus(uploadStatus, "Uploading and extracting...");
    progressSummary.textContent = "Working on " + file.name + "...";

    var form = new FormData();
    form.append("file", file, file.name);
    if (pagesInput.value.trim()) {
      form.append("pages", pagesInput.value.trim());
    }
    if (forceOcr.checked) {
      form.append("forceOcr", "true");
    }

    fetch("/api/extract", {
      method: "POST",
      headers: { Accept: "application/x-ndjson" },
      body: form,
    })
      .then(async function (res) {
        if (!res.ok) {
          var errBody = null;
          try {
            errBody = await res.json();
          } catch (e) {
            errBody = null;
          }
          var msg =
            (errBody && errBody.error && errBody.error.message) ||
            "Extraction failed (" + res.status + ").";
          setStatus(uploadStatus, msg, "error");
          progressSummary.textContent = "Failed.";
          return;
        }

        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        var pageCountSeen = 0;

        while (true) {
          var chunk = await reader.read();
          if (chunk.done) {
            break;
          }
          buffer += decoder.decode(chunk.value, { stream: true });
          var lines = buffer.split("\n");
          buffer = lines.pop() || "";
          lines.forEach(function (line) {
            if (!line.trim()) {
              return;
            }
            var event;
            try {
              event = JSON.parse(line);
            } catch (e) {
              return;
            }
            if (event.type === "page") {
              pageCountSeen += 1;
              addPageRow(event);
              progressSummary.textContent =
                "Page " + pageCountSeen + " finished (" + (event.source || "") + ")";
            } else if (event.type === "done") {
              resultText.value = event.text || "";
              copyBtn.disabled = !resultText.value;
              progressSummary.textContent =
                "Done. " +
                (event.pages ? event.pages.length : pageCountSeen) +
                " page(s) in " +
                (event.durationMs || 0) +
                " ms.";
              setStatus(uploadStatus, "Extraction complete.", "ok");
            }
          });
        }
      })
      .catch(function () {
        setStatus(uploadStatus, "Network error during extraction.", "error");
        progressSummary.textContent = "Failed.";
      });
  }

  fileInput.addEventListener("change", function () {
    var file = fileInput.files && fileInput.files[0];
    processFile(file);
    fileInput.value = "";
  });

  dropZone.addEventListener("click", function (event) {
    if (event.target.closest("label") || event.target === fileInput) {
      return;
    }
    fileInput.click();
  });

  dropZone.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  });

  ["dragenter", "dragover"].forEach(function (name) {
    dropZone.addEventListener(name, function (event) {
      event.preventDefault();
      dropZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach(function (name) {
    dropZone.addEventListener(name, function (event) {
      event.preventDefault();
      dropZone.classList.remove("dragover");
    });
  });

  dropZone.addEventListener("drop", function (event) {
    var file = event.dataTransfer && event.dataTransfer.files[0];
    processFile(file);
  });

  loadSettings().then(refreshHealth);
  setInterval(refreshHealth, 15000);
})();
