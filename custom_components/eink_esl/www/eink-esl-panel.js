/**
 * Sidebar panel for E-Ink ESL — styled like the standalone e-ink web tool.
 * Preview matches server encode: fit → OKLab nearest / Floyd–Steinberg.
 */
const PANELS = [
  { id: "bwr-154", label: '1.54" BWR', width: 200, height: 200, colors: "bwr" },
  { id: "bwry-154", label: '1.54" BWRY', width: 200, height: 200, colors: "bwry" },
  { id: "bwr-213", label: '2.13" BWR', width: 250, height: 122, colors: "bwr" },
  { id: "bw-213", label: '2.13" BW', width: 250, height: 122, colors: "bw" },
  { id: "bwry-213", label: '2.13" BWRY', width: 250, height: 122, colors: "bwry" },
  { id: "bwr-266", label: '2.66" BWR', width: 296, height: 152, colors: "bwr" },
  { id: "bwry-266", label: '2.66" BWRY', width: 296, height: 152, colors: "bwry" },
  { id: "bwr-290", label: '2.90" BWR', width: 296, height: 128, colors: "bwr" },
  { id: "bwry-290", label: '2.90" BWRY', width: 296, height: 128, colors: "bwry" },
  { id: "bwr-350", label: '3.50" BWR', width: 384, height: 184, colors: "bwr" },
  { id: "bwry-350", label: '3.50" BWRY', width: 384, height: 184, colors: "bwry" },
  { id: "bwr-420", label: '4.20" BWR', width: 400, height: 300, colors: "bwr" },
  { id: "bwry-420", label: '4.20" BWRY', width: 400, height: 300, colors: "bwry" },
  { id: "bwr-750", label: '7.50" BWR', width: 800, height: 480, colors: "bwr" },
  { id: "bwry-750", label: '7.50" BWRY', width: 800, height: 480, colors: "bwry" },
];

const PANEL_BY_LABEL = Object.fromEntries(PANELS.map((p) => [p.label, p]));
const PROGRESS_EVENT = "eink_esl_transfer_progress";

const SWATCH_RGB = {
  black: [0, 0, 0],
  white: [255, 255, 255],
  yellow: [255, 255, 0],
  red: [255, 0, 0],
};

