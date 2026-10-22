/**
 * Sidebar panel for E-Ink ESL — styled like the standalone e-ink web tool.
 * Preview pixels come from the Python encoder via ``eink_esl/preview``.
 */
const PANELS = [
  { id: "bwr-154", label: '1.54" BWR', width: 200, height: 200 },
  { id: "bwry-154", label: '1.54" BWRY', width: 200, height: 200 },
  { id: "bwr-213", label: '2.13" BWR', width: 250, height: 122 },
  { id: "bw-213", label: '2.13" BW', width: 250, height: 122 },
  { id: "bwry-213", label: '2.13" BWRY', width: 250, height: 122 },
  { id: "bwr-266", label: '2.66" BWR', width: 296, height: 152 },
  { id: "bwry-266", label: '2.66" BWRY', width: 296, height: 152 },
  { id: "bwr-290", label: '2.90" BWR', width: 296, height: 128 },
  { id: "bwry-290", label: '2.90" BWRY', width: 296, height: 128 },
  { id: "bwr-350", label: '3.50" BWR', width: 384, height: 184 },
  { id: "bwry-350", label: '3.50" BWRY', width: 384, height: 184 },
  { id: "bwr-420", label: '4.20" BWR', width: 400, height: 300 },
  { id: "bwry-420", label: '4.20" BWRY', width: 400, height: 300 },
  { id: "bwr-750", label: '7.50" BWR', width: 800, height: 480 },
  { id: "bwry-750", label: '7.50" BWRY', width: 800, height: 480 },
];

const PANEL_BY_LABEL = Object.fromEntries(PANELS.map((p) => [p.label, p]));
const PROGRESS_EVENT = "eink_esl_transfer_progress";

class EinkEslPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._deviceId = null;
    this._source = null;
    this._dataUrl = null;
    this._objectUrl = null;
    this._busy = false;
    this._fit = "contain";
    this._mode = "floyd-steinberg";
    this._background = "white";
    this._unsubProgress = null;
    this._previewSeq = 0;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._renderShell();
      this._bind();
      void this._subscribeProgress();
    }
    this._refreshDevices();
  }

  disconnectedCallback() {
    if (typeof this._unsubProgress === "function") {
      this._unsubProgress();
      this._unsubProgress = null;
    }
  }

  connectedCallback() {
    if (this._hass && !this.shadowRoot.querySelector(".wrap")) {
      this._renderShell();
      this._bind();
      void this._subscribeProgress();
      this._refreshDevices();
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          overflow: auto;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          font-family: var(--paper-font-body1_-_font-family, system-ui, sans-serif);
        }
        * { box-sizing: border-box; }
        .wrap {
          width: min(1040px, calc(100% - 32px));
          margin: 0 auto;
          padding: 28px 0 48px;
        }
        header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          gap: 12px;
        }
        h1 { margin: 0; font-size: 1.4rem; font-weight: 600; }
        h2 { margin: 0; font-size: 1rem; font-weight: 600; }
        .device-name { color: var(--secondary-text-color); font-size: 0.9rem; }
        .device-name strong { color: var(--primary-text-color); font-weight: 600; }
        .layout {
          display: grid;
          grid-template-columns: minmax(0, 280px) minmax(0, 1fr);
          gap: 16px;
          align-items: start;
        }
        @media (max-width: 860px) {
          .layout { grid-template-columns: 1fr; }
        }
        .card {
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 14px;
          min-width: 0;
        }
        label {
          display: grid;
          gap: 4px;
          margin-top: 12px;
          font-size: 0.75rem;
          color: var(--secondary-text-color);
        }
        label:first-child { margin-top: 0; }
        select {
          width: 100%;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 4px;
          padding: 7px 28px 7px 8px;
          font: inherit;
        }
        .row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
        button {
          border: 1px solid var(--primary-text-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 4px;
          padding: 7px 10px;
          font: inherit;
          cursor: pointer;
        }
        button.primary {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border-color: transparent;
        }
        button:disabled { cursor: not-allowed; opacity: 0.4; }
        .drop {
          position: relative;
          margin-top: 16px;
          padding: 16px 10px;
          text-align: center;
          border: 1px dashed var(--divider-color);
          border-radius: 4px;
          overflow: hidden;
          min-width: 0;
        }
        .drop strong { display: block; }
        #file-label {
          display: block;
          margin-top: 4px;
          color: var(--secondary-text-color);
          font-size: 0.8rem;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 100%;
        }
        #file-label:empty { display: none; }
        .drop input {
          position: absolute;
          inset: 0;
          opacity: 0;
          cursor: pointer;
        }
        .stage-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .swatches { display: flex; gap: 6px; }
        .swatches i {
          width: 12px;
          height: 12px;
          border: 1px solid var(--divider-color);
          display: block;
        }
        .frame {
          margin-top: 8px;
          display: flex;
          justify-content: flex-start;
          align-items: flex-start;
          overflow: auto;
          max-width: 100%;
        }
        .placeholder { margin: 0; color: var(--secondary-text-color); }
        canvas {
          display: block;
          width: auto;
          height: auto;
          max-width: 100%;
          image-rendering: pixelated;
          image-rendering: crisp-edges;
          background: #fff;
          border: 1px solid var(--divider-color);
          flex-shrink: 0;
        }
        .meta, .status { margin: 10px 0 0; min-height: 1.2em; }
        .meta { color: var(--secondary-text-color); font-size: 0.85rem; }
        .progress {
          margin-top: 10px;
          height: 4px;
          background: var(--divider-color);
          overflow: hidden;
        }
        .progress[hidden] { display: none; }
        .progress > div {
          height: 100%;
          width: 0;
          background: var(--primary-color);
          transition: width 0.15s ease-out;
        }
        .empty {
          padding: 24px;
          text-align: center;
          color: var(--secondary-text-color);
        }
      </style>
      <div class="wrap">
        <header>
          <h1>E-ink</h1>
          <div class="device-name"><strong id="device-title">No label</strong></div>
        </header>
        <div class="empty" id="empty" hidden>
          No e-ink labels configured. Add one under Settings → Devices &amp; services → E-Ink ESL.
        </div>
        <div class="layout" id="layout">
          <section class="card">
            <label>
              Label
              <select id="device"></select>
            </label>
            <div class="drop">
              <input id="file" type="file" accept="image/*" />
              <strong>Drop image</strong>
              <span id="file-label"></span>
            </div>
            <label>
              Fit
              <select id="fit">
                <option value="contain">Fit</option>
                <option value="cover">Fill</option>
                <option value="stretch">Stretch</option>
              </select>
            </label>
            <label>
              Background
              <select id="background">
                <option value="white">White</option>
                <option value="black">Black</option>
              </select>
            </label>
            <label>
              Color
              <select id="mode">
                <option value="nearest">Nearest</option>
                <option value="floyd-steinberg" selected>Dither</option>
              </select>
            </label>
          </section>
          <section class="card">
            <div class="stage-head">
              <h2>Preview</h2>
              <div class="swatches" aria-hidden="true">
                <i style="background:#111"></i>
                <i style="background:#fff"></i>
                <i style="background:#e10600"></i>
                <i style="background:#ffe600"></i>
              </div>
            </div>
            <div class="frame">
              <p class="placeholder" id="placeholder">No image</p>
              <canvas id="preview" hidden></canvas>
            </div>
            <p class="meta" id="meta"></p>
            <div class="progress" id="progress" hidden><div id="progress-bar"></div></div>
            <p class="status" id="status" role="status"></p>
            <div class="row">
              <button type="button" class="primary" id="send" disabled>Send</button>
            </div>
          </section>
        </div>
      </div>
    `;
  }

  _bind() {
    const root = this.shadowRoot;
    root.getElementById("device").addEventListener("change", (event) => {
      this._deviceId = event.target.value || null;
      this._updateActions();
      this._schedulePreview();
      this._updateDeviceTitle();
    });
    root.getElementById("fit").addEventListener("change", (event) => {
      this._fit = event.target.value;
      this._schedulePreview();
    });
    root.getElementById("mode").addEventListener("change", (event) => {
      this._mode = event.target.value;
      this._schedulePreview();
    });
    root.getElementById("background").addEventListener("change", (event) => {
      this._background = event.target.value;
      this._schedulePreview();
    });
    root.getElementById("file").addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (file) this._loadFile(file);
    });
    root.getElementById("send").addEventListener("click", () => void this._send());
  }

  async _subscribeProgress() {
    if (!this._hass || this._unsubProgress) return;
    this._unsubProgress = await this._hass.connection.subscribeEvents(
      (event) => this._onProgressEvent(event),
      PROGRESS_EVENT
    );
  }

  _selectedAddress() {
    const device = this._eslDevices().find((item) => item.id === this._deviceId);
    if (!device) return null;
    const connection = (device.connections || []).find(
      (pair) => pair[0] === "bluetooth"
    );
    return connection ? String(connection[1]).toUpperCase() : null;
  }

  _onProgressEvent(event) {
    if (!this._busy) return;
    const data = event.data || {};
    const address = this._selectedAddress();
    if (address && data.address && data.address.toUpperCase() !== address) {
      return;
    }
    if (data.message) this._setStatus(data.message);
    const progress = this.shadowRoot.getElementById("progress");
    const bar = this.shadowRoot.getElementById("progress-bar");
    if (!progress || !bar) return;

    if (data.phase === "chunks" && data.total > 0) {
      progress.hidden = false;
      bar.style.width = `${Math.min(100, (100 * data.sent) / data.total)}%`;
    } else if (data.phase === "waiting" || data.phase === "encoding") {
      progress.hidden = false;
      bar.style.width = "15%";
    } else if (data.phase === "done") {
      progress.hidden = false;
      bar.style.width = "100%";
    } else if (data.phase === "display" || data.phase === "clear") {
      progress.hidden = false;
      bar.style.width = data.phase === "display" ? "95%" : "40%";
    }
  }

  _showProgressBusy() {
    const progress = this.shadowRoot.getElementById("progress");
    const bar = this.shadowRoot.getElementById("progress-bar");
    if (progress && bar) {
      progress.hidden = false;
      bar.style.width = "8%";
    }
  }

  _hideProgress() {
    const progress = this.shadowRoot.getElementById("progress");
    const bar = this.shadowRoot.getElementById("progress-bar");
    if (progress && bar) {
      progress.hidden = true;
      bar.style.width = "0%";
    }
  }

  _eslDevices() {
    const devices = this._hass?.devices || {};
    return Object.values(devices).filter((device) =>
      (device.identifiers || []).some((pair) => pair[0] === "eink_esl")
    );
  }

  _updateDeviceTitle() {
    const title = this.shadowRoot.getElementById("device-title");
    const device = this._eslDevices().find((item) => item.id === this._deviceId);
    title.textContent = device
      ? device.name_by_user || device.name || device.id
      : "No label";
  }

  _refreshDevices() {
    const select = this.shadowRoot.getElementById("device");
    const empty = this.shadowRoot.getElementById("empty");
    const layout = this.shadowRoot.getElementById("layout");
    if (!select) return;

    const list = this._eslDevices().sort((a, b) =>
      (a.name_by_user || a.name || "").localeCompare(b.name_by_user || b.name || "")
    );
    empty.hidden = list.length > 0;
    layout.hidden = list.length === 0;

    const previous = this._deviceId;
    select.innerHTML = "";
    for (const device of list) {
      const option = document.createElement("option");
      option.value = device.id;
      const model = device.model ? ` · ${device.model}` : "";
      option.textContent = `${device.name_by_user || device.name || device.id}${model}`;
      select.append(option);
    }
    if (list.length) {
      const still = list.some((device) => device.id === previous);
      this._deviceId = still ? previous : list[0].id;
      select.value = this._deviceId;
    } else {
      this._deviceId = null;
    }
    this._updateDeviceTitle();
    this._updateActions();
    this._schedulePreview();
  }

  _panelSize() {
    const device = this._eslDevices().find((item) => item.id === this._deviceId);
    const fromModel = device?.model && PANEL_BY_LABEL[device.model];
    if (fromModel) return fromModel;
    return PANEL_BY_LABEL['3.50" BWRY'] || PANELS[10];
  }

  _formatFileLabel(name, width, height) {
    const meta = `${width}×${height}`;
    if (name.length <= 36) return `${name} · ${meta}`;
    return `${name.slice(0, 16)}…${name.slice(-12)} · ${meta}`;
  }

  _loadFile(file) {
    if (!file.type.startsWith("image/")) {
      this._setStatus("Not an image.");
      return;
    }
    if (this._objectUrl) URL.revokeObjectURL(this._objectUrl);
    this._objectUrl = URL.createObjectURL(file);
    const reader = new FileReader();
    reader.onload = () => {
      this._dataUrl = String(reader.result);
      const image = new Image();
      image.onload = () => {
        this._source = image;
        const label = this.shadowRoot.getElementById("file-label");
        label.textContent = this._formatFileLabel(
          file.name,
          image.naturalWidth,
          image.naturalHeight
        );
        label.title = `${file.name} · ${image.naturalWidth}×${image.naturalHeight}`;
        this._schedulePreview();
        this._updateActions();
      };
      image.onerror = () => this._setStatus("Couldn't read the file.");
      image.src = this._objectUrl;
    };
    reader.onerror = () => this._setStatus("Couldn't read the file.");
    reader.readAsDataURL(file);
  }

  _schedulePreview() {
    window.clearTimeout(this._previewTimer);
    this._previewTimer = window.setTimeout(() => void this._drawPreview(), 120);
  }

  _sizeCanvasDisplay(canvas, width, height) {
    const frame = canvas.parentElement;
    const maxWidth = frame ? frame.clientWidth : width;
    let scale = Math.floor(maxWidth / width);
    if (scale < 1) {
      canvas.style.width = "100%";
      canvas.style.height = "auto";
      return;
    }
    const maxCssHeight = 480;
    while (scale > 1 && height * scale > maxCssHeight) {
      scale -= 1;
    }
    canvas.style.width = `${width * scale}px`;
    canvas.style.height = `${height * scale}px`;
  }

  async _drawPreview() {
    const canvas = this.shadowRoot.getElementById("preview");
    const placeholder = this.shadowRoot.getElementById("placeholder");
    const meta = this.shadowRoot.getElementById("meta");
    const size = this._panelSize();
    const seq = ++this._previewSeq;

    if (!this._source || !this._dataUrl || !this._deviceId || !this._hass) {
      canvas.hidden = true;
      placeholder.hidden = false;
      meta.textContent = `${size.width}×${size.height} · ${size.label}`;
      return;
    }

    placeholder.hidden = false;
    placeholder.textContent = "Encoding preview…";
    canvas.hidden = true;

    try {
      const result = await this._hass.connection.sendMessagePromise({
        type: "eink_esl/preview",
        device_id: this._deviceId,
        image: this._dataUrl,
        fit: this._fit,
        mode: this._mode,
        background: this._background,
      });
      if (seq !== this._previewSeq) return;

      const width = result.width;
      const height = result.height;
      const image = new Image();
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(new Error("Bad preview image"));
        image.src = `data:${result.content_type};base64,${result.content}`;
      });
      if (seq !== this._previewSeq) return;

      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) return;
      context.imageSmoothingEnabled = false;
      context.drawImage(image, 0, 0);
      this._sizeCanvasDisplay(canvas, width, height);
      canvas.hidden = false;
      placeholder.hidden = true;
      meta.textContent = `${width}×${height} · ${size.label} · ${
        this._mode === "nearest" ? "nearest" : "dither"
      }`;
    } catch (error) {
      if (seq !== this._previewSeq) return;
      canvas.hidden = true;
      placeholder.hidden = false;
      placeholder.textContent = "Preview failed";
      meta.textContent = error?.message || String(error);
    }
  }

  _updateActions() {
    const ready = Boolean(this._deviceId) && !this._busy;
    this.shadowRoot.getElementById("send").disabled = !(ready && this._source);
  }

  _setStatus(message) {
    this.shadowRoot.getElementById("status").textContent = message;
  }

  _setBusy(busy) {
    this._busy = busy;
    this._updateActions();
  }

  async _send() {
    if (!this._hass || !this._deviceId || !this._dataUrl) return;
    this._setBusy(true);
    this._showProgressBusy();
    this._setStatus("Starting…");
    try {
      await this._hass.callService("eink_esl", "upload_image", {
        device_id: this._deviceId,
        image: this._dataUrl,
        fit: this._fit,
        mode: this._mode,
        background: this._background,
      });
      this._setStatus("Sent.");
    } catch (error) {
      this._setStatus(error?.message || String(error));
    } finally {
      this._setBusy(false);
      window.setTimeout(() => this._hideProgress(), 800);
    }
  }
}

customElements.define("eink-esl-panel", EinkEslPanel);
