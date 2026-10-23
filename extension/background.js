const BRIDGE_URL = "ws://localhost:9444";
let ws = null;
let MATCH = "goofish.com";

chrome.alarms.create("keepAlive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN) connect();
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_STATUS") {
    sendResponse({
      success: true,
      status: { wsConnected: ws !== null && ws.readyState === WebSocket.OPEN },
    });
    return true;
  }
  return false;
});

function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return;
  ws = new WebSocket(BRIDGE_URL);
  ws.onopen = () => {
    console.log("[Xianyu Bridge] connected");
    ws.send(JSON.stringify({ role: "extension" }));
  };
  ws.onmessage = async (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }
    try {
      const result = await handleCommand(msg);
      ws.send(JSON.stringify({ id: msg.id, result: result ?? null }));
    } catch (err) {
      ws.send(JSON.stringify({ id: msg.id, error: String(err.message || err) }));
    }
  };
  ws.onclose = () => setTimeout(connect, 3000);
  ws.onerror = (e) => console.warn("[Xianyu Bridge] websocket error", e);
}

async function handleCommand(msg) {
  const { method, params = {} } = msg;
  switch (method) {
    case "set_match": MATCH = params.value || "goofish.com"; return MATCH;
    case "get_match": return MATCH;
    case "navigate": return await cmdNavigate(params.url);
    case "wait_for_load": return await cmdWaitForLoad(params.timeout || 60000);
    case "get_url": return (await getCurrentTab()).url || "";
    case "get_title": return (await getCurrentTab()).title || "";
    case "evaluate": return await cmdEvaluate(params.expression);
    case "has_element": return await cmdEvaluate(`!!document.querySelector(${JSON.stringify(params.selector)})`);
    case "wait_for_selector": return await cmdWaitForSelector(params.selector, params.timeout || 30000);
    case "get_elements_count": return await cmdEvaluate(`document.querySelectorAll(${JSON.stringify(params.selector)}).length`);
    case "get_element_text": return await cmdEvaluate(`(document.querySelector(${JSON.stringify(params.selector)})||{}).innerText || null`);
    case "get_element_attribute":
      return await cmdEvaluate(`(document.querySelector(${JSON.stringify(params.selector)})||{}).getAttribute?.(${JSON.stringify(params.attr)}) ?? null`);
    case "click_element": return await cmdClick(params.selector);
    case "click_text": return await cmdClickText(params.text);
    case "click_trusted": return await cmdClickTrusted(params.selector, params.text);
    case "input_text": return await cmdInputText(params.selector, params.text);
    case "input_content_editable": return await cmdInputContentEditable(params.selector, params.text);
    case "press_key": return await cmdPressKey(params.key || params.value || "Enter");
    case "type_text": return await cmdTypeText(params.text || "");
    case "set_file_input": return await cmdSetFileInput(params.selector || "input[type=file]", params.files || []);
    case "screenshot": return await cmdScreenshot();
    case "get_cookies": return await cmdGetCookies(params.domain || "goofish.com");
    default: throw new Error(`Unsupported method: ${method}`);
  }
}

async function getCurrentTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  let tab = tabs.find(t => (t.url || "").includes(MATCH));
  if (!tab) {
    const all = await chrome.tabs.query({});
    tab = all.find(t => (t.url || "").includes(MATCH));
  }
  if (!tab) {
    tab = await chrome.tabs.create({ url: "https://www.goofish.com/", active: true });
    await sleep(1500);
  }
  return tab;
}

async function cmdNavigate(url) {
  const tab = await getCurrentTab();
  await chrome.tabs.update(tab.id, { url, active: true });
  await waitTabComplete(tab.id, 60000).catch(() => {});
  return true;
}

async function cmdWaitForLoad(timeout) {
  const tab = await getCurrentTab();
  await waitTabComplete(tab.id, timeout);
  return true;
}

function waitTabComplete(tabId, timeout) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("wait_for_load timeout"));
    }, timeout);
    const listener = (id, info) => {
      if (id === tabId && info.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve(true);
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime.lastError) return;
      if (tab.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve(true);
      }
    });
  });
}

async function cmdEvaluate(expression) {
  const tab = await getCurrentTab();
  const [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    world: "MAIN",
    func: (expr) => {
      // eslint-disable-next-line no-eval
      return eval(expr);
    },
    args: [expression],
  });
  return res?.result;
}

async function cmdWaitForSelector(selector, timeout) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const ok = await cmdEvaluate(`!!document.querySelector(${JSON.stringify(selector)})`);
    if (ok) return true;
    await sleep(300);
  }
  return false;
}

async function cmdClick(selector) {
  return await cmdEvaluate(`(() => {
    const nodes = Array.from(document.querySelectorAll(${JSON.stringify(selector)}));
    if (!nodes.length) throw new Error("element not found: " + ${JSON.stringify(selector)});
    const el = nodes.find(n => {
      const r = n.getBoundingClientRect();
      const s = getComputedStyle(n);
      return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden";
    }) || nodes[0];
    const target = el.closest("button,a,[role=button],[tabindex],label") || el;
    target.scrollIntoView({ block: "center", inline: "center" });
    target.focus?.();
    const r = target.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    for (const type of ["pointerdown","mousedown","pointerup","mouseup","click"]) {
      target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }));
    }
    return true;
  })()`);
}

