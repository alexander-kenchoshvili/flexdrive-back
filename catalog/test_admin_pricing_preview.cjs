const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'static/catalog/admin_product_pricing_preview.js'), 'utf8');

function form(initial = {}, exact = "0") {
  const fields = {};
  for (const [name, value] of Object.entries({ supplier_price: '100', price: '100',
    markup_percent_override: '', pricing_input: '', category: '1', ...initial })) {
    fields[name] = { value, handlers: {}, validity: '',
      addEventListener(event, callback) { this.handlers[event] = callback; },
      setCustomValidity(message) { this.validity = message; },
      getAttribute() { return exact; } };
  }
  const nodes = {};
  const document = { readyState: 'complete',
    getElementById(id) { return fields[id.replace('id_', '')]; },
    querySelector(selector) { return nodes[selector] ||= { textContent: '' }; } };
  vm.runInNewContext(source, { document });
  function edit(name, value, event = 'input') {
    fields[name].value = value;
    fields[name].handlers[event]();
  }
  return { fields, edit };
}

test('amount entry and then percentage entry select the last edited field', () => {
  const { fields, edit } = form();
  edit('price', '120');
  assert.equal(fields.markup_percent_override.value, '20.00');
  assert.equal(fields.pricing_input.value, 'price');
  edit('markup_percent_override', '25');
  assert.equal(fields.price.value, '125.00');
  assert.equal(fields.pricing_input.value, 'markup');
});

test('clearing markup uses zero and category changes have no pricing handler', () => {
  const { fields, edit } = form();
  assert.equal(fields.category.handlers.change, undefined);
  edit('price', '150');
  edit('markup_percent_override', '');
  assert.equal(fields.price.value, '100.00');
  assert.equal(fields.markup_percent_override.value, '');
});

test('recurring percentage preserves cents when switching source', () => {
  const { fields, edit } = form();
  edit('supplier_price', '73');
  edit('price', '100');
  assert.equal(fields.markup_percent_override.value, '36.99');
  edit('markup_percent_override', fields.markup_percent_override.value);
  assert.equal(fields.price.value, '100.00');
});

test('decimal half cents round up without floating point drift', () => {
  const { fields, edit } = form();
  edit('supplier_price', '1');
  edit('markup_percent_override', '0.5');
  assert.equal(fields.price.value, '1.01');
});

test('supplier changes use the selected input source', () => {
  const { fields, edit } = form();
  edit('markup_percent_override', '20');
  edit('supplier_price', '110');
  assert.equal(fields.price.value, '132.00');
  edit('price', '121');
  assert.equal(fields.markup_percent_override.value, '10.00');
});

test('undefined percentage and out-of-range amounts block submission', () => {
  const { fields, edit } = form();
  edit('supplier_price', '0');
  edit('price', '120');
  assert.notEqual(fields.price.validity, '');
  edit('supplier_price', '100');
  assert.equal(fields.price.validity, '');
  edit('price', '99');
  assert.notEqual(fields.price.validity, '');
  edit('price', '1101');
  assert.notEqual(fields.price.validity, '');
});

test('initialization and manual products do not overwrite entered prices', () => {
  const { fields, edit } = form();
  assert.equal(fields.price.value, '100');
  assert.equal(fields.pricing_input.value, '');
  edit('supplier_price', '');
  edit('price', '120');
  assert.equal(fields.price.value, '120');
  assert.equal(fields.markup_percent_override.value, '');
});


test('rounded initial display retains precise percentage when supplier price changes', () => {
  const { fields, edit } = form({supplier_price: '3999', price: '4999.99', markup_percent_override: '25.03'}, '25.0310077519');
  edit('supplier_price', '4000');
  assert.equal(fields.price.value, '5001.24');
  assert.equal(fields.pricing_input.value, 'supplier');
  edit('markup_percent_override', '25.03');
  assert.equal(fields.price.value, '5001.20');
});
