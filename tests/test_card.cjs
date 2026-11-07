/** Dependency-free smoke checks of the Lovelace card in a simulated DOM. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeElement {
  constructor() {
    this.innerHTML = '';
    this.style = { setProperty(key, value) { this[key] = value; } };
    this.handlers = {};
    this.dataset = {};
  }
  attachShadow() {
    this.shadowRoot = {
      children: [], appendChild(node) { this.children.push(node); },
      getElementById() { return null; },
    };
    return this.shadowRoot;
  }
  addEventListener(event, fn) { this.handlers[event] = fn; }
  removeEventListener(event) { delete this.handlers[event]; }
  dispatchEvent(event) { this.lastEvent = event; return true; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
const elements = new Map();
global.HTMLElement = FakeElement;
global.document = { createElement() { return new FakeElement(); } };
global.customElements = {
  get(name) { return elements.get(name); },
  define(name, ctor) { assert(!elements.has(name)); elements.set(name, ctor); },
};
global.window = { customCards: [], matchMedia: () => ({ matches: false }) };
global.CustomEvent = class { constructor(type, opts) { this.type = type; this.detail = opts.detail; } };

const cardPath = path.resolve(__dirname, '../custom_components/electricity_consumption_tracker/frontend/electricity-consumption-card.js');
const code = fs.readFileSync(cardPath, 'utf8');
vm.runInThisContext(code, { filename: cardPath });
vm.runInThisContext(code, { filename: cardPath }); // two resources must not register twice
assert.equal(window.customCards.length, 1);
const Card = elements.get('electricity-consumption-card');
const Editor = elements.get('electricity-consumption-editor');
assert(Card && Editor);
assert.equal(Card.getStubConfig({ states: {} }).entity, '');
assert.equal(new Card().getCardSize(), 9);
assert.equal(new Card().getGridOptions().columns, 12);

const total = 'sensor.home_total_all_time';
const year = 'sensor.home_nam_2026';
const month = 'sensor.home_thang_11_2026';
const hass = {
  states: {
    [total]: { state: '12', attributes: {
      friendly_name: 'Nhà Total All Time',
      chi_tiet_tung_nam: { Nam_2026: { tong_san_luong_kwh: 12, tong_tien_vnd: 23000 } },
    } },
    [year]: { state: '23000', attributes: {
      tong_san_luong_nam: 12, tong_tien_truoc_thue: 23000, tong_tien_sau_thue: 24840,
      chi_tiet_cac_thang: { Thang_11: { san_luong_kwh: 12, thanh_tien_vnd: 23000 } },
    } },
    [month]: { state: '23000', attributes: {
      tong_san_luong_kwh: 12, tong_tien_truoc_thue: 23000,
      tong_tien_sau_thue: 24840, ky_hoa_don: '2026-10-15 -> 2026-11-14',
      chi_tiet_ngay: { Ngay_01: 12 }, chi_tiet_ngay_iso: { '2026-11-01': 12 },
    } },
  },
  entities: {}, devices: {}, themes: { darkMode: false },
};
const card = new Card();
card.setConfig({ entity: total, title: '<script>alert(1)</script>', lineKwh: '"><script>alert(1)</script>' });
card.hass = hass;
assert.equal(card._currentEntityId, total);
assert(card._yearsList.includes(2026));
assert(card._monthsList.includes(11));
assert(card.card.innerHTML.includes('&lt;script&gt;'));
assert(!card.card.innerHTML.includes('<script>'));
assert(!card.card.innerHTML.includes('"><script>'));
assert(card._buildMonthChart(2026, 11, card._resolveColors()).includes('Chi tiết T11/2026'));
assert(card._buildYearChart(2026, card._resolveColors()).includes('2026'));
card._handleChange({ target: { id: 'sel-year', value: '2026' } });
card.disconnectedCallback();

// Renamed entity IDs still resolve through HA entity registry unique_id/device_id.
const renamedYear = 'sensor.custom_year';
const renamedMonth = 'sensor.custom_month';
const renamedHass = {
  ...hass,
  states: { [total]: hass.states[total], [renamedYear]: hass.states[year], [renamedMonth]: hass.states[month] },
  entities: {
    [total]: { device_id: 'meter-1', unique_id: 'abc_total_all_time' },
    [renamedYear]: { device_id: 'meter-1', unique_id: 'abc_bill_2026' },
    [renamedMonth]: { device_id: 'meter-1', unique_id: 'abc_bill_2026_11' },
  },
};
const renamedCard = new Card();
renamedCard.setConfig({ entity: total });
renamedCard.hass = renamedHass;
assert.equal(renamedCard._getPeriodState('year', 2026), renamedHass.states[renamedYear]);
assert.equal(renamedCard._getPeriodState('month', 2026, 11), renamedHass.states[renamedMonth]);
assert(renamedCard.card.innerHTML.includes('Chi tiết T11/2026'));

const emptyCard = new Card();
emptyCard.setConfig({});
emptyCard.hass = { states: {}, entities: {}, devices: {} };
assert(emptyCard.card.innerHTML.includes('Chưa có sensor'));
const editor = new Editor();
editor.setConfig({ entity: total });
editor.hass = hass;
assert(editor.innerHTML.includes('entity-select'));

console.log('Lovelace card: registration, config editor, charts, escaping, rename, empty states OK');
