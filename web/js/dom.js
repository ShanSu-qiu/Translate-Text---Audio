// Tiny DOM helpers. Everything dynamic goes through textContent / setAttribute, never innerHTML.

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  node.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
  return node;
}

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export function emit(name, detail) {
  document.dispatchEvent(new CustomEvent(name, { detail }));
}

export function on(name, handler) {
  document.addEventListener(name, (event) => handler(event.detail));
}

export function setStatus(node, message, tone = "info") {
  node.textContent = message;
  node.dataset.tone = tone;
}
