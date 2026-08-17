import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import widget_repo
from app.schemas.widget import WidgetConfigOut

router = APIRouter(tags=["delivery"])


@router.get("/widgets/{widget_id}/config", response_model=WidgetConfigOut)
def get_widget_config(widget_id: uuid.UUID, response: Response, db: Session = Depends(get_db)):
    widget = widget_repo.get_public(db, widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="widget not found")

    # Short-lived cache: config can change (owner edits title/fields), but
    # we don't need every render to hit the DB.
    response.headers["Cache-Control"] = "public, max-age=60"
    return WidgetConfigOut(
        id=widget.id,
        type=widget.type,
        title=widget.title,
        description=widget.description,
        fields=widget.fields,
        button_text=widget.button_text,
        display_options=widget.display_options,
        bundle_version=widget.bundle_version,
    )


@router.get("/widget.js")
def get_widget_bundle():
    """The loader script every customer pastes onto their site. It reads
    its own ?id=, fetches /widgets/{id}/config, and renders a minimal form.
    Served with an aggressively long, immutable cache — this file's content
    never changes for a given deployment; ship a new URL (e.g. widget.v2.js)
    to invalidate it, per the versioned-bundle pattern in DESIGN.md."""
    return Response(
        content=WIDGET_JS,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


WIDGET_JS = """
(function () {
  var script = document.currentScript;
  var url = new URL(script.src);
  var widgetId = url.searchParams.get("id");
  if (!widgetId) return;

  var apiBase = url.origin;

  // -- targeting rules (stretch goal, see DESIGN.md) --------------------

  function pathMatches(pattern, actualPath) {
    var escaped = pattern.replace(/[.+?^${}()|[\\]\\\\]/g, "\\\\$&");
    var regexStr = "^" + escaped.replace(/\\*/g, ".*") + "$";
    return new RegExp(regexStr).test(actualPath);
  }

  function shouldShowOnThisPath(targetPaths, actualPath) {
    if (!targetPaths || !targetPaths.length) return true;
    return targetPaths.some(function (p) { return pathMatches(p, actualPath); });
  }

  function seenKey(id) { return "flyrank_widget_seen_" + id; }

  function hasAlreadyBeenSeen(id) {
    try {
      return window.localStorage.getItem(seenKey(id)) === "1";
    } catch (e) {
      // localStorage can throw in private-browsing/blocked-cookie
      // contexts. Fail OPEN (show the widget) rather than crash the
      // customer's page — a targeting nicety must never break delivery.
      return false;
    }
  }

  function markAsSeen(id) {
    try {
      window.localStorage.setItem(seenKey(id), "1");
    } catch (e) {
      // same fail-open reasoning as above
    }
  }

  // -----------------------------------------------------------------------

  fetch(apiBase + "/widgets/" + widgetId + "/config")
    .then(function (r) { return r.json(); })
    .then(function (config) {
      var opts = config.display_options || {};

      if (opts.show_once_per_visitor && hasAlreadyBeenSeen(widgetId)) return;
      if (!shouldShowOnThisPath(opts.target_paths, window.location.pathname)) return;

      var delayMs = (opts.delay_seconds || 0) * 1000;
      setTimeout(function () {
        renderWidget(config);
        if (opts.show_once_per_visitor) markAsSeen(widgetId);
      }, delayMs);
    })
    .catch(function (err) { console.error("widget config failed to load", err); });

  function renderWidget(config) {
    var container = document.createElement("div");
    container.className = "flyrank-widget";

    var title = document.createElement("h3");
    title.textContent = config.title;
    container.appendChild(title);

    var form = document.createElement("form");

    // Honeypot: real visitors never see this field. Bots that auto-fill
    // every input on the page will fill it, tripping server-side spam
    // detection. Hidden via CSS, not `type="hidden"`, since some bots skip
    // hidden inputs but not visually-hidden ones.
    var honeypot = document.createElement("input");
    honeypot.name = "hp_field";
    honeypot.tabIndex = -1;
    honeypot.autocomplete = "off";
    honeypot.style.cssText = "position:absolute;left:-9999px;opacity:0;height:0;width:0;";
    form.appendChild(honeypot);

    (config.fields || []).forEach(function (field) {
      var input = document.createElement("input");
      input.name = field.name;
      input.placeholder = field.label;
      input.type = field.type === "email" ? "email" : "text";
      if (field.required) input.required = true;
      form.appendChild(input);
    });

    var submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = config.button_text || "Submit";
    form.appendChild(submit);

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = {};
      (config.fields || []).forEach(function (field) {
        data[field.name] = form.elements[field.name].value;
      });

      fetch(apiBase + "/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          widget_id: widgetId,
          data: data,
          hp_field: form.elements["hp_field"].value
        })
      })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
        .then(function (res) {
          if (res.ok) {
            container.innerHTML = "<p>Thanks! Your submission was received.</p>";
          } else {
            console.error("submission rejected", res.body);
          }
        })
        .catch(function (err) { console.error("submission failed", err); });
    });

    container.appendChild(form);
    script.parentNode.insertBefore(container, script.nextSibling);
  }
})();
"""
