async function refresh() {
  const el = document.getElementById("status");
  chrome.runtime.sendMessage({ type: "GET_STATUS" }, (resp) => {
    const ok = resp && resp.status && resp.status.wsConnected;
    el.textContent = ok ? "已连接" : "未连接";
    el.className = ok ? "ok" : "bad";
  });
}

document.getElementById("refresh").addEventListener("click", refresh);
refresh();