function srgbToLinear(channel) {
  const value = channel / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function rgbToOklab(r, g, b) {
  const lr = srgbToLinear(r);
  const lg = srgbToLinear(g);
  const lb = srgbToLinear(b);
  const l = (0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb) ** (1 / 3);
  const m = (0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb) ** (1 / 3);
  const s = (0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb) ** (1 / 3);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function makeSwatch(rgb) {
  return { rgb, lab: rgbToOklab(rgb[0], rgb[1], rgb[2]) };
}

const ALL_SWATCHES = {
  black: makeSwatch(SWATCH_RGB.black),
  white: makeSwatch(SWATCH_RGB.white),
  yellow: makeSwatch(SWATCH_RGB.yellow),
  red: makeSwatch(SWATCH_RGB.red),
};

function paletteFor(colors) {
  if (colors === "bw") return [ALL_SWATCHES.black, ALL_SWATCHES.white];
  if (colors === "bwr") {
    return [ALL_SWATCHES.black, ALL_SWATCHES.white, ALL_SWATCHES.red];
  }
  return [
    ALL_SWATCHES.black,
    ALL_SWATCHES.white,
    ALL_SWATCHES.yellow,
    ALL_SWATCHES.red,
  ];
}

function nearestSwatch(lab, palette) {
  let best = palette[0];
  let bestDistance = Infinity;
  for (const color of palette) {
    const dL = lab[0] - color.lab[0];
    const dA = lab[1] - color.lab[1];
    const dB = lab[2] - color.lab[2];
    const distance = dL * dL + dA * dA + dB * dB;
    if (distance < bestDistance) {
      best = color;
      bestDistance = distance;
    }
  }
  return best;
}

function clampLab(lab) {
  return [
    Math.min(1, Math.max(0, lab[0])),
    Math.min(0.5, Math.max(-0.5, lab[1])),
    Math.min(0.5, Math.max(-0.5, lab[2])),
  ];
}

function diffuseError(error, width, height, x, y, leftover, weight) {
  if (x < 0 || y < 0 || x >= width || y >= height) return;
  const index = (y * width + x) * 3;
  error[index] += leftover[0] * weight;
  error[index + 1] += leftover[1] * weight;
  error[index + 2] += leftover[2] * weight;
}

/** Quantize RGBA ImageData in place to panel pigments (matches Python palette.py). */
function quantizeImageData(imageData, mode, colors) {
  const { width, height, data } = imageData;
  const pixelCount = width * height;
  const palette = paletteFor(colors);
  const source = new Float64Array(pixelCount * 3);

  for (let index = 0; index < pixelCount; index += 1) {
    const offset = index * 4;
    const lab = rgbToOklab(data[offset], data[offset + 1], data[offset + 2]);
    source[index * 3] = lab[0];
    source[index * 3 + 1] = lab[1];
    source[index * 3 + 2] = lab[2];
  }

  const write = (index, rgb) => {
    const offset = index * 4;
    data[offset] = rgb[0];
    data[offset + 1] = rgb[1];
    data[offset + 2] = rgb[2];
    data[offset + 3] = 255;
  };

  if (mode === "nearest") {
    for (let index = 0; index < pixelCount; index += 1) {
      const color = nearestSwatch(
        [source[index * 3], source[index * 3 + 1], source[index * 3 + 2]],
        palette
      );
      write(index, color.rgb);
    }
    return;
  }

  const error = new Float64Array(pixelCount * 3);
  for (let y = 0; y < height; y += 1) {
    const leftToRight = y % 2 === 0;
    const step = leftToRight ? 1 : -1;
    const startX = leftToRight ? 0 : width - 1;
    const endX = leftToRight ? width : -1;
    for (let x = startX; x !== endX; x += step) {
      const index = y * width + x;
      const shifted = clampLab([
        source[index * 3] + error[index * 3],
        source[index * 3 + 1] + error[index * 3 + 1],
        source[index * 3 + 2] + error[index * 3 + 2],
      ]);
      const color = nearestSwatch(shifted, palette);
      write(index, color.rgb);
      const leftover = [
        shifted[0] - color.lab[0],
        shifted[1] - color.lab[1],
        shifted[2] - color.lab[2],
      ];
      diffuseError(error, width, height, x + step, y, leftover, 7 / 16);
      diffuseError(error, width, height, x - step, y + 1, leftover, 3 / 16);
      diffuseError(error, width, height, x, y + 1, leftover, 5 / 16);
      diffuseError(error, width, height, x + step, y + 1, leftover, 1 / 16);
    }
  }
}

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
    this._unsubProgress = null;
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
                <option value="#ffffff">White</option>
                <option value="#000000">Black</option>
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
  }

  _schedulePreview() {
    window.clearTimeout(this._previewTimer);
    this._previewTimer = window.setTimeout(() => this._drawPreview(), 40);
  }

  _sizeCanvasDisplay(canvas, width, height) {
    const frame = canvas.parentElement;
    const maxWidth = frame ? frame.clientWidth : width;
    // Prefer integer CSS pixels so panel pixels stay square (no stretch).
    let scale = Math.floor(maxWidth / width);
    if (scale < 1) {
      canvas.style.width = "100%";
      canvas.style.height = "auto";
      return;
    }
    // Cap very large panels so preview stays readable.
    const maxCssHeight = 480;
    while (scale > 1 && height * scale > maxCssHeight) {
      scale -= 1;
    }
    canvas.style.width = `${width * scale}px`;
    canvas.style.height = `${height * scale}px`;
  }

  _drawPreview() {
    const canvas = this.shadowRoot.getElementById("preview");
    const placeholder = this.shadowRoot.getElementById("placeholder");
    const meta = this.shadowRoot.getElementById("meta");
    const size = this._panelSize();
    const width = size.width;
    const height = size.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
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
    const imageData = context.getImageData(0, 0, width, height);
    quantizeImageData(imageData, this._mode, size.colors || "bwry");
    context.putImageData(imageData, 0, 0);

    this._sizeCanvasDisplay(canvas, width, height);
    canvas.hidden = false;
    placeholder.hidden = true;
    meta.textContent = `${width}×${height} · ${size.label} · ${this._mode === "nearest" ? "nearest" : "dither"}`;
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
    const drawnWidth = Math.max(1, Math.round(image.naturalWidth * scale));
    const drawnHeight = Math.max(1, Math.round(image.naturalHeight * scale));
    context.imageSmoothingEnabled = scale < 1;
    context.drawImage(
      image,
      Math.floor((width - drawnWidth) / 2),
      Math.floor((height - drawnHeight) / 2),
      drawnWidth,
      drawnHeight
    );
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
    this._showProgressBusy();
    this._setStatus("Starting…");
    try {
      const image = await this._fileAsDataUrl();
      await this._hass.callService("eink_esl", "upload_image", {
        device_id: this._deviceId,
        image,
        fit: this._fit,
        mode: this._mode,
        background: this._background === "#000000" ? "black" : "white",
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
