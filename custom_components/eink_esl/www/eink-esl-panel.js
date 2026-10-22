/**
 * Sidebar panel for E-Ink ESL — device picker, image preview, send / clear.
 * Receives the live `hass` object from Home Assistant (not an iframe).
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

class EinkEslPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._deviceId = null;
    this._source = null;
    this._objectUrl = null;
    this._busy = false;
    this._fit = "contain";
    this._mode = "floyd-steinberg";
    this._background = "#ffffff";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._renderShell();
      this._bind();
    }
    this._refreshDevices();
  }

  connectedCallback() {
    if (this._hass && !this.shadowRoot.querySelector(".wrap")) {
      this._renderShell();
      this._bind();
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
          background: var(--primary-background-color, #f3f3f1);
          color: var(--primary-text-color, #1a1a1a);
          font-family: var(--paper-font-body1_-_font-family, system-ui, sans-serif);
        }
        .wrap {
          width: min(1040px, calc(100% - 32px));
          margin: 0 auto;
          padding: 24px 0 48px;
        }
        header {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 12px;
          margin-bottom: 16px;
        }
        h1 { margin: 0; font-size: 1.35rem; font-weight: 600; }
        .hint { color: var(--secondary-text-color, #6b6b66); font-size: 0.9rem; }
        .layout {
          display: grid;
          grid-template-columns: 280px 1fr;
          gap: 16px;
          align-items: start;
        }
        @media (max-width: 800px) {
          .layout { grid-template-columns: 1fr; }
        }
        .card {
          background: var(--card-background-color, #fff);
          border: 1px solid var(--divider-color, #d8d8d4);
          border-radius: 8px;
          padding: 14px;
        }
        label { display: grid; gap: 4px; margin-top: 12px; font-size: 0.75rem; color: var(--secondary-text-color, #6b6b66); }
        label:first-child { margin-top: 0; }
        select, input[type="file"] {
          width: 100%;
          border: 1px solid var(--divider-color, #d8d8d4);
          background: var(--primary-background-color, #fff);
          color: inherit;
          border-radius: 4px;
          padding: 7px 8px;
          font: inherit;
        }
        .row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
        button {
          border: 1px solid var(--primary-text-color, #1a1a1a);
          background: var(--card-background-color, #fff);
          color: inherit;
          border-radius: 4px;
          padding: 7px 10px;
          font: inherit;
          cursor: pointer;
        }
        button.primary {
          background: var(--primary-color, #1a1a1a);
          color: var(--text-primary-color, #fff);
          border-color: transparent;
        }
        button:disabled { opacity: 0.4; cursor: not-allowed; }
        .drop {
          position: relative;
          margin-top: 16px;
          padding: 18px 10px;
          text-align: center;
          border: 1px dashed var(--divider-color, #d8d8d4);
          border-radius: 6px;
        }
        .drop input {
          position: absolute;
          inset: 0;
          opacity: 0;
          cursor: pointer;
        }
        .frame {
          position: relative;
          min-height: 160px;
          display: grid;
          place-items: center;
          background:
            linear-gradient(45deg, #e8e8e4 25%, transparent 25%),
            linear-gradient(-45deg, #e8e8e4 25%, transparent 25%),
            linear-gradient(45deg, transparent 75%, #e8e8e4 75%),
            linear-gradient(-45deg, transparent 75%, #e8e8e4 75%);
          background-size: 16px 16px;
          background-position: 0 0, 0 8px, 8px -8px, -8px 0;
          border-radius: 4px;
          overflow: auto;
        }
        canvas {
          max-width: 100%;
          image-rendering: pixelated;
          background: #fff;
        }
        .placeholder { color: var(--secondary-text-color, #6b6b66); }
        .status { min-height: 1.2em; margin: 10px 0 0; font-size: 0.9rem; }
        .meta { margin: 8px 0 0; font-size: 0.8rem; color: var(--secondary-text-color, #6b6b66); }
        .empty {
          padding: 24px;
          text-align: center;
          color: var(--secondary-text-color, #6b6b66);
        }
      </style>
      <div class="wrap">
        <header>
          <h1>E-Ink ESL</h1>
          <span class="hint">Preview is approximate; the tag receives quantized colors.</span>
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
            <label>
              Fit
              <select id="fit">
                <option value="contain">Fit</option>
                <option value="cover">Fill</option>
                <option value="stretch">Stretch</option>
              </select>
            </label>
            <label>
              Color
              <select id="mode">
                <option value="nearest">Nearest</option>
                <option value="floyd-steinberg" selected>Dither</option>
              </select>
            </label>
            <label>
              Background
              <select id="background">
                <option value="#ffffff">White</option>
                <option value="#000000">Black</option>
              </select>
            </label>
            <div class="drop">
              <input id="file" type="file" accept="image/*" />
              <strong>Drop or choose image</strong>
              <div id="file-label"></div>
            </div>
          </section>
          <section class="card">
            <div class="frame">
              <p class="placeholder" id="placeholder">No image</p>
              <canvas id="preview" hidden></canvas>
            </div>
            <p class="meta" id="meta"></p>
            <p class="status" id="status" role="status"></p>
            <div class="row">
              <button type="button" class="primary" id="send" disabled>Send</button>
              <button type="button" id="clear-white" disabled>Clear white</button>
              <button type="button" id="clear-black" disabled>Clear black</button>
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
    });
    root.getElementById("fit").addEventListener("change", (event) => {
      this._fit = event.target.value;
      this._schedulePreview();
    });
    root.getElementById("mode").addEventListener("change", (event) => {
      this._mode = event.target.value;
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
    root.getElementById("clear-white").addEventListener("click", () => void this._clear("white"));
    root.getElementById("clear-black").addEventListener("click", () => void this._clear("black"));
  }

  _eslDevices() {
    const devices = this._hass?.devices || {};
    return Object.values(devices).filter((device) =>
      (device.identifiers || []).some((pair) => pair[0] === "eink_esl")
    );
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
    this._updateActions();
    this._schedulePreview();
  }

  _panelSize() {
    const device = this._eslDevices().find((item) => item.id === this._deviceId);
    const fromModel = device?.model && PANEL_BY_LABEL[device.model];
    if (fromModel) return fromModel;
    return PANEL_BY_LABEL['3.50" BWRY'] || PANELS[10];
  }

  _loadFile(file) {
    if (!file.type.startsWith("image/")) {
      this._setStatus("Not an image.");
      return;
    }
    if (this._objectUrl) URL.revokeObjectURL(this._objectUrl);
    this._objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      this._source = image;
      this.shadowRoot.getElementById("file-label").textContent =
        `${file.name} · ${image.naturalWidth}×${image.naturalHeight}`;
      this._schedulePreview();
      this._updateActions();
    };
    image.onerror = () => this._setStatus("Couldn't read the file.");
    image.src = this._objectUrl;
  }

  _schedulePreview() {
    window.clearTimeout(this._previewTimer);
    this._previewTimer = window.setTimeout(() => this._drawPreview(), 40);
  }

  _drawPreview() {
    const canvas = this.shadowRoot.getElementById("preview");
    const placeholder = this.shadowRoot.getElementById("placeholder");
    const meta = this.shadowRoot.getElementById("meta");
    const size = this._panelSize();
    const width = size.width;
    const height = size.height;
    const context = canvas.getContext("2d");
    if (!context) return;

    canvas.width = width;
    canvas.height = height;
    context.fillStyle = this._background;
    context.fillRect(0, 0, width, height);

    if (!this._source) {
      canvas.hidden = true;
      placeholder.hidden = false;
      meta.textContent = `${width}×${height} · ${size.label}`;
      return;
    }

    this._drawFitted(context, this._source, width, height);
    canvas.hidden = false;
    placeholder.hidden = true;
    meta.textContent = `${width}×${height} · ${size.label} · preview (pre-quantize)`;
  }

  _drawFitted(context, image, width, height) {
    if (this._fit === "stretch") {
      context.imageSmoothingEnabled =
        image.naturalWidth > width || image.naturalHeight > height;
      context.drawImage(image, 0, 0, width, height);
      return;
    }
    const scale =
      this._fit === "contain"
        ? Math.min(width / image.naturalWidth, height / image.naturalHeight)
        : Math.max(width / image.naturalWidth, height / image.naturalHeight);
    const drawnWidth = image.naturalWidth * scale;
    const drawnHeight = image.naturalHeight * scale;
    context.imageSmoothingEnabled = scale < 1;
    context.drawImage(
      image,
      (width - drawnWidth) / 2,
      (height - drawnHeight) / 2,
      drawnWidth,
      drawnHeight
    );
  }

  _updateActions() {
    const ready = Boolean(this._deviceId) && !this._busy;
    this.shadowRoot.getElementById("send").disabled = !(ready && this._source);
    this.shadowRoot.getElementById("clear-white").disabled = !ready;
    this.shadowRoot.getElementById("clear-black").disabled = !ready;
  }

  _setStatus(message) {
    this.shadowRoot.getElementById("status").textContent = message;
  }

  _setBusy(busy) {
    this._busy = busy;
    this._updateActions();
  }

  async _fileAsDataUrl() {
    const file = this.shadowRoot.getElementById("file").files?.[0];
    if (!file) throw new Error("No image selected.");
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("Couldn't read the file."));
      reader.readAsDataURL(file);
    });
  }

  async _send() {
    if (!this._hass || !this._deviceId || !this._source) return;
    this._setBusy(true);
    this._setStatus("Sending…");
    try {
      const image = await this._fileAsDataUrl();
      await this._hass.callService("eink_esl", "upload_image", {
        device_id: this._deviceId,
        image,
        fit: this._fit,
        mode: this._mode,
      });
      this._setStatus("Sent.");
    } catch (error) {
      this._setStatus(error?.message || String(error));
    } finally {
      this._setBusy(false);
    }
  }

  async _clear(color) {
    if (!this._hass || !this._deviceId) return;
    this._setBusy(true);
    this._setStatus("Clearing…");
    try {
      await this._hass.callService("eink_esl", "clear_screen", {
        device_id: this._deviceId,
        color,
      });
      this._setStatus("Cleared.");
    } catch (error) {
      this._setStatus(error?.message || String(error));
    } finally {
      this._setBusy(false);
    }
  }
}

customElements.define("eink-esl-panel", EinkEslPanel);
