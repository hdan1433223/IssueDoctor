import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";


function element(overrides = {}) {
  const listeners = {};
  const classes = new Set();
  const style = {
    removeProperty(name) {
      delete this[name];
    }
  };
  return {
    dataset: {},
    children: [],
    hidden: false,
    offsetWidth: 56,
    offsetHeight: 56,
    style,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      toggle: (name, active) => active ? classes.add(name) : classes.delete(name),
      contains: (name) => classes.has(name)
    },
    addEventListener(name, callback) {
      listeners[name] = callback;
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    remove() {
      this.removed = true;
    },
    querySelectorAll() {
      return [];
    },
    setAttribute(name, value) {
      this[name] = value;
    },
    getAttribute(name) {
      return this[name] ?? null;
    },
    focus() {},
    setPointerCapture() {},
    releasePointerCapture() {},
    hasPointerCapture() { return true; },
    getBoundingClientRect() { return this.rect; },
    listeners,
    ...overrides
  };
}


test("drag moves and stores the launcher without opening the panel", async () => {
  const meta = {content: "csrf"};
  const launcher = element();
  const panel = element({hidden: true, offsetWidth: 520, offsetHeight: 740});
  const root = element({offsetWidth: 56});
  launcher.getBoundingClientRect = () => {
    const left = root.style.left ? Number.parseFloat(root.style.left) : 1000;
    const top = root.style.top ? Number.parseFloat(root.style.top) : 600;
    return {left, top, width: 56, height: 56, right: left + 56, bottom: top + 56};
  };
  const closeButton = element();
  const clearButton = element();
  const form = element();
  const input = element();
  const submit = element();
  const messages = element();
  const status = element();
  const roots = new Map([
    ["[data-assistant-launcher]", launcher],
    ["[data-assistant-panel]", panel],
    ["#assistant-panel", panel],
    ["[data-assistant-close]", closeButton],
    ["[data-assistant-clear]", clearButton],
    ["[data-assistant-form]", form],
    ["[data-assistant-input]", input],
    ["[data-assistant-submit]", submit],
    ["[data-assistant-messages]", messages],
    ["[data-assistant-status]", status]
  ]);
  root.querySelector = (selector) => roots.get(selector) || null;
  root.querySelectorAll = () => [];
  root.dataset.runId = "run-one";
  const storage = new Map();
  const sessionStorageData = new Map();
  const windowListeners = {};
  const window = {
    innerWidth: 1440,
    innerHeight: 900,
    localStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value)
    },
    sessionStorage: {
      getItem: (key) => sessionStorageData.get(key) || null,
      setItem: (key, value) => sessionStorageData.set(key, value),
      removeItem: (key) => sessionStorageData.delete(key)
    },
    matchMedia: () => ({matches: false}),
    addEventListener: (name, callback) => { windowListeners[name] = callback; },
    setTimeout: (callback) => callback(),
    confirm: () => true,
    requestAnimationFrame: (callback) => callback()
  };
  const document = {
    querySelector: (selector) => selector === "[data-assistant-root]" ? root : selector === 'meta[name="csrf-token"]' ? meta : null,
    createElement: () => element(),
    addEventListener() {}
  };
  vm.runInNewContext(
    readFileSync("issuedoctor/static/js/assistant.js", "utf8"),
    {window, document, JSON, Math, Number, console}
  );

  launcher.listeners.pointerdown({button: 0, pointerId: 1, clientX: 1020, clientY: 620});
  launcher.listeners.pointermove({pointerId: 1, clientX: 820, clientY: 420});
  launcher.listeners.pointerup({pointerId: 1});
  launcher.listeners.click({preventDefault() {}});

  assert.equal(root.style.left, "800px");
  assert.equal(root.style.top, "400px");
  assert.equal(root.style.right, "auto");
  assert.equal(root.style.bottom, "auto");
  assert.equal(panel.hidden, true);
  assert.equal(
    storage.get("issuedoctor.assistant.position.v1"),
    JSON.stringify({x: 800 / 1440, y: 400 / 900})
  );

  await new Promise((resolve) => setTimeout(resolve, 260));
  launcher.listeners.click({preventDefault() {}});
  assert.equal(panel.hidden, false);
  assert.equal(launcher["aria-expanded"], "true");
  assert.equal(panel.style.left !== undefined, true);
  assert.equal(panel.style.top !== undefined, true);
  assert.equal(typeof windowListeners.resize, "function");
});


test("restores a completed conversation for the same report", () => {
  const transcriptKey = "issuedoctor.assistant.transcript.run-two.v1";
  const saved = {
    transcript: [
      {kind: "user", text: "旧问题"},
      {
        kind: "result",
        result: {
          answer: "旧答案",
          key_points: [],
          limitations: "",
          mode: "extractive",
          sources: []
        }
      }
    ],
    history: [
      {role: "user", content: "旧问题"},
      {role: "assistant", content: "旧答案"}
    ]
  };
  const meta = {content: "csrf"};
  const launcher = element();
  const panel = element({hidden: true, offsetWidth: 520, offsetHeight: 740});
  const root = element({offsetWidth: 56});
  const messages = element();
  messages.scrollTop = 0;
  messages.scrollHeight = 100;
  const status = element();
  const elements = new Map([
    ["[data-assistant-launcher]", launcher],
    ["[data-assistant-panel]", panel],
    ["#assistant-panel", panel],
    ["[data-assistant-close]", element()],
    ["[data-assistant-clear]", element()],
    ["[data-assistant-form]", element()],
    ["[data-assistant-input]", element()],
    ["[data-assistant-submit]", element()],
    ["[data-assistant-messages]", messages],
    ["[data-assistant-status]", status]
  ]);
  root.dataset.runId = "run-two";
  root.querySelector = (selector) => elements.get(selector) || null;
  root.querySelectorAll = () => [];
  launcher.getBoundingClientRect = () => ({left: 1000, top: 600, width: 56, height: 56, right: 1056, bottom: 656});
  const sessionStorageData = new Map([[transcriptKey, JSON.stringify(saved)]]);
  const window = {
    innerWidth: 1440,
    innerHeight: 900,
    localStorage: {getItem: () => null, setItem() {}},
    sessionStorage: {
      getItem: (key) => sessionStorageData.get(key) || null,
      setItem: (key, value) => sessionStorageData.set(key, value),
      removeItem: (key) => sessionStorageData.delete(key)
    },
    matchMedia: () => ({matches: false}),
    addEventListener() {},
    setTimeout: (callback) => callback(),
    confirm: () => true
  };
  const document = {
    querySelector: (selector) => selector === "[data-assistant-root]" ? root : selector === 'meta[name="csrf-token"]' ? meta : null,
    createElement: () => element(),
    addEventListener() {}
  };
  vm.runInNewContext(
    readFileSync("issuedoctor/static/js/assistant.js", "utf8"),
    {window, document, JSON, Math, Number, console}
  );

  assert.equal(messages.children.length, 2);
  assert.equal(messages.children[0].children[0].textContent, "旧问题");
  assert.equal(messages.children[1].children[1].textContent, "旧答案");
  assert.equal(status.textContent, "已恢复本次报告的对话");
});
