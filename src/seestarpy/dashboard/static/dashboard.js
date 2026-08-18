/* Seestar dashboard front end.
 *
 * Listens to /api/events (Server-Sent Events, one fleet snapshot a second)
 * and keeps one card per Seestar up to date.  Cards are built once from the
 * <template> and then updated in place, so the <img> element survives every
 * refresh — replacing it wholesale would make each card blink.
 *
 * Frames are versioned by `frame_seq`.  When it changes the new JPEG is
 * decoded off-screen first and only swapped in once it is ready, which keeps
 * the swap instant instead of showing an empty box mid-download.
 */

(function () {
  "use strict";

  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  const template = document.getElementById("card-template");
  const fleetCount = document.getElementById("fleet-count");
  const linkState = document.getElementById("link-state");
  const scanned = document.getElementById("scanned");

  /** sn -> {root, els, seq} */
  const cards = new Map();
  let cardOrder = "";

  const DASH = "—";

  // ---------------------------------------------------------------- format

  function has(value) {
    return value !== null && value !== undefined && value !== "";
  }

  /** Write a value plus an optional dimmed sub-note into a <dd>. */
  function set(dd, value, sub, tone) {
    dd.className = "";
    if (!has(value)) {
      dd.textContent = DASH;
      dd.classList.add("is-none");
      return;
    }
    dd.textContent = value;
    if (has(sub)) {
      const span = document.createElement("span");
      span.className = "sub";
      span.textContent = "  " + sub;
      dd.appendChild(span);
    }
    if (tone) dd.classList.add("is-" + tone);
  }

  function fmtSeconds(s) {
    if (!has(s)) return null;
    if (s < 90) return Math.round(s) + " s";
    if (s < 5400) return (s / 60).toFixed(1) + " min";
    const hours = Math.floor(s / 3600);
    return hours + " h " + Math.round((s % 3600) / 60) + " m";
  }

  function fmtExposure(s) {
    if (!has(s)) return null;
    return (s < 1 ? s.toFixed(2) : String(+s.toFixed(1))) + " s";
  }

  function signed(value, digits) {
    const text = Math.abs(value).toFixed(digits);
    return (value < 0 ? "−" : "+") + text;
  }

  // ------------------------------------------------------------ status pill

  /** Decide the header pill: what is this scope doing right now? */
  function statusOf(s) {
    if (!s.connected) return { tone: "critical", text: "offline" };
    if (has(s.view_error) && s.view_error !== "no error") {
      return { tone: "serious", text: String(s.view_error).toLowerCase() };
    }
    const stage = has(s.view_stage) ? String(s.view_stage) : "";
    if (s.view_state === "working") {
      if (stage === "Stack") return { tone: "good", text: "stacking" };
      // Slewing, focusing, plate-solving: busy, but not a status alert —
      // hence the neutral accent rather than one of the status hues.
      return { tone: "busy", text: (stage || "working").toLowerCase() };
    }
    if (s.parked) return { tone: "muted", text: "parked" };
    return { tone: "muted", text: "idle" };
  }

  function setPill(el, tone, text) {
    el.className = "status pill pill-" + tone;
    el.querySelector(".pill-text").textContent = text;
  }

  // ------------------------------------------------------------------ card

  function buildCard(sn) {
    const root = template.content.firstElementChild.cloneNode(true);
    const q = (sel) => root.querySelector(sel);
    const stat = (key) => root.querySelector('[data-k="' + key + '"]');
    const els = {
      sn: q(".sn"),
      ip: q(".ip"),
      link: q(".link-badge"),
      status: q(".status"),
      frame: q(".frame"),
      img: q(".frame-img"),
      placeholder: q(".frame-placeholder"),
      tagLeft: q(".frame-tag-left"),
      tagRight: q(".frame-tag-right"),
      exp: stat("exp"),
      stacktime: stat("stacktime"),
      dropped: stat("dropped"),
      filter: stat("filter"),
      target: stat("target"),
      radec: stat("radec"),
      altaz: stat("altaz"),
      view: stat("view"),
      mount: stat("mount"),
      battery: stat("battery"),
      temp: stat("temp"),
      free: stat("free")
    };
    els.sn.textContent = sn;
    els.img.alt = "Live image from Seestar " + sn;
    const card = { root: root, els: els, seq: 0 };
    cards.set(sn, card);
    grid.appendChild(root);
    return card;
  }

  function updateCard(card, s) {
    const els = card.els;

    card.root.classList.toggle("offline", !s.connected);
    els.ip.textContent = s.ip || DASH;
    els.link.textContent = s.link ? s.link.toUpperCase() : "";
    els.link.style.display = s.link ? "" : "none";
    card.root.title = [s.model, s.dev_id, s.firmware && "fw " + s.firmware]
      .filter(Boolean).join("  ·  ");

    const status = statusOf(s);
    setPill(els.status, status.tone, status.text);

    // -- imaging -----------------------------------------------------------
    set(els.exp, fmtExposure(s.exp_s), has(s.gain) ? "gain " + s.gain : null);
    set(els.stacktime, fmtSeconds(s.stack_time_s),
        has(s.stacked_frames) ? s.stacked_frames + " subs" : null);

    let droppedTone = null;
    if (has(s.dropped_pct)) {
      if (s.dropped_pct >= 25) droppedTone = "critical";
      else if (s.dropped_pct >= 10) droppedTone = "serious";
    }
    set(els.dropped,
        has(s.dropped_pct) ? s.dropped_pct.toFixed(1) + " %" : null,
        has(s.dropped_frames) ? s.dropped_frames + " frames" : null,
        droppedTone);

    set(els.filter, s.filter, s.dither ? "dither " + s.dither : null);

    // -- pointing ----------------------------------------------------------
    set(els.target, s.target && s.target !== "Unknown" ? s.target : null);
    set(els.radec,
        has(s.ra) && has(s.dec)
          ? s.ra.toFixed(3) + " h  " + signed(s.dec, 2) + "°"
          : null);
    set(els.altaz,
        has(s.alt) && has(s.az)
          ? s.alt.toFixed(1) + "°  " + s.az.toFixed(1) + "°"
          : null,
        s.compass);
    set(els.view, s.view_state, s.view_stage);

    // -- housekeeping ------------------------------------------------------
    let mount = null;
    if (s.equ_mode === true) mount = "Equatorial";
    else if (s.equ_mode === false) mount = "Alt-Az";
    set(els.mount, mount, s.tracking === true ? "tracking" : null);

    let batteryTone = null;
    if (has(s.battery)) {
      if (s.battery < 15) batteryTone = "critical";
      else if (s.battery < 30) batteryTone = "warning";
    }
    set(els.battery, has(s.battery) ? s.battery + " %" : null,
        s.charging ? "charging" : null, batteryTone);

    let tempTone = null;
    if (has(s.temp_c) && s.temp_c >= 70) tempTone = "warning";
    set(els.temp, has(s.temp_c) ? s.temp_c.toFixed(1) + " °C" : null,
        null, tempTone);

    let freeTone = null;
    if (has(s.free_gb)) {
      if (s.free_gb < 2) freeTone = "critical";
      else if (s.free_gb < 5) freeTone = "warning";
    }
    set(els.free, has(s.free_gb) ? s.free_gb.toFixed(1) + " GB" : null,
        has(s.total_gb) ? "of " + s.total_gb.toFixed(0) : null, freeTone);

    updateImage(card, s);
  }

  function updateImage(card, s) {
    const els = card.els;

    if (has(s.frame_width) && has(s.frame_height) && s.frame_height > 0) {
      els.frame.style.aspectRatio = s.frame_width + " / " + s.frame_height;
    }

    if (s.frame_kind) {
      // The transfer mode explains why one card refreshes in seconds and
      // another in half a minute: JPG is ~2.5 MB a frame, RAW ~50 MB.
      const mode = s.transfer_mode ? " · " + s.transfer_mode.toUpperCase() : "";
      els.tagLeft.textContent =
        (s.frame_kind === "stacked" ? "STACKED" : "LIVE") + mode;
      els.tagLeft.classList.toggle("stacked", s.frame_kind === "stacked");
    }
    if (has(s.frame_age_s)) {
      els.tagRight.textContent = fmtSeconds(s.frame_age_s) + " ago";
    }
    // Explain an empty panel rather than leaving it blank: "no image" is
    // usually the scope refusing a second stream client, not a dead card.
    if (!s.frame_seq) {
      if (!s.connected) {
        els.placeholder.textContent = "no connection";
      } else if (s.image_error) {
        els.placeholder.textContent = "no image stream\n" + s.image_error;
      } else {
        els.placeholder.textContent = "waiting for frame…";
      }
    }

    if (!s.frame_seq || s.frame_seq === card.seq) return;
    card.seq = s.frame_seq;

    // Decode off-screen, then swap: assigning straight to the live <img>
    // would blank the card for the length of the download.
    const url = "/api/image/" + encodeURIComponent(s.sn) + "?s=" + s.frame_seq;
    const pre = new Image();
    pre.onload = function () {
      els.img.src = url;
      els.frame.classList.add("has-image");
    };
    pre.src = url;
  }

  // ---------------------------------------------------------------- render

  function render(snapshot) {
    const scopes = snapshot.scopes || [];
    const seen = new Set();

    scopes.forEach(function (s) {
      seen.add(s.sn);
      const card = cards.get(s.sn) || buildCard(s.sn);
      updateCard(card, s);
    });

    // Drop cards for scopes the server no longer tracks.
    cards.forEach(function (card, sn) {
      if (!seen.has(sn)) {
        card.root.remove();
        cards.delete(sn);
      }
    });

    // Keep the DOM in the server's (serial-number) order, so a scope holds
    // its place in the grid when another one joins.
    const order = scopes.map(function (s) { return s.sn; }).join(",");
    if (order !== cardOrder) {
      cardOrder = order;
      scopes.forEach(function (s) { grid.appendChild(cards.get(s.sn).root); });
    }

    const online = scopes.filter(function (s) { return s.connected; }).length;
    fleetCount.textContent = scopes.length
      ? online + " of " + scopes.length + " online"
      : "";
    empty.classList.toggle("show", scopes.length === 0);

    if (snapshot.scanned_at) {
      const ago = Math.max(0, Math.round(snapshot.server_time - snapshot.scanned_at));
      scanned.textContent = "Last network scan " + fmtSeconds(ago) + " ago";
    }
  }

  // ------------------------------------------------------------------ feed

  function setLink(tone, text) {
    linkState.className = "pill pill-" + tone;
    linkState.querySelector(".pill-text").textContent = text;
  }

  function connect() {
    const source = new EventSource("/api/events");

    source.onopen = function () { setLink("good", "live"); };

    source.onmessage = function (event) {
      try {
        render(JSON.parse(event.data));
      } catch (err) {
        console.error("[dashboard] bad snapshot", err);
      }
    };

    // EventSource reconnects on its own; just say so while it is down.
    source.onerror = function () { setLink("critical", "reconnecting"); };
  }

  connect();
})();
