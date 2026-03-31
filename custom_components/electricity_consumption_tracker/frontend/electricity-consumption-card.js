(function() {
  'use strict';

  // HÀM TIỆN ÍCH CHUNG
  const formatMoney = (val) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Math.round(val || 0));
  const formatNumber = (val) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(val || 0);

  const hexToRgba = (hex, opacity) => {
    let c;
    if(/^#([A-Fa-f0-9]{3}){1,2}$/.test(hex)){
      c= hex.substring(1).split('');
      if(c.length === 3) c= [c[0], c[0], c[1], c[1], c[2], c[2]];
      c= '0x'+c.join('');
      return 'rgba('+[(c>>16)&255, (c>>8)&255, c&255].join(',')+','+(opacity/100)+')';
    }
    return hex; 
  };

  // ==========================================
  // 1. LỚP CHỈNH SỬA GIAO DIỆN UI (EDITOR)
  // ==========================================
  class ElectricityConsumptionEditor extends HTMLElement {
    
    constructor() {
      super();
      this._config = {}; 
    }

    setConfig(config) {
      this._config = config || {};
      if (this._rendered) this.updateUI();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._rendered) {
        this.render();
        this._rendered = true;
      }
    }

    render() {
      if (!this._hass) return;
      
      const conf = this._config || {};
      const currentTitle = conf.title || "";
      const currentIcon = conf.icon || "";

      const chartColorFields = [
        { id: 'barKwh1', label: 'Cột kWh (Đỉnh)', default: '#3b82f6' },
        { id: 'barKwh2', label: 'Cột kWh (Đáy)', default: '#1e3a8a' },
        { id: 'barVnd1', label: 'Cột VNĐ (Đỉnh)', default: '#10b981' },
        { id: 'barVnd2', label: 'Cột VNĐ (Đáy)', default: '#047857' },
        { id: 'lineKwh', label: 'Line kWh (Năm)', default: '#ff3366' }, 
        { id: 'lineVnd', label: 'Line VNĐ (Năm)', default: '#ffcc00' }, 
        { id: 'lineMonth', label: 'Line (Tháng)', default: '#ff3366' } 
      ];

      this.innerHTML = `
        <style>
          .editor-container { padding: 12px 0; font-family: var(--paper-font-body1_-_font-family, sans-serif); }
          .row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; width: 100%;}
          .row-col { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; width: 100%;}
          .row:last-child, .row-col:last-child { margin-bottom: 0; }
          .label { font-weight: 500; color: var(--primary-text-color); font-size: 14px; }
          .input-group { display: flex; align-items: center; gap: 12px; }
          input[type=color] { cursor: pointer; border: 1px solid var(--divider-color, #e0e0e0); border-radius: 6px; padding: 2px; width: 40px; height: 32px; background: transparent; }
          input[type=range] { flex-grow: 1; cursor: pointer; }
          input[type=text], select.custom-input { width: 100%; padding: 8px; border-radius: 6px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, transparent); color: var(--primary-text-color); box-sizing: border-box; font-size: 14px;}
          .val-badge { background: var(--primary-color); color: var(--text-primary-color, white); padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; min-width: 48px; text-align: center; }
          select.ha-select { background: var(--card-background-color, transparent); color: var(--primary-text-color); border: 1px solid var(--divider-color, #e0e0e0); padding: 6px 8px; border-radius: 6px; font-family: inherit; font-size: 14px; flex-grow: 1; max-width: 250px; cursor: pointer; }
          
          .section { border: 1px solid var(--divider-color, #e0e0e0); border-radius: 12px; padding: 16px; margin-bottom: 16px; background: var(--card-background-color, transparent); box-shadow: 0 2px 4px rgba(0,0,0,0.05); transition: padding 0.3s ease; }
          .section.collapsed { padding-bottom: 16px; }
          .section-title { font-weight: 600; display: flex; align-items: center; justify-content: space-between; font-size: 16px; color: var(--primary-text-color); border-bottom: 1px solid var(--divider-color, #e0e0e0); padding-bottom: 8px; margin-bottom: 16px; cursor: pointer; user-select: none; }
          .section-title.no-collapse { cursor: default; }
          .section-title.no-collapse:hover { opacity: 1; }
          .section-title:hover { opacity: 0.8; }
          .section.collapsed .section-title { margin-bottom: 0; border-bottom: none; padding-bottom: 0; }
          .section-content { display: block; overflow: hidden; animation: slideDown 0.3s ease-out forwards; }
          .section.collapsed .section-content { display: none; }
          .section-icon { font-size: 12px; opacity: 0.6; transition: transform 0.3s ease; }
          .section.collapsed .section-icon { transform: rotate(-90deg); }
          .title-left { display: flex; align-items: center; gap: 8px; pointer-events: none; }
          .title-right { display: flex; align-items: center; gap: 12px; }
          
          .color-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 10px; background: rgba(0,0,0,0.02); border-radius: 8px; border: 1px solid var(--divider-color); margin-top: 8px;}
          .color-item { display: flex; flex-direction: column; gap: 4px; }
          .color-label { font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
          .color-picker { width: 100% !important; height: 28px !important; padding: 0 !important; }
          
          @keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        </style>

        <div class="editor-container">
          
          <div class="section">
            <div class="section-title no-collapse">
              <div class="title-left">⚙️ Cài đặt chung</div>
            </div>
            <div class="section-content">
              <div class="row-col">
                <span class="label">Tiêu đề thẻ (Tuỳ chọn)</span>
                <input type="text" id="title-input" class="custom-input config-trigger" placeholder="VD: Thống kê Điện năng" value="${currentTitle}">
              </div>
              <div class="row-col">
                <span class="label">Icon hoặc Emoji (Tuỳ chọn)</span>
                <input type="text" id="icon-input" class="custom-input config-trigger" placeholder="VD: mdi:flash hoặc ⚡" value="${currentIcon}">
              </div>
              <div class="row-col">
                <span class="label">Sensor mặc định</span>
                <select id="entity-select" class="custom-input config-trigger">
                  <option value="">Đang tải danh sách...</option>
                </select>
              </div>
            </div>
          </div>

          <div class="section">
            <div class="section-title no-collapse">
              <div class="title-left">🎨 Nền (Background)</div>
            </div>
            <div class="section-content">
              <div class="row">
                <span class="label" style="min-width: 120px;">Loại nền</span>
                <select id="bg_type" class="ha-select config-trigger">
                  <option value="solid">Màu đơn sắc (Solid)</option>
                  <option value="gradient">Màu dải (Gradient)</option>
                </select>
              </div>
              <div class="row">
                <span class="label" style="min-width: 120px;">Độ trong suốt (%)</span>
                <input type="range" id="bg_opacity" class="config-trigger" min="0" max="100">
                <span class="val-badge" id="bg_opacity_val"></span>
              </div>

              <div id="solid_settings">
                <div class="row" style="margin-top: 16px; border-top: 1px dashed var(--divider-color, #e0e0e0); padding-top: 16px;">
                  <span class="label">Màu nền</span>
                  <div class="input-group"><input type="color" id="bg_color" class="config-trigger"><span class="val-badge" id="bg_color_val"></span></div>
                </div>
              </div>

              <div id="gradient_settings" style="display:none;">
                <div class="row" style="margin-top: 16px; border-top: 1px dashed var(--divider-color, #e0e0e0); padding-top: 16px;">
                  <span class="label" style="min-width: 120px;">Mẫu Gradient</span>
                  <select id="bg_gradient_preset" class="ha-select config-trigger">
                    <option value="linear-gradient(135deg, #f0f4f8, #d9e2ec)">☀️ Sáng mặc định (Màu zin)</option>
                    <option value="linear-gradient(135deg, #1e293b, #0f172a)">🌙 Tối mặc định</option>
                    <option value="linear-gradient(135deg, #141e30, #243b55)">🌌 Royal Night</option>
                    <option value="linear-gradient(135deg, #0f2027, #203a43, #2c5364)">🌊 Deep Ocean</option>
                    <option value="linear-gradient(135deg, #232526, #414345)">🏙️ Midnight City</option>
                    <option value="linear-gradient(135deg, #1a1a1a, #000000)">⚫ Dark Elegance</option>
                    <option value="linear-gradient(135deg, #ff0099, #493240)">🔮 Cosmic Fusion</option>
                    <option value="linear-gradient(135deg, #ff512f, #dd2476)">🌅 Sunset Vibes</option>
                    <option value="linear-gradient(135deg, #134e5e, #71b280)">🌲 Forest Mist</option>
                    <option value="linear-gradient(135deg, rgba(255,255,255,0.15), rgba(255,255,255,0.05))">🪟 Glassmorphism</option>
                    <option value="linear-gradient(135deg, #0f0c29, #302b63, #24243e)">🚀 Deep Space</option>
                    <option value="linear-gradient(135deg, #667eea, #764ba2)">💜 Plum Plate</option>
                    <option value="linear-gradient(135deg, #ff9a9e, #fecfef)">🌸 Cherry Blossom</option>
                    <option value="linear-gradient(135deg, #f12711, #f5af19)">🔥 Fire Glow</option>
                    <option value="linear-gradient(135deg, #11998e, #38ef7d)">🌿 Neon Life</option>
                    <option value="linear-gradient(135deg, #00c6ff, #0072ff)">❄️ Winter Sky</option>
                    <option value="linear-gradient(135deg, #f6d365, #fda085)">🍑 Sunrise Peach</option>
                    <option value="linear-gradient(135deg, #9D50BB, #6E48AA)">💎 Amethyst</option>
                    <option value="linear-gradient(135deg, #2b5876, #4e4376)">🌠 Starry Night</option>
                    <option value="linear-gradient(135deg, #ff758c, #ff7eb3)">🍉 Sweet Pink</option>
                    <option value="linear-gradient(135deg, #4facfe, #00f2fe)">🏝️ Tropical Blue</option>
                    <option value="linear-gradient(135deg, #870000, #190a05)">🍷 Blood Moon</option>
                    <option value="custom">✍️ Tùy chỉnh (Custom)</option>
                  </select>
                </div>

                <div id="custom_gradient_row" style="display:none; flex-direction: column; gap: 12px; margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--divider-color, #e0e0e0);">
                  <div class="row" style="width: 100%;">
                    <span class="label">Màu 1</span>
                    <div class="input-group"><input type="color" id="bg_gradient_color1" class="config-trigger"><span class="val-badge" id="bg_gradient_color1_val"></span></div>
                  </div>
                  <div class="row" style="width: 100%;">
                    <span class="label">Màu 2</span>
                    <div class="input-group"><input type="color" id="bg_gradient_color2" class="config-trigger"><span class="val-badge" id="bg_gradient_color2_val"></span></div>
                  </div>
                  <div class="row" style="width: 100%;">
                    <span class="label" style="min-width: 120px;">Góc độ (°)</span>
                    <input type="range" id="bg_gradient_angle" class="config-trigger" min="0" max="360" step="1">
                    <span class="val-badge" id="bg_gradient_angle_val"></span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="section collapsed">
            <div class="section-title">
              <div class="title-left">🖋️ Nội dung & Biểu đồ</div>
              <div class="title-right">
                <input type="checkbox" id="auto_contrast" class="config-trigger" style="transform: scale(1.2); cursor: pointer;" title="Tự động tương phản màu theo Nền">
                <span class="section-icon">▼</span>
              </div>
            </div>
            <div class="section-content">
              <div id="custom_colors_settings">
                <div class="row"><span class="label">Màu chữ chính</span><div class="input-group"><input type="color" id="textColor" class="config-trigger"></div></div>
                <div class="row"><span class="label">Màu số nổi bật (Đỏ)</span><div class="input-group"><input type="color" id="redText" class="config-trigger"></div></div>
                <div class="row"><span class="label">Màu Nền các khối nhỏ</span><div class="input-group"><input type="color" id="blockBg" class="config-trigger"></div></div>
              </div>
              
              <div id="chart_colors_settings" class="row-col" style="margin-top: 16px; border-top: 1px dashed var(--divider-color, #e0e0e0); padding-top: 16px;">
                <span class="label">Màu sắc Biểu đồ:</span>
                <div class="color-grid">
                  ${chartColorFields.map(f => `
                    <div class="color-item">
                      <span class="color-label" title="${f.label}">${f.label}</span>
                      <input type="color" class="color-picker chart-color-trigger" data-key="${f.id}" value="${conf[f.id] || f.default}">
                    </div>
                  `).join('')}
                </div>
              </div>
            </div>
          </div>

          <div class="section collapsed">
            <div class="section-title">
              <div class="title-left">🔲 Viền (Border)</div>
              <div class="title-right">
                <input type="checkbox" id="border_enable" class="config-trigger" style="transform: scale(1.2); cursor: pointer;" title="Bật/Tắt viền">
                <span class="section-icon">▼</span>
              </div>
            </div>
            <div class="section-content">
              <div id="border_settings">
                <div class="row"><span class="label">Màu viền</span><div class="input-group"><input type="color" id="border_color" class="config-trigger"><span class="val-badge" id="border_color_val"></span></div></div>
                <div class="row"><span class="label" style="min-width: 120px;">Độ dày viền (px)</span><input type="range" id="border_width" class="config-trigger" min="0" max="10" step="1"><span class="val-badge" id="border_width_val"></span></div>
                <div class="row"><span class="label" style="min-width: 120px;">Độ trong suốt (%)</span><input type="range" id="border_opacity" class="config-trigger" min="0" max="100"><span class="val-badge" id="border_opacity_val"></span></div>
              </div>
            </div>
          </div>

          <div class="section collapsed">
            <div class="section-title">
              <div class="title-left">☁️ Đổ bóng (Shadow)</div>
              <div class="title-right">
                <input type="checkbox" id="shadow_enable" class="config-trigger" style="transform: scale(1.2); cursor: pointer;" title="Bật/Tắt hiệu ứng đổ bóng">
                <span class="section-icon">▼</span>
              </div>
            </div>
            <div class="section-content">
              <div id="shadow_settings">
                <div class="row"><span class="label">Màu đổ bóng</span><div class="input-group"><input type="color" id="shadow_color" class="config-trigger"><span class="val-badge" id="shadow_color_val"></span></div></div>
                <div class="row"><span class="label" style="min-width: 120px;">Độ trong suốt (%)</span><input type="range" id="shadow_opacity" class="config-trigger" min="0" max="100"><span class="val-badge" id="shadow_opacity_val"></span></div>
                <div class="row"><span class="label" style="min-width: 120px;">Độ nhòe (Blur)</span><input type="range" id="shadow_blur" class="config-trigger" min="0" max="100"><span class="val-badge" id="shadow_blur_val"></span></div>
                <div class="row"><span class="label" style="min-width: 120px;">Khoảng cách (X)</span><input type="range" id="shadow_offset_x" class="config-trigger" min="-50" max="50"><span class="val-badge" id="shadow_offset_x_val"></span></div>
                <div class="row"><span class="label" style="min-width: 120px;">Khoảng cách (Y)</span><input type="range" id="shadow_offset_y" class="config-trigger" min="-50" max="50"><span class="val-badge" id="shadow_offset_y_val"></span></div>
              </div>
            </div>
          </div>

        </div>
      `;

      this.updateUI();
      this.addListeners();
    }

    get _bg_type() { return this._config?.bg_type || 'gradient'; }
    get _bg_color() { return this._config?.bg_color || '#f0f4f8'; }
    get _bg_opacity() { return this._config?.bg_opacity !== undefined ? this._config.bg_opacity : 100; }
    get _bg_gradient_preset() { return this._config?.bg_gradient_preset || 'linear-gradient(135deg, #f0f4f8, #d9e2ec)'; }
    get _bg_gradient_color1() { return this._config?.bg_gradient_color1 || '#f0f4f8'; }
    get _bg_gradient_color2() { return this._config?.bg_gradient_color2 || '#d9e2ec'; }
    get _bg_gradient_angle() { return this._config?.bg_gradient_angle !== undefined ? this._config.bg_gradient_angle : 135; }

    get _border_enable() { return this._config?.border_enable !== undefined ? this._config.border_enable : (this._config?.border_width > 0); }
    get _border_color() { return this._config?.border_color || '#ffffff'; }
    get _border_width() { return this._config?.border_width !== undefined ? this._config.border_width : 0; }
    get _border_opacity() { return this._config?.border_opacity !== undefined ? this._config.border_opacity : 0; }
    
    get _shadow_enable() { return this._config?.shadow_enable !== undefined ? this._config.shadow_enable : true; }
    get _shadow_color() { return this._config?.shadow_color || '#000000'; }
    get _shadow_opacity() { return this._config?.shadow_opacity !== undefined ? this._config.shadow_opacity : 10; }
    get _shadow_blur() { return this._config?.shadow_blur !== undefined ? this._config.shadow_blur : 20; }
    get _shadow_offset_x() { return this._config?.shadow_offset_x !== undefined ? this._config.shadow_offset_x : 0; }
    get _shadow_offset_y() { return this._config?.shadow_offset_y !== undefined ? this._config.shadow_offset_y : 8; }

    get _auto_contrast() { return this._config?.auto_contrast !== undefined ? this._config.auto_contrast : false; }
    get _textColor() { return this._config?.textColor || '#1e3a8a'; }
    get _redText() { return this._config?.redText || '#dc2626'; }
    get _blockBg() { return this._config?.blockBg || '#ffffff'; }

    updateUI() {
      if (!this.querySelector('#bg_type')) return;

      const entitySelect = this.querySelector('#entity-select');
      if (entitySelect && this._hass) {
          const currentVal = this._config.entity || "";
          let selectHtml = `<option value="">-- Tự động chọn cái đầu tiên --</option>`;
          
          const states = this._hass.states || {};
          const validEntities = Object.keys(states).filter(eid => states[eid].attributes && states[eid].attributes.chi_tiet_tung_nam !== undefined);
          
          if (currentVal && !validEntities.includes(currentVal)) {
              validEntities.unshift(currentVal);
          }

          validEntities.forEach(e => {
              const state = states[e];
              let name = state ? (state.attributes.friendly_name || e) : e;
              if (this._hass.entities && this._hass.entities[e]) {
                  const entInfo = this._hass.entities[e];
                  if (entInfo.device_id && this._hass.devices && this._hass.devices[entInfo.device_id]) {
                      const devInfo = this._hass.devices[entInfo.device_id];
                      name = devInfo.name_by_user || devInfo.name || name;
                  } else if (entInfo.name) name = entInfo.name;
              }
              name = name.replace(' Total All Time', '').trim();
              selectHtml += `<option value="${e}">${name}</option>`;
          });

          entitySelect.innerHTML = selectHtml;
          entitySelect.value = currentVal;
      }
      
      const titleInput = this.querySelector('#title-input');
      if (titleInput && this._config.title !== undefined) titleInput.value = this._config.title || "";
      
      const iconInput = this.querySelector('#icon-input');
      if (iconInput && this._config.icon !== undefined) iconInput.value = this._config.icon || "";
      
      const chartColorKeys = ['barKwh1', 'barKwh2', 'barVnd1', 'barVnd2', 'lineKwh', 'lineVnd', 'lineMonth'];
      chartColorKeys.forEach(key => {
          const input = this.querySelector(`.chart-color-trigger[data-key="${key}"]`);
          if (input && this._config[key]) {
              input.value = this._config[key];
          }
      });

      this.querySelector('#bg_type').value = this._bg_type;
      this.querySelector('#bg_opacity').value = this._bg_opacity;
      this.querySelector('#bg_opacity_val').textContent = this._bg_opacity + '%';

      if (this._bg_type === 'gradient') {
        this.querySelector('#solid_settings').style.display = 'none';
        this.querySelector('#gradient_settings').style.display = 'block';
      } else {
        this.querySelector('#solid_settings').style.display = 'block';
        this.querySelector('#gradient_settings').style.display = 'none';
      }

      this.querySelector('#bg_color').value = this._bg_color;
      this.querySelector('#bg_color_val').textContent = this._bg_color.toUpperCase();
      this.querySelector('#bg_gradient_preset').value = this._bg_gradient_preset;
      
      if (this._bg_gradient_preset === 'custom') {
        this.querySelector('#custom_gradient_row').style.display = 'flex';
      } else {
        this.querySelector('#custom_gradient_row').style.display = 'none';
      }
      
      this.querySelector('#bg_gradient_color1').value = this._bg_gradient_color1;
      this.querySelector('#bg_gradient_color1_val').textContent = this._bg_gradient_color1.toUpperCase();
      this.querySelector('#bg_gradient_color2').value = this._bg_gradient_color2;
      this.querySelector('#bg_gradient_color2_val').textContent = this._bg_gradient_color2.toUpperCase();
      this.querySelector('#bg_gradient_angle').value = this._bg_gradient_angle;
      this.querySelector('#bg_gradient_angle_val').textContent = this._bg_gradient_angle + '°';

      const borderCheckbox = this.querySelector('#border_enable');
      if (borderCheckbox) borderCheckbox.checked = this._border_enable;
      this.querySelector('#border_settings').style.display = this._border_enable ? 'block' : 'none';
      this.querySelector('#border_color').value = this._border_color;
      this.querySelector('#border_color_val').textContent = this._border_color.toUpperCase();
      this.querySelector('#border_width').value = this._border_width;
      this.querySelector('#border_width_val').textContent = this._border_width + 'px';
      this.querySelector('#border_opacity').value = this._border_opacity;
      this.querySelector('#border_opacity_val').textContent = this._border_opacity + '%';

      this.querySelector('#shadow_enable').checked = this._shadow_enable;
      this.querySelector('#shadow_settings').style.display = this._shadow_enable ? 'block' : 'none';
      this.querySelector('#shadow_color').value = this._shadow_color;
      this.querySelector('#shadow_color_val').textContent = this._shadow_color.toUpperCase();
      this.querySelector('#shadow_opacity').value = this._shadow_opacity;
      this.querySelector('#shadow_opacity_val').textContent = this._shadow_opacity + '%';
      this.querySelector('#shadow_blur').value = this._shadow_blur;
      this.querySelector('#shadow_blur_val').textContent = this._shadow_blur + 'px';
      this.querySelector('#shadow_offset_x').value = this._shadow_offset_x;
      this.querySelector('#shadow_offset_x_val').textContent = this._shadow_offset_x + 'px';
      this.querySelector('#shadow_offset_y').value = this._shadow_offset_y;
      this.querySelector('#shadow_offset_y_val').textContent = this._shadow_offset_y + 'px';

      this.querySelector('#auto_contrast').checked = this._auto_contrast;
      if (this._auto_contrast) {
          this.querySelector('#custom_colors_settings').style.opacity = '0.4';
          this.querySelector('#custom_colors_settings').style.pointerEvents = 'none';
          this.querySelector('#chart_colors_settings').style.opacity = '0.4';
          this.querySelector('#chart_colors_settings').style.pointerEvents = 'none';
      } else {
          this.querySelector('#custom_colors_settings').style.opacity = '1';
          this.querySelector('#custom_colors_settings').style.pointerEvents = 'auto';
          this.querySelector('#chart_colors_settings').style.opacity = '1';
          this.querySelector('#chart_colors_settings').style.pointerEvents = 'auto';
      }

      this.querySelector('#textColor').value = this._textColor;
      this.querySelector('#redText').value = this._redText;
      this.querySelector('#blockBg').value = this._blockBg;
    }

    addListeners() {
      const dispatchUpdate = () => {
        let newConfig = { 
            ...this._config,
            entity: this.querySelector('#entity-select').value,
            title: this.querySelector('#title-input').value,
            icon: this.querySelector('#icon-input').value,

            bg_type: this.querySelector('#bg_type').value,
            bg_color: this.querySelector('#bg_color').value,
            bg_opacity: parseInt(this.querySelector('#bg_opacity').value, 10),
            bg_gradient_preset: this.querySelector('#bg_gradient_preset').value,
            bg_gradient_color1: this.querySelector('#bg_gradient_color1').value,
            bg_gradient_color2: this.querySelector('#bg_gradient_color2').value,
            bg_gradient_angle: parseInt(this.querySelector('#bg_gradient_angle').value, 10),

            border_enable: this.querySelector('#border_enable').checked,
            border_color: this.querySelector('#border_color').value,
            border_width: parseInt(this.querySelector('#border_width').value, 10),
            border_opacity: parseInt(this.querySelector('#border_opacity').value, 10),
            
            shadow_enable: this.querySelector('#shadow_enable').checked,
            shadow_color: this.querySelector('#shadow_color').value,
            shadow_opacity: parseInt(this.querySelector('#shadow_opacity').value, 10),
            shadow_blur: parseInt(this.querySelector('#shadow_blur').value, 10),
            shadow_offset_x: parseInt(this.querySelector('#shadow_offset_x').value, 10),
            shadow_offset_y: parseInt(this.querySelector('#shadow_offset_y').value, 10),

            auto_contrast: this.querySelector('#auto_contrast').checked,
            textColor: this.querySelector('#textColor').value,
            redText: this.querySelector('#redText').value,
            blockBg: this.querySelector('#blockBg').value
        };
        
        this.querySelectorAll('.chart-color-trigger').forEach(input => {
            newConfig[input.dataset.key] = input.value;
        });
        
        const event = new CustomEvent("config-changed", { detail: { config: newConfig }, bubbles: true, composed: true });
        this.dispatchEvent(event);
      };

      this.querySelectorAll('.config-trigger, .chart-color-trigger').forEach(el => {
        if (el.tagName === 'SELECT') {
            el.addEventListener('change', dispatchUpdate);
        } else {
            el.addEventListener('input', dispatchUpdate);
            el.addEventListener('change', dispatchUpdate); 
        }
      });

      this.querySelectorAll('.section-title:not(.no-collapse)').forEach(titleEl => {
        const inputs = titleEl.querySelectorAll('input, select, button');
        inputs.forEach(input => {
          input.addEventListener('click', (e) => e.stopPropagation());
        });

        titleEl.addEventListener('click', () => {
          const section = titleEl.closest('.section');
          section.classList.toggle('collapsed');
        });
      });
    }
  }

  // ==========================================
  // 2. LỚP HIỂN THỊ GIAO DIỆN THẺ (CARD)
  // ==========================================
  class ElectricityConsumptionCard extends HTMLElement {
    static getConfigElement() { return document.createElement('electricity-consumption-editor'); }
    static getStubConfig(hass) {
      if (!hass || !hass.states) return {};
      const entity = Object.keys(hass.states).find(eid => hass.states[eid].attributes?.chi_tiet_tung_nam !== undefined);
      return { entity: entity || "" };
    }

    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this.config = {}; 
      
      this._selectedYear = null;
      this._selectedMonth = null;
      
      this._activeTab = 'overview'; 
      this._formYear = null;
      this._formMonth = ''; 
      this._searchYear = null;
      this._searchMonth = null;
      this._hasSearched = false;

      this._yearsList = [];
      this._monthsList = [];
      this._resetTimer = null; 
      this._availableInstances = [];
      this._currentEntityId = null;
      this._lastHtml = ""; 
      
      // Biến phục vụ tối ưu hóa Load
      this._initialized = false;
      this._loadStartTime = null;
    }

    setConfig(config) {
      this.config = config || {};
      this.render(); 
      if (this._hass) {
        this.scanForInstances();
        this.processData();
        this.updateView();
      }
    }

    set hass(hass) {
      const oldHass = this._hass;
      this._hass = hass;
      
      if (!this._initialized) {
        this.scanForInstances();
        this.processData();
        this.updateView();
        this._initialized = true;
        return;
      }

      if (!this._currentEntityId || this._availableInstances.length === 0) {
        this.scanForInstances();
        if (this._availableInstances.length > 0) {
          this.processData();
        }
        this.updateView(); 
        return;
      }

      if (oldHass && oldHass.states[this._currentEntityId] !== hass.states[this._currentEntityId]) {
        this.processData();
        this.updateView();
      }
    }

    startResetTimer() {
      this.clearResetTimer();
      this._resetTimer = setTimeout(() => { this.resetToCurrentDate(); }, 120000);
    }

    clearResetTimer() {
      if (this._resetTimer) { clearTimeout(this._resetTimer); this._resetTimer = null; }
    }

    resetToCurrentDate() {
      const now = new Date();
      const currentYear = now.getFullYear();
      const currentMonth = now.getMonth() + 1;
      
      let needsUpdate = false;
      if (this._activeTab !== 'overview') {
          this._activeTab = 'overview';
          needsUpdate = true;
      }
      if (this._selectedYear !== currentYear || this._selectedMonth !== currentMonth) {
        this._selectedYear = currentYear; 
        this._selectedMonth = currentMonth;
        needsUpdate = true;
      }
      
      if (needsUpdate) {
          this.processData(); 
          this.updateView();
      }
    }

    disconnectedCallback() { this.clearResetTimer(); }

    scanForInstances() {
      if (!this._hass) return;
      const totalEntities = Object.keys(this._hass.states).filter(eid => this._hass.states[eid].attributes?.chi_tiet_tung_nam !== undefined);
      this._availableInstances = totalEntities.map(eid => {
        let name = this._hass.states[eid].attributes.friendly_name || eid;
        if (this._hass.entities && this._hass.entities[eid]) {
          const entInfo = this._hass.entities[eid];
          if (entInfo.device_id && this._hass.devices && this._hass.devices[entInfo.device_id]) {
            name = this._hass.devices[entInfo.device_id].name_by_user || this._hass.devices[entInfo.device_id].name || name; 
          } else if (entInfo.name) name = entInfo.name;
        }
        return { id: eid, name: name.replace(' Total All Time', '').trim() };
      }).sort((a, b) => a.name.localeCompare(b.name));

      const conf = this.config || {};
      if (!this._currentEntityId || !this._availableInstances.some(inst => inst.id === this._currentEntityId)) {
        if (this._availableInstances.length > 0) {
          this._currentEntityId = (conf.entity && this._availableInstances.some(inst => inst.id === conf.entity)) ? conf.entity : this._availableInstances[0].id;
        } else this._currentEntityId = null;
      }
    }

    processData() {
      if (!this._hass || !this._currentEntityId) return;
      this.baseSlug = this._currentEntityId.replace('_total_all_time', '');
      const totalState = this._hass.states[this._currentEntityId];
      if (!totalState || !totalState.attributes.chi_tiet_tung_nam) {
          this._yearsList = []; this._monthsList = []; return;
      }

      this._yearsList = Object.keys(totalState.attributes.chi_tiet_tung_nam).map(y => parseInt(y.replace('Nam_', ''))).sort((a, b) => b - a); 
      
      if (this._selectedYear === null && this._yearsList.length > 0) this._selectedYear = this._yearsList[0];
      if (this._formYear === null && this._yearsList.length > 0) this._formYear = this._yearsList[0];

      if (this._selectedYear !== null) {
        const yearState = this._hass.states[`${this.baseSlug}_nam_${this._selectedYear}`];
        this._monthsList = [];
        if (yearState && yearState.attributes.chi_tiet_cac_thang) {
          this._monthsList = Object.keys(yearState.attributes.chi_tiet_cac_thang).map(m => parseInt(m.replace('Thang_', ''))).sort((a, b) => b - a);
        } else {
          this._monthsList = Object.keys(this._hass.states).filter(eid => eid.startsWith(`${this.baseSlug}_thang_`) && eid.endsWith(`_${this._selectedYear}`)).map(eid => parseInt(eid.split('_thang_')[1].split('_')[0])).sort((a, b) => b - a);
        }
        if (this._selectedMonth === null && this._monthsList.length > 0) this._selectedMonth = this._monthsList[0];
      }
    }

    render() {
      if (!this.card) {
        this.card = document.createElement('ha-card');
        this.card.style.padding = '6px 12px 12px 12px'; 
        this.card.style.borderRadius = 'var(--ha-card-border-radius, 16px)'; 
        this.card.style.isolation = 'isolate'; 
        this.card.style.position = 'relative';

        this.shadowRoot.appendChild(this.card);

        this.card.addEventListener('mouseleave', () => { this.startResetTimer(); });
        this.card.addEventListener('mouseenter', () => { this.clearResetTimer(); });
        this.card.addEventListener('touchstart', () => { this.clearResetTimer(); });
        this.card.addEventListener('touchend', () => { this.startResetTimer(); });

        this.card.addEventListener('click', (e) => {
          const el = e.target;
          if (!el || !el.closest) return; // Fail-safe bảo vệ DOM Element

          // Nút bấm cho tab Tổng quan
          if (el.closest('.btn-y-prev')) this.changeYear(-1);
          if (el.closest('.btn-y-next')) this.changeYear(1);
          if (el.closest('.btn-m-prev')) this.changeMonth(-1);
          if (el.closest('.btn-m-next')) this.changeMonth(1);
          
          // Nút bấm cho tab Tra cứu
          if (el.closest('.btn-sy-prev')) this.changeSearchYear(-1);
          if (el.closest('.btn-sy-next')) this.changeSearchYear(1);
          if (el.closest('.btn-sm-prev')) this.changeSearchMonth(-1);
          if (el.closest('.btn-sm-next')) this.changeSearchMonth(1);

          if (el.closest('.tab-item')) {
              const clickedTab = el.closest('.tab-item').dataset.tab;
              if (this._activeTab !== clickedTab) {
                  this._activeTab = clickedTab;
                  this.updateView();
              }
          }

          if (el.closest('#btn-do-search')) {
              // Sử dụng this.card.querySelector để lấy DOM an toàn tuyệt đối
              const selYear = this.card.querySelector('#sel-search-year');
              const selMonth = this.card.querySelector('#sel-search-month');
              if (selYear && selMonth) {
                  this._formYear = parseInt(selYear.value);
                  const mVal = selMonth.value;
                  this._formMonth = mVal;
                  this._searchYear = this._formYear;
                  this._searchMonth = mVal !== "" ? parseInt(mVal) : null;
                  this._hasSearched = true;
                  this.updateView();
              }
          }
        });

        this.card.addEventListener('change', (e) => {
          const el = e.target;
          if (!el) return;

          if (el.id === 'sel-instance') {
            this._currentEntityId = el.value; this._selectedYear = null; this._selectedMonth = null;
            this._hasSearched = false;
            this.processData(); this.updateView();
          }
          if (el.id === 'sel-year') { 
            this._selectedYear = parseInt(el.value); this._selectedMonth = null; 
            this.processData(); this.updateView(); 
          }
          if (el.id === 'sel-month') { 
            this._selectedMonth = parseInt(el.value); this.updateView(); 
          }
          if (el.id === 'sel-search-year') {
              this._formYear = parseInt(el.value);
              this.triggerAutoSearch();
          }
          if (el.id === 'sel-search-month') {
              this._formMonth = el.value;
              this.triggerAutoSearch();
          }
        });
      }
    }

    // ==========================================
    // LOGIC CHUYỂN ĐỔI - TỔNG QUAN
    // ==========================================
    changeYear(step) {
      if (!this._yearsList || this._yearsList.length === 0) return;
      const idx = this._yearsList.indexOf(this._selectedYear);
      if (idx !== -1 && this._yearsList[idx - step] !== undefined) {
        this._selectedYear = this._yearsList[idx - step]; this._selectedMonth = null; 
        this.processData(); this.updateView();
      }
    }

    changeMonth(step) {
      if (!this._monthsList || this._monthsList.length === 0) return;
      const idx = this._monthsList.indexOf(this._selectedMonth);
      if (idx !== -1 && this._monthsList[idx - step] !== undefined) {
        this._selectedMonth = this._monthsList[idx - step]; this.updateView();
      }
    }

    // ==========================================
    // LOGIC CHUYỂN ĐỔI - TRA CỨU
    // ==========================================
    triggerAutoSearch() {
        if (this._hasSearched) {
            this._searchYear = this._formYear;
            this._searchMonth = this._formMonth !== "" ? parseInt(this._formMonth) : null;
        }
        this.updateView();
    }

    changeSearchYear(step) {
      if (!this._yearsList || this._yearsList.length === 0) return;
      let currentYear = this._formYear;
      if (currentYear === null) currentYear = this._yearsList[0]; // Backup fail-safe
      
      const idx = this._yearsList.indexOf(currentYear);
      if (idx !== -1 && this._yearsList[idx - step] !== undefined) {
        this._formYear = this._yearsList[idx - step];
        this.triggerAutoSearch();
      }
    }

    changeSearchMonth(step) {
      const states = ['', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
      let current = this._formMonth;
      if (current !== '') current = parseInt(current);
      
      let idx = states.indexOf(current);
      if (idx === -1) idx = 0;
      
      let newIdx = idx + step;
      if (newIdx >= states.length) newIdx = 0; 
      if (newIdx < 0) newIdx = states.length - 1; 
      
      this._formMonth = states[newIdx];
      this.triggerAutoSearch();
    }


    updateView() {
      if (!this._hass || !this.card) return;

      if (this._availableInstances.length === 0) {
        if (!this._loadStartTime) this._loadStartTime = Date.now();
        
        if (Date.now() - this._loadStartTime > 20000) {
            this.card.innerHTML = `
                <div style="padding: 24px 16px; text-align: center; border-radius: 12px; background: rgba(220, 38, 38, 0.1); border: 1px dashed rgba(220, 38, 38, 0.3);">
                    <ha-icon icon="mdi:alert-circle-outline" style="color: #dc2626; font-size: 32px; margin-bottom: 8px;"></ha-icon>
                    <div style="color: #dc2626; font-weight: bold; font-size: 14px;">Chưa tìm thấy dữ liệu từ Tracker.</div>
                    <div style="color: #ef4444; font-size: 12px; margin-top: 4px;">Vui lòng kiểm tra lại cấu hình sensor trong HA.</div>
                </div>`;
        } else {
            this.card.innerHTML = `
                <style>
                    .ha-card-loader { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; gap: 16px; min-height: 150px; }
                    .loader-spinner { width: 36px; height: 36px; border: 3px solid var(--divider-color, rgba(120, 120, 120, 0.2)); border-top-color: #3b82f6; border-radius: 50%; animation: ha-spin 1s linear infinite; }
                    .loader-text { text-align: center; font-family: sans-serif; font-size: 14px; font-weight: 600; color: var(--secondary-text-color, #888); animation: ha-pulse 1.5s ease-in-out infinite; }
                    @keyframes ha-spin { to { transform: rotate(360deg); } }
                    @keyframes ha-pulse { 0%, 100% { opacity: 0.6; } 50% { opacity: 1; } }
                </style>
                <div class="ha-card-loader">
                    <div class="loader-spinner"></div>
                    <div class="loader-text">Đang đồng bộ dữ liệu Điện năng...
                    <br>Vui lòng chờ dữ liệu đang được nạp
                    <br>Nếu báo lỗi hãy F5 lại trang hoặc đóng trình duyệt và mở lại
                    </div>
                </div>
            `;
            setTimeout(() => { if (this._availableInstances.length === 0) this.updateView(); }, 1000);
        }
        return;
      } else {
        this._loadStartTime = null; 
      }

      if (!this._currentEntityId) return;

      const totalState = this._hass.states[this._currentEntityId];
      if (!totalState) return;

      const now = new Date();
      const currentYear = now.getFullYear();
      const currentMonth = now.getMonth() + 1; 
      const currentDay = now.getDate();

      const conf = this.config || {};
      const displayTitle = conf.title || "Thống kê Điện năng";
      const configIcon = conf.icon || "mdi:transmission-tower";
      
      const applyOpacityToGradientStr = (str, opacity) => {
          return str.replace(/#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})\b/gi, (match) => hexToRgba(match, opacity));
      };

      const bgType = conf.bg_type || 'gradient';
      const bgOpacity = conf.bg_opacity !== undefined ? conf.bg_opacity : 100;
      let stringForContrastCalc = ""; 

      if (bgType === 'gradient') {
          const preset = conf.bg_gradient_preset || 'linear-gradient(135deg, #f0f4f8, #d9e2ec)';
          if (preset === 'custom') {
              const color1 = conf.bg_gradient_color1 || '#f0f4f8';
              const color2 = conf.bg_gradient_color2 || '#d9e2ec';
              const angle = conf.bg_gradient_angle !== undefined ? conf.bg_gradient_angle : 135;
              this.card.style.background = `linear-gradient(${angle}deg, ${hexToRgba(color1, bgOpacity)}, ${hexToRgba(color2, bgOpacity)})`;
              stringForContrastCalc = `${color1} ${color2}`;
          } else {
              this.card.style.background = applyOpacityToGradientStr(preset, bgOpacity);
              stringForContrastCalc = preset;
          }
      } else {
          const bgColor = conf.bg_color || '#f0f4f8';
          this.card.style.background = hexToRgba(bgColor, bgOpacity);
          stringForContrastCalc = bgColor;
      }

      const borderEnabled = conf.border_enable !== undefined ? conf.border_enable : (conf.border_width > 0);
      if (borderEnabled) {
          const borderWidth = conf.border_width !== undefined ? conf.border_width : 0;
          const borderOpacity = conf.border_opacity !== undefined ? conf.border_opacity : 0;
          const borderColor = conf.border_color || '#ffffff';
          if (borderOpacity > 0 && borderWidth > 0) {
              this.card.style.border = `${borderWidth}px solid ${hexToRgba(borderColor, borderOpacity)}`;
          } else {
              this.card.style.border = 'none';
          }
      } else {
          this.card.style.border = 'none';
      }

      const shadowEnabled = conf.shadow_enable !== undefined ? conf.shadow_enable : true;
      if (shadowEnabled) {
          const shadowColor = conf.shadow_color || '#000000';
          const shadowOpacity = conf.shadow_opacity !== undefined ? conf.shadow_opacity : 10;
          const blur = conf.shadow_blur !== undefined ? conf.shadow_blur : 20;
          const offsetX = conf.shadow_offset_x !== undefined ? conf.shadow_offset_x : 0;
          const offsetY = conf.shadow_offset_y !== undefined ? conf.shadow_offset_y : 8;
          this.card.style.boxShadow = `${offsetX}px ${offsetY}px ${blur}px ${hexToRgba(shadowColor, shadowOpacity)}`;
      } else {
          this.card.style.boxShadow = 'none';
      }

      let c_block = conf.blockBg || '#ffffff';
      let c_text = conf.textColor || '#1e3a8a';
      let c_red = conf.redText || '#dc2626';
      let c_option_bg = '#ffffff'; 
      
      let c_barK1 = conf.barKwh1 || '#3b82f6';
      let c_barK2 = conf.barKwh2 || '#1e3a8a';
      let c_barV1 = conf.barVnd1 || '#10b981';
      let c_barV2 = conf.barVnd2 || '#047857';
      let c_lineK = conf.lineKwh || '#ff3366'; 
      let c_lineV = conf.lineVnd || '#ffcc00'; 
      let c_lineM = conf.lineMonth || '#ff3366';

      if (conf.auto_contrast) {
          const hexRegex = /#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})\b/gi;
          let match;
          let colorsToCheck = [];
          while ((match = hexRegex.exec(stringForContrastCalc)) !== null) {
              let hex = match[1];
              if (hex.length === 3) hex = hex.split('').map(x => x+x).join('');
              colorsToCheck.push({ r: parseInt(hex.substring(0,2), 16), g: parseInt(hex.substring(2,4), 16), b: parseInt(hex.substring(4,6), 16) });
          }
          const rgbRegex = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/gi;
          while ((match = rgbRegex.exec(stringForContrastCalc)) !== null) {
              colorsToCheck.push({ r: parseInt(match[1], 10), g: parseInt(match[2], 10), b: parseInt(match[3], 10) });
          }

          if (colorsToCheck.length > 0) {
              let avgR = 0, avgG = 0, avgB = 0;
              colorsToCheck.forEach(c => { avgR += c.r; avgG += c.g; avgB += c.b; });
              avgR = Math.round(avgR / colorsToCheck.length);
              avgG = Math.round(avgG / colorsToCheck.length);
              avgB = Math.round(avgB / colorsToCheck.length);

              let isDarkTheme = false;
              if (this._hass && this._hass.themes && this._hass.themes.darkMode !== undefined) {
                  isDarkTheme = this._hass.themes.darkMode;
              } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                  isDarkTheme = true;
              }

              const op = bgOpacity / 100;
              const baseBg = isDarkTheme ? 30 : 245; 
              
              const effR = Math.round(avgR * op + baseBg * (1 - op));
              const effG = Math.round(avgG * op + baseBg * (1 - op));
              const effB = Math.round(avgB * op + baseBg * (1 - op));

              const yiq = ((effR * 299) + (effG * 587) + (effB * 114)) / 1000;
              const isLightBackground = yiq >= 135;

              let r = effR / 255, g = effG / 255, b = effB / 255;
              let max = Math.max(r, g, b), min = Math.min(r, g, b);
              let h, s, l = (max + min) / 2;
              if (max == min) { h = s = 0; }
              else {
                  let d = max - min;
                  s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
                  switch(max) {
                      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
                      case g: h = (b - r) / d + 2; break;
                      case b: h = (r - g) / d + 4; break;
                  }
                  h /= 6;
              }
              let hue = Math.round(h * 360);

              let chartPalette = { kwh: 'blue', vnd: 'green' }; 
              if (s >= 0.15) {
                  if (hue >= 330 || hue < 45) { chartPalette = { kwh: 'cyan', vnd: 'green' }; } 
                  else if (hue >= 45 && hue < 160) { chartPalette = { kwh: 'purple', vnd: 'blue' }; } 
                  else if (hue >= 160 && hue < 260) { chartPalette = { kwh: 'orange', vnd: 'pink' }; } 
                  else { chartPalette = { kwh: 'green', vnd: 'cyan' }; }
              }

              if (isLightBackground) {
                  c_text = '#1a1a1a';
                  c_block = hexToRgba('#000000', Math.max(5, op * 10)); 
                  c_option_bg = '#ffffff'; 
                  
                  if (s < 0.15) { c_red = '#E65100'; }
                  else if (hue >= 330 || hue < 30) { c_red = '#0D47A1'; }
                  else if (hue >= 30 && hue < 90) { c_red = '#4A148C'; }
                  else if (hue >= 90 && hue < 170) { c_red = '#B71C1C'; }
                  else if (hue >= 170 && hue < 260) { c_red = '#E65100'; }
                  else { c_red = '#E64A19'; }
                  
                  const palettesLight = {
                      'blue':   {1: '#3b82f6', 2: '#1e3a8a', l: '#ef4444'},
                      'green':  {1: '#10b981', 2: '#047857', l: '#8b5cf6'},
                      'cyan':   {1: '#06b6d4', 2: '#0891b2', l: '#e11d48'},
                      'purple': {1: '#8b5cf6', 2: '#5b21b6', l: '#f59e0b'},
                      'orange': {1: '#f97316', 2: '#c2410c', l: '#2563eb'},
                      'pink':   {1: '#ec4899', 2: '#be185d', l: '#059669'} 
                  };
                  c_barK1 = palettesLight[chartPalette.kwh][1]; c_barK2 = palettesLight[chartPalette.kwh][2]; c_lineK = palettesLight[chartPalette.kwh].l;
                  c_barV1 = palettesLight[chartPalette.vnd][1]; c_barV2 = palettesLight[chartPalette.vnd][2]; c_lineV = palettesLight[chartPalette.vnd].l;
                  c_lineM = c_lineK; 
              } else {
                  c_text = '#ffffff';
                  c_block = hexToRgba('#ffffff', Math.max(10, op * 15)); 
                  c_option_bg = '#1e1e1e'; 
                  
                  if (s < 0.15) { c_red = '#FFCA28'; }
                  else if (hue >= 330 || hue < 30) { c_red = '#FFEA00'; }
                  else if (hue >= 30 && hue < 90) { c_red = '#69F0AE'; }
                  else if (hue >= 90 && hue < 170) { c_red = '#FF9100'; }
                  else if (hue >= 170 && hue < 260) { c_red = '#C6FF00'; }
                  else { c_red = '#FFD54F'; }

                  const palettesDark = {
                      'blue':   {1: '#60a5fa', 2: '#3b82f6', l: '#fde047'},
                      'green':  {1: '#34d399', 2: '#10b981', l: '#f472b6'},
                      'cyan':   {1: '#22d3ee', 2: '#06b6d4', l: '#fb923c'},
                      'purple': {1: '#a78bfa', 2: '#8b5cf6', l: '#4ade80'},
                      'orange': {1: '#fb923c', 2: '#f97316', l: '#22d3ee'},
                      'pink':   {1: '#f472b6', 2: '#ec4899', l: '#fef08a'} 
                  };
                  c_barK1 = palettesDark[chartPalette.kwh][1]; c_barK2 = palettesDark[chartPalette.kwh][2]; c_lineK = palettesDark[chartPalette.kwh].l;
                  c_barV1 = palettesDark[chartPalette.vnd][1]; c_barV2 = palettesDark[chartPalette.vnd][2]; c_lineV = palettesDark[chartPalette.vnd].l;
                  c_lineM = c_lineK; 
              }
          }
      }

      this.card.style.color = c_text; 

      const iconHtml = configIcon.includes(":") 
          ? `<ha-icon icon="${configIcon}"></ha-icon>` 
          : `<span class="emoji-icon">${configIcon}</span>`;


      const buildMonthChart = (y, m, isSearchMode = false) => {
        const mState = this._hass.states[`${this.baseSlug}_thang_${m}_${y}`];
        if (!mState) return `<div class="chart-section" style="text-align:center; padding: 20px;">Không có dữ liệu tháng ${m}/${y}</div>`;

        const m_kwh = mState.attributes.tong_san_luong_kwh || 0;
        const m_truoc = mState.attributes.tong_tien_truoc_thue || 0;
        const m_sau = mState.attributes.tong_tien_sau_thue || 0;
        const dailyData = mState.attributes.chi_tiet_ngay || {};
        const daysInSelectedMonth = new Date(y, m, 0).getDate();
        
        const fullDailyData = [];
        let validDaysCount = 0;
        let maxDayVal = -1, minDayVal = Infinity, maxDayStr = "", minDayStr = "";

        for(let i = 1; i <= daysInSelectedMonth; i++) {
          let val = Number(dailyData[`Ngay_${i < 10 ? '0'+i : i}`] ?? dailyData[`Ngay_${i}`] ?? 0) || 0;
          let isFuture = (y > currentYear) || (y === currentYear && m > currentMonth) || (y === currentYear && m === currentMonth && i > currentDay);
          fullDailyData.push({ dayNum: i, dayStr: (i < 10 ? '0'+i : i.toString()), val: isFuture ? 0 : val, isFuture: isFuture });
          
          if (!isFuture && val > 0) {
              validDaysCount++;
              if (val > maxDayVal) { maxDayVal = val; maxDayStr = i.toString(); }
              if (val < minDayVal) { minDayVal = val; minDayStr = i.toString(); }
          }
        }
        
        let maxDaily = Math.max(...fullDailyData.filter(d => !d.isFuture).map(d => d.val), 1); 

        let pointsDaily = [];
        let polylinePointsDaily = fullDailyData.map((d, index) => {
          if (d.isFuture) return null;
          let colW = 100 / fullDailyData.length;
          let x = ((index + 0.5) * colW).toFixed(4); 
          let y_coord = (100 - ((d.val / maxDaily) * 100)).toFixed(4);
          pointsDaily.push({x, y: y_coord}); return `${x},${y_coord}`;
        }).filter(p => p !== null).join(' ');

        let dotsHtmlDaily = pointsDaily.map(p => `<div class="chart-dot" style="left: ${p.x}%; top: ${p.y}%; border: 1.5px solid ${c_lineM}; background: ${c_lineM};"></div>`).join('');


        let searchStatsHtml = '';
        if (isSearchMode) {
            let avgKwh = validDaysCount > 0 ? (m_kwh / validDaysCount) : 0;
            let avgVnd = validDaysCount > 0 ? (m_sau / validDaysCount) : 0;
            if (minDayVal === Infinity) { minDayVal = 0; minDayStr = "-"; maxDayVal = 0; maxDayStr = "-"; }

            searchStatsHtml = `
              <div class="search-stats-grid">
                 <div class="s-stat-card"> <div class="s-label">⚡ Ngày cao nhất</div> <div class="s-val">Ngày ${maxDayStr}: <span class="primary">${formatNumber(maxDayVal)}</span> kWh</div> </div>
                 <div class="s-stat-card"> <div class="s-label">⚡ Ngày thấp nhất</div> <div class="s-val">Ngày ${minDayStr}: <span class="primary">${formatNumber(minDayVal)}</span> kWh</div> </div>
                 <div class="s-stat-card"> <div class="s-label">📊 Trung bình/Ngày</div> <div class="s-val"><span class="primary">${formatNumber(avgKwh)}</span> kWh</div> </div>
                 <div class="s-stat-card"> <div class="s-label">💸 Tiền TB/Ngày</div> <div class="s-val"><span class="money">${formatMoney(avgVnd)} đ</span></div> </div>
              </div>
            `;
        }

        let chartHtml = `
          <div class="chart-section">
            <div class="chart-header">
              <div class="chart-title">
                <span><ha-icon icon="mdi:chart-bar" style="font-size: clamp(18px, 4vw, 22px); color:#3b82f6;"></ha-icon> Chi tiết T${m}/${y}</span>
              </div>
              <div class="chart-stats">
                <div class="hover-zap" style="cursor: default;">
                  <div class="c-stat-val primary">${formatNumber(m_kwh)} <ha-icon icon="mdi:lightning-bolt" class="icon-kwh" style="font-size:16px; margin-left: 4px;"></ha-icon></div>
                  <div class="stat-label">Sản lượng</div>
                </div>
                <div class="hover-fly" style="cursor: default;">
                  <div class="c-stat-val money">${formatMoney(m_truoc)} <span class="emoji-money" style="font-size: 16px; margin-left: 4px;">💸</span></div>
                  <div class="stat-label">Trước VAT</div>
                </div>
                <div class="hover-fly" style="cursor: default;">
                  <div class="c-stat-val money">${formatMoney(m_sau)} <span class="emoji-money" style="font-size: 16px; margin-left: 4px;">💸</span></div>
                  <div class="stat-label">Sau VAT</div>
                </div>
              </div>
            </div>
            
            <div class="chart-container">
              <svg class="svg-overlay" preserveAspectRatio="none" viewBox="0 0 100 100">
                <polyline points="${polylinePointsDaily}" fill="none" stroke="${c_lineM}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              <div class="dots-overlay">${dotsHtmlDaily}</div>
              <div class="bar-chart">
                ${fullDailyData.map((data) => {
                  const heightPct = (data.val / maxDaily) * 100;
                  const isToday = (y === currentYear && m === currentMonth && data.dayNum === currentDay);
                  return `
                    <div class="bar-col" tabindex="0">
                      ${!data.isFuture ? `
                        <div class="bar-val bar-val-daily">${formatNumber(data.val)}</div>
                        <div class="bar" style="height: ${heightPct}%;"></div>
                      ` : ''}
                      <div class="${isToday ? 'bar-label label-active' : 'bar-label'}">${data.dayStr}</div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          </div>
        `;
        return searchStatsHtml + chartHtml;
      };

      const buildYearChart = (y, isSearchMode = false) => {
        const yState = this._hass.states[`${this.baseSlug}_nam_${y}`];
        if (!yState) return `<div class="chart-section" style="text-align:center; padding: 20px;">Không có dữ liệu năm ${y}</div>`;

        const y_kwh = yState.attributes.tong_san_luong_nam || 0;
        const y_truoc = yState.attributes.tong_tien_truoc_thue || 0;
        const y_sau = yState.attributes.tong_tien_sau_thue || 0;
        const monthlyData = yState.attributes.chi_tiet_cac_thang || {};
        
        const fullYearData = [];
        let validMonthsCount = 0;
        let maxMKwh = -1, maxMVnd = -1, minMKwh = Infinity, minMVnd = Infinity;
        let maxMStr = "", minMStr = "";

        for(let i = 1; i <= 12; i++) {
          let monthObj = monthlyData[`Thang_${i < 10 ? '0'+i : i}`] || monthlyData[`Thang_${i}`] || {};
          let kwhVal = Number(monthObj.san_luong_kwh) || 0;
          let vndVal = Number(monthObj.thanh_tien_sau_thue_vnd || monthObj.thanh_tien_vnd) || 0;
          if (!vndVal || vndVal === 0) {
            const mState = this._hass.states[`${this.baseSlug}_thang_${i}_${y}`];
            if (mState && mState.attributes) vndVal = Number(mState.attributes.tong_tien_sau_thue || mState.attributes.tong_tien_truoc_thue) || 0;
          }
          let isFuture = (y > currentYear) || (y === currentYear && i > currentMonth);
          fullYearData.push({ monthNum: i, monthStr: (i < 10 ? '0'+i : i.toString()), kwhVal: isFuture ? 0 : kwhVal, vndVal: isFuture ? 0 : vndVal, isFuture: isFuture });
        
          if (!isFuture && kwhVal > 0) {
              validMonthsCount++;
              if (kwhVal > maxMKwh) { maxMKwh = kwhVal; maxMVnd = vndVal; maxMStr = i.toString(); }
              if (kwhVal < minMKwh) { minMKwh = kwhVal; minMVnd = vndVal; minMStr = i.toString(); }
          }
        }

        let maxMonthlyKwh = Math.max(...fullYearData.filter(d=>!d.isFuture).map(d => d.kwhVal), 1);
        let maxMonthlyVnd = Math.max(...fullYearData.filter(d=>!d.isFuture).map(d => d.vndVal), 1);

        let pointsKwh = []; let pointsVnd = [];
        let polylinePointsKwh = fullYearData.map((d, index) => {
          if (d.isFuture) return null;
          let colW = 100 / 12, groupW = colW * 0.85; 
          let x = ((index * colW) + ((colW - groupW) / 2) + (groupW / 4)).toFixed(4); 
          let y_coord = (100 - ((d.kwhVal / maxMonthlyKwh) * 100)).toFixed(4);
          pointsKwh.push({x, y: y_coord}); return `${x},${y_coord}`;
        }).filter(p => p !== null).join(' ');

        let polylinePointsVnd = fullYearData.map((d, index) => {
          if (d.isFuture) return null;
          let colW = 100 / 12, groupW = colW * 0.85; 
          let x = ((index * colW) + ((colW - groupW) / 2) + (3 * groupW / 4)).toFixed(4); 
          let y_coord = (100 - ((d.vndVal / maxMonthlyVnd) * 100)).toFixed(4);
          pointsVnd.push({x, y: y_coord}); return `${x},${y_coord}`;
        }).filter(p => p !== null).join(' ');

        let dotsKwhHtml = pointsKwh.map(p => `<div class="chart-dot" style="left: ${p.x}%; top: ${p.y}%; border: 1.5px solid ${c_lineK}; background: ${c_lineK};"></div>`).join('');
        let dotsVndHtml = pointsVnd.map(p => `<div class="chart-dot" style="left: ${p.x}%; top: ${p.y}%; border: 1.5px solid ${c_lineV}; background: ${c_lineV};"></div>`).join('');

        let searchStatsHtml = '';
        if (isSearchMode) {
            let avgKwh = validMonthsCount > 0 ? (y_kwh / validMonthsCount) : 0;
            let avgVnd = validMonthsCount > 0 ? (y_sau / validMonthsCount) : 0;
            if (minMKwh === Infinity) { minMKwh = 0; minMVnd = 0; minMStr = "-"; maxMKwh = 0; maxMVnd = 0; maxMStr = "-"; }

            searchStatsHtml = `
              <div class="search-stats-grid">
                 <div class="s-stat-card"> <div class="s-label">⚡ Tháng cao nhất</div> <div class="s-val">Tháng ${maxMStr}: <span class="primary">${formatNumber(maxMKwh)}</span> kWh <br><span class="money" style="font-size: 0.9em;">(${formatMoney(maxMVnd)} đ)</span></div> </div>
                 <div class="s-stat-card"> <div class="s-label">⚡ Tháng thấp nhất</div> <div class="s-val">Tháng ${minMStr}: <span class="primary">${formatNumber(minMKwh)}</span> kWh <br><span class="money" style="font-size: 0.9em;">(${formatMoney(minMVnd)} đ)</span></div> </div>
                 <div class="s-stat-card"> <div class="s-label">📊 Trung bình/Tháng</div> <div class="s-val"><span class="primary">${formatNumber(avgKwh)}</span> kWh</div> </div>
                 <div class="s-stat-card"> <div class="s-label">💸 Tiền TB/Tháng</div> <div class="s-val"><span class="money">${formatMoney(avgVnd)} đ</span></div> </div>
              </div>
            `;
        }

        let chartHtml = `
          <div class="chart-section">
            <div class="chart-header">
              <div class="chart-title">
                <span><ha-icon icon="mdi:chart-timeline-variant" style="font-size: clamp(18px, 4vw, 22px); color:#10b981;"></ha-icon> Thống kê ${y}</span>
              </div>
              <div class="chart-stats">
                <div class="hover-zap" style="cursor: default;">
                  <div class="c-stat-val primary">${formatNumber(y_kwh)} <ha-icon icon="mdi:lightning-bolt" class="icon-kwh" style="font-size:16px; margin-left: 4px;"></ha-icon></div>
                  <div class="stat-label">Sản lượng</div>
                </div>
                <div class="hover-fly" style="cursor: default;">
                  <div class="c-stat-val money">${formatMoney(y_truoc)} <span class="emoji-money" style="font-size: 16px; margin-left: 4px;">💸</span></div>
                  <div class="stat-label">Trước VAT</div>
                </div>
                <div class="hover-fly" style="cursor: default;">
                  <div class="c-stat-val money">${formatMoney(y_sau)} <span class="emoji-money" style="font-size: 16px; margin-left: 4px;">💸</span></div>
                  <div class="stat-label">Sau VAT</div>
                </div>
              </div>
            </div>

            <div class="chart-container">
              <svg class="svg-overlay" preserveAspectRatio="none" viewBox="0 0 100 100">
                <polyline points="${polylinePointsKwh}" fill="none" stroke="${c_lineK}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" />
                <polyline points="${polylinePointsVnd}" fill="none" stroke="${c_lineV}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              <div class="dots-overlay">${dotsKwhHtml}${dotsVndHtml}</div>
              <div class="bar-chart">
                ${fullYearData.map((data) => {
                  const isCurrentMonth = (y === currentYear && data.monthNum === currentMonth);
                  return `
                    <div class="bar-col" tabindex="0">
                      <div class="bar-group">
                        ${!data.isFuture ? `
                          <div><div class="bar-val bar-val-kwh">${formatNumber(data.kwhVal)}</div><div class="bar-kwh" style="height: ${(data.kwhVal / maxMonthlyKwh) * 100}%;"></div></div>
                          <div><div class="bar-val bar-val-vnd">${formatMoney(data.vndVal)}</div><div class="bar-vnd" style="height: ${(data.vndVal / maxMonthlyVnd) * 100}%;"></div></div>
                        ` : ''}
                      </div>
                      <div class="${isCurrentMonth ? 'bar-label label-active' : 'bar-label'}">T${data.monthStr}</div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          </div>
        `;
        return searchStatsHtml + chartHtml;
      };

      const buildDecadeCharts = () => {
          if (this._yearsList.length === 0) return '';
          
          let chunks = [];
          for (let i = 0; i < this._yearsList.length; i += 10) {
              chunks.push(this._yearsList.slice(i, i + 10)); 
          }

          return chunks.map((chunk, chunkIdx) => {
              let totalKwh = 0;
              let totalTruocVat = 0;
              let totalSauVat = 0;

              let chunkData = chunk.map(y => {
                  const yState = this._hass.states[`${this.baseSlug}_nam_${y}`];
                  let kwh = 0, vnd = 0, truocVat = 0;
                  if (yState) {
                      kwh = yState.attributes.tong_san_luong_nam || 0;
                      vnd = yState.attributes.tong_tien_sau_thue || 0;
                      truocVat = yState.attributes.tong_tien_truoc_thue || 0;
                  }
                  
                  totalKwh += kwh;
                  totalTruocVat += truocVat;
                  totalSauVat += vnd;

                  return { year: y, kwh: kwh, vnd: vnd };
              });

              let maxKwh = Math.max(...chunkData.map(d => d.kwh), 1);
              let maxVnd = Math.max(...chunkData.map(d => d.vnd), 1);
              let chartLen = chunkData.length;

              let pointsKwh = []; let pointsVnd = [];
              let polylinePointsKwh = chunkData.map((d, index) => {
                let colW = 100 / chartLen, groupW = colW * 0.85; 
                let x = ((index * colW) + ((colW - groupW) / 2) + (groupW / 4)).toFixed(4); 
                let y_coord = (100 - ((d.kwh / maxKwh) * 100)).toFixed(4);
                pointsKwh.push({x, y: y_coord}); return `${x},${y_coord}`;
              }).join(' ');

              let polylinePointsVnd = chunkData.map((d, index) => {
                let colW = 100 / chartLen, groupW = colW * 0.85; 
                let x = ((index * colW) + ((colW - groupW) / 2) + (3 * groupW / 4)).toFixed(4); 
                let y_coord = (100 - ((d.vnd / maxVnd) * 100)).toFixed(4);
                pointsVnd.push({x, y: y_coord}); return `${x},${y_coord}`;
              }).join(' ');

              let dotsKwhHtml = pointsKwh.map(p => `<div class="chart-dot" style="left: ${p.x}%; top: ${p.y}%; border: 1.5px solid ${c_lineK};"></div>`).join('');
              let dotsVndHtml = pointsVnd.map(p => `<div class="chart-dot" style="left: ${p.x}%; top: ${p.y}%; border: 1.5px solid ${c_lineV};"></div>`).join('');

              let minYear = Math.min(...chunk);
              let maxYear = Math.max(...chunk);
              let titleSpan = chunk.length > 1 ? `${maxYear} - ${minYear}` : `${chunk[0]}`;

              let summaryHtml = `
                <div class="decade-summary">
                  <div class="d-sum-item hover-zap" style="cursor: default;">
                    <div class="d-sum-val">${formatNumber(totalKwh)} <ha-icon icon="mdi:lightning-bolt" class="icon-kwh" style="font-size: clamp(16px, 4vw, 20px);"></ha-icon></div>
                    <div class="d-sum-label">Sản lượng</div>
                  </div>
                  <div class="d-sum-item hover-fly" style="cursor: default;">
                    <div class="d-sum-val money">${formatMoney(totalTruocVat)} <span class="emoji-money" style="font-size: clamp(16px, 4vw, 20px);">💸</span></div>
                    <div class="d-sum-label">Trước VAT</div>
                  </div>
                  <div class="d-sum-item hover-fly" style="cursor: default;">
                    <div class="d-sum-val money">${formatMoney(totalSauVat)} <span class="emoji-money" style="font-size: clamp(16px, 4vw, 20px);">💸</span></div>
                    <div class="d-sum-label">Sau VAT</div>
                  </div>
                </div>
              `;

              return `
                <div class="chart-section" style="margin-top: 16px;">
                  <div class="chart-header" style="margin-bottom: 8px; border-bottom: none; padding-bottom: 0;">
                    <div class="chart-title">
                      <span><ha-icon icon="mdi:history" style="font-size: clamp(18px, 4vw, 22px); color:#8b5cf6;"></ha-icon> Tổng quan ${titleSpan}</span>
                    </div>
                  </div>
                  
                  ${summaryHtml}

                  <div class="chart-container">
                    <svg class="svg-overlay" preserveAspectRatio="none" viewBox="0 0 100 100">
                      <polyline points="${polylinePointsKwh}" fill="none" stroke="${c_lineK}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" />
                      <polyline points="${polylinePointsVnd}" fill="none" stroke="${c_lineV}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <div class="dots-overlay">${dotsKwhHtml}${dotsVndHtml}</div>
                    <div class="bar-chart">
                      ${chunkData.map((data) => {
                        const isCurrentYear = (data.year === currentYear);
                        return `
                          <div class="bar-col" tabindex="0">
                            <div class="bar-group">
                                <div><div class="bar-val bar-val-kwh">${formatNumber(data.kwh)}</div><div class="bar-kwh" style="height: ${(data.kwh / maxKwh) * 100}%;"></div></div>
                                <div><div class="bar-val bar-val-vnd">${formatMoney(data.vnd)}</div><div class="bar-vnd" style="height: ${(data.vnd / maxVnd) * 100}%;"></div></div>
                            </div>
                            <div class="${isCurrentYear ? 'bar-label label-active' : 'bar-label'}">${data.year}</div>
                          </div>
                        `;
                      }).join('')}
                    </div>
                  </div>
                </div>
              `;
          }).join('');
      };


      let html = `
        <style>
          :host {
            --block-bg: ${c_block};
            --text-main: ${c_text};
            --bar-k1: ${c_barK1};
            --bar-k2: ${c_barK2};
            --bar-v1: ${c_barV1};
            --bar-v2: ${c_barV2};
            --text-red: ${c_red};
            --option-bg: ${c_option_bg};
          }

          select option {
            background-color: var(--option-bg) !important;
            color: var(--text-main) !important;
          }

          .main-card-header { 
            display: flex; align-items: flex-end; gap: 12px; font-weight: 800; font-size: clamp(20px, 5vw, 24px); color: var(--text-main); margin-top: 0; margin-bottom: 12px; padding-left: 4px; line-height: 1; 
          }
          .main-card-header ha-icon, .main-card-header .emoji-icon { font-size: clamp(28px, 7vw, 36px); line-height: 1; margin-bottom: -4px; color: #f59e0b; }
          
          .top-dashboard, .chart-section, .control-pill { 
            background: var(--block-bg); border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.05); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
          }
          .top-dashboard { padding: 12px; margin-bottom: 12px; }
          .chart-section { padding: 12px; margin-bottom: 12px; position: relative; }
          .control-pill { border-radius: 50px; display: flex; align-items: center; justify-content: space-between; padding: 2px; min-width: 0; }
          
          .header-tools { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;}
          .tabs-container { display: flex; background: rgba(0,0,0,0.1); padding: 4px; border-radius: 10px; gap: 4px; border: 1px solid rgba(0,0,0,0.05);}
          .tab-item { padding: clamp(4px, 1vw, 6px) clamp(8px, 2vw, 14px); border-radius: 8px; font-size: clamp(11px, 3vw, 13px); font-weight: 700; color: var(--text-main); opacity: 0.6; cursor: pointer; transition: all 0.3s; white-space: nowrap;}
          .tab-item:hover { opacity: 0.8; }
          .tab-item.active { background: var(--block-bg); opacity: 1; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }

          select.main-sel {
            background: rgba(0,0,0,0.4); color: #ffffff; border: none; border-radius: 8px; padding: 8px 12px; font-size: 14px; font-weight: 700; outline: none; cursor: pointer; -webkit-appearance: none; appearance: none;
            background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
            background-repeat: no-repeat; background-position: right 10px center; background-size: 14px; transition: all 0.2s ease; padding-right: 30px;
          }
          select.main-sel:hover { background: rgba(0,0,0,0.6); }

          .btn-search { background: #3b82f6; color: white; border: none; padding: clamp(8px, 2vw, 10px) 16px; border-radius: 20px; font-weight: bold; cursor: pointer; transition: background 0.2s; font-size: clamp(12px, 3.5vw, 14px); white-space: nowrap; box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3);}
          .btn-search:hover { background: #2563eb; transform: translateY(-1px); }

          .search-stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: clamp(8px, 1.5vw, 16px); margin-bottom: 16px; }
          .s-stat-card { background: var(--block-bg); border-radius: 8px; padding: clamp(10px, 2vw, 20px); box-shadow: 0 2px 6px rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.05); text-align: center; display: flex; flex-direction: column; justify-content: center; min-height: clamp(60px, 8vw, 80px);}
          .s-label { font-size: clamp(11px, 2vw, 15px); font-weight: 700; color: var(--text-main); opacity: 0.7; margin-bottom: clamp(4px, 1vw, 8px); }
          .s-val { font-size: clamp(13px, 2.5vw, 18px); font-weight: 800; color: var(--text-main); line-height: 1.4; }
          .s-val .primary { color: #3b82f6; font-size: clamp(15px, 3.5vw, 24px); }
          .s-val .money { color: var(--text-red); font-size: clamp(15px, 3.5vw, 24px); }

          .global-stats-compact { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; text-align: center; width: 100%; box-sizing: border-box; }
          .stat-box { display: flex; flex-direction: column; justify-content: center; cursor: default; transition: background 0.3s; border-radius: 8px; padding: clamp(2px, 1vw, 4px) 2px; min-width: 0; overflow: hidden; }
          .stat-box.primary { border-right: 1px solid rgba(0,0,0,0.05); }
          .stat-box.primary .stat-value { color: var(--text-main); }
          .stat-value { font-size: clamp(12px, 3.5vw, 17px); font-weight: 800; color: var(--text-red); display: flex; align-items: center; justify-content: center; gap: 2px; flex-wrap: wrap; letter-spacing: -0.3px; line-height: 1.1;}
          .stat-unit { font-size: clamp(10px, 2.5vw, 13px); color: var(--text-main); opacity: 0.7; font-weight: 600; white-space: nowrap;}
          .stat-label { font-size: clamp(10px, 2.5vw, 12px); font-weight: 700; color: var(--text-main); opacity: 0.6; margin-top: 2px; letter-spacing: 0.1px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; width: 100%;}
          .emoji-money, .icon-kwh { flex-shrink: 0; }
          
          .icon-kwh { color: #f59e0b; transition: all 0.3s; transform-origin: center; display: inline-block; }
          @keyframes zapHover { 0% { transform: scale(1) rotate(0deg); filter: brightness(1); } 20% { transform: scale(1.5) rotate(-15deg); filter: brightness(1.5) drop-shadow(0 0 6px #fbbf24); color: #fcd34d; } 40% { transform: scale(1.5) rotate(15deg); filter: brightness(1.8) drop-shadow(0 0 10px #fef3c7); color: #fef3c7; } 60% { transform: scale(1.5) rotate(-15deg); filter: brightness(1.5) drop-shadow(0 0 6px #fbbf24); color: #fcd34d; } 80% { transform: scale(1.5) rotate(15deg); filter: brightness(1.2) drop-shadow(0 0 4px #f59e0b); color: #fbbf24; } 100% { transform: scale(1) rotate(0deg); filter: brightness(1); } }
          .hover-zap:hover .icon-kwh { animation: zapHover 0.7s ease-in-out forwards; }

          .emoji-money { display: inline-block; font-size: 1.2em; transition: all 0.3s; transform-origin: bottom center; }
          @keyframes flyAwayHover { 0% { transform: translate(0, 0) scale(1) rotate(0deg); opacity: 1; } 30% { transform: translate(10px, -15px) scale(1.3) rotate(15deg); opacity: 0.8; } 45% { transform: translate(25px, -30px) scale(0.5) rotate(30deg); opacity: 0; } 46% { transform: translate(-20px, 15px) scale(0); opacity: 0; } 100% { transform: translate(0, 0) scale(1) rotate(0deg); opacity: 1; } }
          .hover-fly:hover .emoji-money { animation: flyAwayHover 0.8s ease-in-out forwards; }
          
          .controls { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: clamp(4px, 2vw, 10px); margin-bottom: 12px; }
          .control-content { display: flex; align-items: center; gap: clamp(2px, 1vw, 4px); padding: 0 clamp(2px, 1vw, 6px); flex: 1; justify-content: center; border-left: 1px solid rgba(0,0,0,0.05); border-right: 1px solid rgba(0,0,0,0.05); min-width: 0;}
          .ctrl-icon { font-size: clamp(14px, 3.5vw, 18px); color: var(--text-main); flex-shrink: 0;}
          
          select.styled-sel { flex: 1; min-width: 0; width: 100%; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; background: transparent; border: none; font-weight: 800; font-size: clamp(12px, 3.5vw, 15px); color: var(--text-main); outline: none; cursor: pointer; text-align: center; text-align-last: center; -webkit-appearance: none; appearance: none; padding: 4px 16px 4px 2px; margin: 0; background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233b82f6' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e"); background-repeat: no-repeat; background-position: right 0px center; background-size: 14px; border-radius: 6px; transition: background-color 0.2s ease; }
          select.styled-sel:hover { background-color: rgba(0,0,0,0.05); } 
          
          .nav-btn { cursor: pointer; display: flex; align-items: center; justify-content: center; width: clamp(24px, 6vw, 28px); height: clamp(24px, 6vw, 28px); border-radius: 50%; color: #3b82f6; transition: all 0.2s; user-select: none; background: transparent; flex-shrink: 0;}
          .nav-btn:hover { background: rgba(59, 130, 246, 0.1); color: var(--text-main); }
          .nav-btn ha-icon { font-size: clamp(18px, 5vw, 20px); }

          .chart-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid rgba(0,0,0,0.05); padding-bottom: 8px; }
          .chart-title { font-weight: 800; font-size: clamp(14px, 3.8vw, 18px); display: flex; align-items: flex-end; gap: 4px; color: var(--text-main); width: 100%; justify-content: space-between; margin-bottom: 4px;}
          .chart-title span { display: flex; align-items: flex-end; gap: 6px; line-height: 1; }
          .chart-stats { display: flex; gap: 4px; text-align: right; width: 100%; justify-content: space-between; flex-wrap: wrap; }
          .c-stat-val { font-size: clamp(11px, 3vw, 16px); font-weight: 800; display:flex; align-items:center; justify-content:flex-end; gap: 2px; flex-wrap: wrap; letter-spacing: -0.3px;}
          .c-stat-val.primary { color: var(--text-main); } .c-stat-val.money { color: var(--text-red); }   
          
          .decade-summary { display: flex; justify-content: space-between; align-items: center; padding: 4px 8px 12px 8px; margin-bottom: 12px; border-bottom: 1px dashed rgba(0,0,0,0.08);}
          .d-sum-item { display: flex; flex-direction: column; }
          .d-sum-item:nth-child(1) { align-items: flex-start; }
          .d-sum-item:nth-child(2) { align-items: center; }
          .d-sum-item:nth-child(3) { align-items: flex-end; }
          .d-sum-val { font-size: clamp(14px, 4vw, 22px); font-weight: 900; display: flex; align-items: center; gap: 4px; color: var(--text-main); letter-spacing: -0.5px; line-height: 1.1;}
          .d-sum-val.money { color: var(--text-red); }
          .d-sum-label { font-size: clamp(10px, 2.5vw, 12px); font-weight: 600; color: var(--text-main); opacity: 0.6; margin-top: 4px; }

          .chart-container { position: relative; height: 130px; margin-top: 50px; margin-bottom: 16px; }
          .bar-chart { display: flex; align-items: flex-end; justify-content: space-between; height: 100%; gap: 0; position: relative; width: 100%;}
          .bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; position: relative; cursor: pointer; z-index: 2; transition: z-index 0.3s; }
          .bar-col:hover, .bar-col:focus-within { z-index: 50; }
          
          .bar { width: 75%; margin: 0 auto; background: linear-gradient(180deg, var(--bar-k1) 0%, var(--bar-k2) 100%); border-radius: 3px 3px 0 0; transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1); position: relative; min-height: 2px; }
          .bar:hover { filter: brightness(1.2); transform: scaleY(1.02); transform-origin: bottom; }
          
          .bar-group { display: flex; align-items: flex-end; justify-content: center; gap: 0; width: 85%; height: 100%; margin: 0 auto; cursor: pointer; z-index: 10;}
          .bar-group > div { position: relative; transition: z-index 0.3s; z-index: 10; width: 50%; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center;}
          
          .bar-kwh, .bar-vnd { transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1); min-height: 2px; width: 100%; }
          .bar-kwh:hover, .bar-vnd:hover { filter: brightness(1.2); }
          .bar-kwh { background: linear-gradient(180deg, var(--bar-k1) 0%, var(--bar-k2) 100%); border-radius: 3px 0 0 0; }
          .bar-vnd { background: linear-gradient(180deg, var(--bar-v1) 0%, var(--bar-v2) 100%); border-radius: 0 3px 0 0; }

          .bar-val { position: absolute; top: -24px; font-size: 8px; font-weight: 800; color: var(--text-main); width: max-content; text-align: center; white-space: nowrap; left: 50%; transform: translateX(-50%) rotate(-45deg); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); z-index: 5; pointer-events: none; display: flex; align-items: center; justify-content: center; opacity: 0.8;}
          .bar-col:hover .bar-val, .bar-col:focus-within .bar-val, .bar-group > div:hover .bar-val, .bar-group > div:focus-within .bar-val { z-index: 100; background: var(--block-bg) !important; padding: 2px 4px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); transform-origin: 50% 100%; opacity: 1;}

          .bar-col:hover .bar-val-daily { transform: translateX(-50%) translateY(-20px) rotate(0deg) scale(2); color: var(--text-main) !important; }
          .bar-col:hover .bar-val-vnd { left: 0%; transform: translateX(-50%) translateY(-40px) rotate(0deg) scale(2); color: var(--text-red) !important; z-index: 101; }
          .bar-col:hover .bar-val-kwh { left: 100%; transform: translateX(-50%) translateY(-5px) rotate(0deg) scale(2); color: var(--text-main) !important; z-index: 100;}

          .bar-label { position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%); font-size: clamp(8px, 2vw, 10px); font-weight: 600; color: var(--text-main); opacity: 0.7; margin-top: 0; text-align: center; width: 100%; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);}
          .bar-col:hover .bar-label, .bar-col:focus-within .bar-label { transform: translateX(-50%) scale(1.4) !important; opacity: 1 !important; font-weight: 800; color: var(--text-main); z-index: 100;}
          
          @keyframes pulseColor { 0% { color: #f59e0b; text-shadow: 0 0 0px rgba(245,158,11,0); transform: translateX(-50%) scale(1); } 50% { color: var(--text-red); text-shadow: 0 0 6px rgba(220,38,38,0.3); transform: translateX(-50%) scale(1.15); } 100% { color: #f59e0b; text-shadow: 0 0 0px rgba(245,158,11,0); transform: translateX(-50%) scale(1); } }
          .label-active { font-weight: 900 !important; animation: pulseColor 1.5s infinite ease-in-out; opacity: 1 !important;}
          
          .svg-overlay { position: absolute; top: -2px; left: -2px; width: calc(100% + 4px); height: calc(100% + 4px); pointer-events: none; z-index: 5; overflow: hidden; filter: drop-shadow(0px 2px 2px rgba(0,0,0,0.1)); }
          .svg-overlay polyline { filter: drop-shadow(0px 3px 4px rgba(0,0,0,0.4)); }
          .dots-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 6;}
          .chart-dot { position: absolute; width: 3px; height: 3px; background: var(--block-bg); border-radius: 50%; transform: translate(-50%, -50%); box-shadow: 0 2px 4px rgba(0,0,0,0.5); }
        </style>

        <div class="main-card-header">
          ${iconHtml} <span>${displayTitle}</span>
        </div>

        <div class="header-tools">
            <div class="tabs-container">
                <div class="tab-item ${this._activeTab === 'overview' ? 'active' : ''}" data-tab="overview">Tổng quan</div>
                <div class="tab-item ${this._activeTab === 'search' ? 'active' : ''}" data-tab="search">Tra cứu</div>
            </div>
            ${this._availableInstances.length > 1 ? `
              <select id="sel-instance" class="main-sel">
                ${this._availableInstances.map(inst => `
                  <option value="${inst.id}" ${this._currentEntityId === inst.id ? 'selected' : ''}>${inst.name}</option>
                `).join('')}
              </select>
            ` : ''}
        </div>
      `;

      if (this._activeTab === 'overview') {
          const t_kwh = totalState.state;
          const t_truoc = totalState.attributes.tong_tien_tich_luy;
          const t_sau = totalState.attributes.tong_tien_tich_luy_sau_thue;

          html += `
            <div class="top-dashboard">
              <div class="global-stats-compact">
                <div class="stat-box primary hover-zap">
                  <div class="stat-value"><ha-icon icon="mdi:lightning-bolt" class="icon-kwh"></ha-icon> ${formatNumber(t_kwh)} <span class="stat-unit">kWh</span></div>
                  <div class="stat-label">Tổng sản lượng</div>
                </div>
                <div class="stat-box hover-fly">
                  <div class="stat-value"><span class="emoji-money">💸</span> ${formatMoney(t_truoc)} <span class="stat-unit">đ</span></div>
                  <div class="stat-label">Trước VAT</div>
                </div>
                <div class="stat-box hover-fly">
                  <div class="stat-value"><span class="emoji-money">💸</span> ${formatMoney(t_sau)} <span class="stat-unit">đ</span></div>
                  <div class="stat-label">Sau VAT</div>
                </div>
              </div>
            </div>

            <div class="controls">
              <div class="control-pill">
                <div class="nav-btn btn-y-prev" title="Năm trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
                <div class="control-content">
                  <ha-icon icon="mdi:calendar-blank" class="ctrl-icon"></ha-icon>
                  <select id="sel-year" class="styled-sel">
                    ${this._yearsList.map(y => `<option value="${y}" ${this._selectedYear === y ? 'selected' : ''}>${y}</option>`).join('')}
                  </select>
                </div>
                <div class="nav-btn btn-y-next" title="Năm sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
              </div>
              <div class="control-pill">
                <div class="nav-btn btn-m-prev" title="Tháng trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
                <div class="control-content">
                  <ha-icon icon="mdi:calendar-month" class="ctrl-icon"></ha-icon>
                  <select id="sel-month" class="styled-sel">
                    ${this._monthsList.map(m => `<option value="${m}" ${this._selectedMonth === m ? 'selected' : ''}>${m}</option>`).join('')}
                  </select>
                </div>
                <div class="nav-btn btn-m-next" title="Tháng sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
              </div>
            </div>
          `;

          html += buildMonthChart(this._selectedYear, this._selectedMonth, false);
          html += buildYearChart(this._selectedYear, false);

      } else {
          html += `
             <div class="controls" style="margin-bottom: 12px;">
              <div class="control-pill">
                <div class="nav-btn btn-sy-prev" title="Năm trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
                <div class="control-content">
                  <ha-icon icon="mdi:calendar-blank" class="ctrl-icon"></ha-icon>
                  <select id="sel-search-year" class="styled-sel">
                    ${this._yearsList.map(y => `<option value="${y}" ${this._formYear === y ? 'selected' : ''}>${y}</option>`).join('')}
                  </select>
                </div>
                <div class="nav-btn btn-sy-next" title="Năm sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
              </div>
              
              <div class="control-pill">
                <div class="nav-btn btn-sm-prev" title="Tháng trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
                <div class="control-content">
                  <ha-icon icon="mdi:calendar-month" class="ctrl-icon"></ha-icon>
                  <select id="sel-search-month" class="styled-sel">
                    <option value="" ${this._formMonth === '' ? 'selected' : ''}>-- Cả năm --</option>
                    ${[1,2,3,4,5,6,7,8,9,10,11,12].map(m => `<option value="${m}" ${this._formMonth == m ? 'selected' : ''}>${m}</option>`).join('')}
                  </select>
                </div>
                <div class="nav-btn btn-sm-next" title="Tháng sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
              </div>
            </div>

            <div style="display: flex; justify-content: center; margin-bottom: 16px;">
                <button id="btn-do-search" class="btn-search" style="width: 100%;">
                    <ha-icon icon="mdi:magnify" style="font-size:18px; margin-right:4px; margin-bottom:-2px;"></ha-icon> Bắt đầu Tra cứu
                </button>
            </div>
          `;

          if (this._hasSearched && this._searchYear) {
              if (this._searchMonth !== null) {
                  html += buildMonthChart(this._searchYear, this._searchMonth, true);
              } else {
                  html += buildYearChart(this._searchYear, true);
              }
          }

          html += buildDecadeCharts();
      }

      if (this._lastHtml !== html) {
        this.card.innerHTML = html;
        this._lastHtml = html;
      }
    }
  }

  customElements.define('electricity-consumption-editor', ElectricityConsumptionEditor);
  customElements.define('electricity-consumption-card', ElectricityConsumptionCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "electricity-consumption-card",
    name: "Thống kê Điện năng",
    description: "Thẻ hiển thị thống kê tiêu thụ điện năng có hỗ trợ Nền Gradient & Tương phản.",
    preview: true,
  });

})();