async function cmdClickText(text) {
  return await cmdEvaluate(`(() => {
    const wanted = ${JSON.stringify(text)};
    const nodes = Array.from(document.querySelectorAll("button,a,span,div,label,[role=option],[role=button]"));
    const el = nodes.find(n => (n.innerText || n.textContent || "").trim() === wanted)
      || nodes.find(n => (n.innerText || n.textContent || "").includes(wanted));
    if (!el) throw new Error("text not found: " + wanted);
    const target = el.closest("button,a,[role=option],[role=button],[tabindex],label") || el;
    target.scrollIntoView({ block: "center", inline: "center" });
    target.focus?.();
    const r = target.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    for (const type of ["pointerdown","mousedown","pointerup","mouseup","click"]) {
      target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }));
    }
    return true;
  })()`);
}

async function cmdInputText(selector, text) {
  return await cmdEvaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error("input not found: " + ${JSON.stringify(selector)});
    el.scrollIntoView({ block: "center" });
    el.focus?.();
    const value = ${JSON.stringify(text)};
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);
}

async function cmdInputContentEditable(selector, text) {
  return await cmdEvaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error("editor not found: " + ${JSON.stringify(selector)});
    el.scrollIntoView({ block: "center" });
    el.focus?.();
    el.innerText = ${JSON.stringify(text)};
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: ${JSON.stringify(text)} }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`);
}

async function cmdPressKey(key) {
  return await cmdEvaluate(`(() => {
    const el = document.activeElement || document.body;
    el.dispatchEvent(new KeyboardEvent("keydown", { key: ${JSON.stringify(key)}, bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { key: ${JSON.stringify(key)}, bubbles: true }));
    return true;
  })()`);
}

async function cmdTypeText(text) {
  return await cmdEvaluate(`(() => {
    const el = document.activeElement;
    if (!el) throw new Error("no active element");
    const text = ${JSON.stringify(text)};
    if (el.isContentEditable) {
      document.execCommand("insertText", false, text);
    } else {
      const start = el.selectionStart ?? el.value?.length ?? 0;
      const end = el.selectionEnd ?? start;
      el.value = (el.value || "").slice(0, start) + text + (el.value || "").slice(end);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    return true;
  })()`);
}

// 用 CDP Input.dispatchMouseEvent 产生 isTrusted=true 的真实鼠标事件。
// 闲鱼对「发布」按钮校验事件可信度，JS dispatchEvent 的合成事件会被静默忽略，必须走这条。
async function cmdClickTrusted(selector, text) {
  const picker = text
    ? `(Array.from(document.querySelectorAll("button,a,span,div,label,[role=button],[role=option]"))
         .find(n => (n.innerText||n.textContent||"").trim() === ${JSON.stringify(text)})
       || Array.from(document.querySelectorAll("button,a,span,div,label,[role=button],[role=option]"))
         .find(n => (n.innerText||n.textContent||"").includes(${JSON.stringify(text)})))`
    : `document.querySelector(${JSON.stringify(selector || "")})`;
  const rect = await cmdEvaluate(`(() => {
    const el0 = ${picker};
    if (!el0) throw new Error("click_trusted: element not found");
    const el = el0.closest("button,a,[role=button],[tabindex],label") || el0;
    el.scrollIntoView({ block: "center", inline: "center" });
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) throw new Error("click_trusted: element has zero size");
    el.focus?.();
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
             tag: el.tagName, w: Math.round(r.width), h: Math.round(r.height),
             label: (el.innerText || "").trim().slice(0, 40) };
  })()`);
  const tab = await getCurrentTab();
  const target = { tabId: tab.id };
  await chrome.debugger.attach(target, "1.3").catch((e) => {
    if (!String(e).includes("Another debugger")) throw e;
  });
  try {
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      type: "mouseMoved", x: rect.x, y: rect.y, button: "none", clickCount: 0,
    });
    await sleep(80);
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      type: "mousePressed", x: rect.x, y: rect.y, button: "left", buttons: 1, clickCount: 1,
    });
    await sleep(80);
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      type: "mouseReleased", x: rect.x, y: rect.y, button: "left", buttons: 0, clickCount: 1,
    });
    return { clicked: true, isTrusted: true, ...rect };
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
}

async function cmdSetFileInput(selector, files) {
  const tab = await getCurrentTab();
  if (!files.length) throw new Error("files is empty");
  const target = { tabId: tab.id };
  await chrome.debugger.attach(target, "1.3").catch((e) => {
    if (!String(e).includes("Another debugger")) throw e;
  });
  try {
    await chrome.debugger.sendCommand(target, "DOM.enable");
    const doc = await chrome.debugger.sendCommand(target, "DOM.getDocument", { depth: -1, pierce: true });
    const found = await chrome.debugger.sendCommand(target, "DOM.querySelector", {
      nodeId: doc.root.nodeId,
      selector,
    });
    if (!found.nodeId) throw new Error("file input not found: " + selector);
    await chrome.debugger.sendCommand(target, "DOM.setFileInputFiles", {
      nodeId: found.nodeId,
      files,
    });
    return true;
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
}

async function cmdScreenshot() {
  const tab = await getCurrentTab();
  const target = { tabId: tab.id };
  await chrome.debugger.attach(target, "1.3").catch((e) => {
    if (!String(e).includes("Another debugger")) throw e;
  });
  try {
    const result = await chrome.debugger.sendCommand(target, "Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
    return `data:image/png;base64,${result.data}`;
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
}

async function cmdGetCookies(domain) {
  return await chrome.cookies.getAll({ domain });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

connect();
