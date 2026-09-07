const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const elements = {
  form: $("#promptForm"),
  input: $("#promptInput"),
  send: $("#sendButton"),
  welcome: $("#welcome"),
  messages: $("#messages"),
  conversation: $("#conversation"),
  history: $("#historyList"),
  settingsPanel: $("#settingsPanel"),
  settingsToggle: $("#settingsToggle"),
  aspect: $("#aspectRatio"),
  ratioShortcut: $("#ratioShortcut"),
  steps: $("#steps"),
  stepsValue: $("#stepsValue"),
  guidance: $("#guidance"),
  guidanceValue: $("#guidanceValue"),
  negative: $("#negativePrompt"),
  seed: $("#seed"),
  sidebar: $("#sidebar"),
  scrim: $("#sidebarScrim"),
  toast: $("#toast"),
};

const icon = `<svg viewBox="0 0 44 44"><path d="M22 3.5C24.9 12.9 31.1 19.1 40.5 22 31.1 24.9 24.9 31.1 22 40.5 19.1 31.1 12.9 24.9 3.5 22 12.9 19.1 19.1 12.9 22 3.5Z" fill="currentColor"/></svg>`;
const ideas = [
  "清晨薄雾中的江南水乡，青石板路，一位撑油纸伞的行人，柔和自然光，写实摄影，细腻质感",
  "未来主义电动跑车停在荒漠公路旁，黄金时刻，长焦压缩感，汽车广告摄影，8K 细节",
  "法式餐厅厨房里的年轻主厨，专注摆盘，暖色环境光，纪实摄影，真实肤质与蒸汽细节",
  "深海潜水员发现沉没的古代石像，幽蓝光束穿过海水，电影画面，超写实，宏大尺度",
];

let busy = false;
let conversations = JSON.parse(localStorage.getItem("lumen-history") || "[]");
let currentConversation = null;
let toastTimer;

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => elements.toast.classList.remove("show"), 2200);
}

function autoResize() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 150)}px`;
}

function getSettings() {
  const [width, height] = elements.aspect.value.split("x").map(Number);
  return {
    width,
    height,
    steps: Number(elements.steps.value),
    guidance: Number(elements.guidance.value),
    negativePrompt: elements.negative.value.trim(),
    seed: elements.seed.value === "" ? undefined : Number(elements.seed.value),
  };
}

function saveConversation(prompt) {
  const item = {
    id: crypto.randomUUID(),
    title: prompt.slice(0, 34),
    prompt,
    createdAt: Date.now(),
  };
  conversations.unshift(item);
  conversations = conversations.slice(0, 12);
  currentConversation = item.id;
  localStorage.setItem("lumen-history", JSON.stringify(conversations));
  renderHistory();
}

function renderHistory() {
  if (!conversations.length) {
    elements.history.innerHTML = `<div class="empty-history">你的提示词会保存在此设备上，方便再次创作。</div>`;
    return;
  }
  elements.history.innerHTML = conversations.map((item) => `
    <button class="history-item ${item.id === currentConversation ? "active" : ""}" data-id="${item.id}">
      <svg viewBox="0 0 24 24"><path d="M4 5h16v12H8l-4 4V5Z"/></svg>
      <span>${escapeHtml(item.title)}</span>
    </button>
  `).join("");
}

function beginConversation() {
  elements.welcome.hidden = true;
  elements.messages.style.display = "block";
}

function appendUserMessage(prompt) {
  const article = document.createElement("article");
  article.className = "message user-message";
  article.innerHTML = `<div class="user-bubble">${escapeHtml(prompt)}</div>`;
  elements.messages.append(article);
}

function appendLoader() {
  const article = document.createElement("article");
  article.className = "message assistant-message";
  article.innerHTML = `
    <div class="assistant-mark">${icon}</div>
    <div class="assistant-content">
      <p class="assistant-title">正在构筑画面</p>
      <div class="generation-loader">
        <div class="loader-inner"><span class="pulse-mark">${icon}</span><span>FLUX 正在处理光影与细节…</span></div>
      </div>
    </div>`;
  elements.messages.append(article);
  return article;
}

function replaceWithImage(article, blob, prompt, settings) {
  const imageUrl = URL.createObjectURL(blob);
  article.querySelector(".assistant-title").textContent = "图像已生成";
  const content = article.querySelector(".assistant-content");
  content.querySelector(".generation-loader").outerHTML = `
    <div class="image-card">
      <img src="${imageUrl}" alt="${escapeHtml(prompt)}" />
      <div class="image-actions">
        <button class="image-action download-action" type="button">
          <svg viewBox="0 0 24 24"><path d="M12 3v13M7 11l5 5 5-5M5 21h14"/></svg>下载
        </button>
        <button class="image-action reuse-action" type="button">
          <svg viewBox="0 0 24 24"><path d="M4 4v6h6M20 20v-6h-6M5.1 15a8 8 0 0 0 13.2 2M18.9 9A8 8 0 0 0 5.7 7"/></svg>再创作
        </button>
      </div>
    </div>
    <div class="meta-row">
      <span class="meta-chip">${settings.width} × ${settings.height}</span>
      <span class="meta-chip">${settings.steps} STEPS</span>
      <span class="meta-chip">CFG ${settings.guidance}</span>
      <span class="meta-chip">REALISM LORA</span>
    </div>`;

  content.querySelector(".download-action").addEventListener("click", () => {
    const link = document.createElement("a");
    link.href = imageUrl;
    link.download = `lumen-${Date.now()}.${blob.type.includes("png") ? "png" : "jpg"}`;
    link.click();
  });
  content.querySelector(".reuse-action").addEventListener("click", () => {
    elements.input.value = prompt;
    autoResize();
    elements.input.focus();
  });
}

function replaceWithError(article, message) {
  article.querySelector(".assistant-title").textContent = "生成未完成";
  article.querySelector(".generation-loader").outerHTML = `<div class="error-card">${escapeHtml(message)}</div>`;
}

async function generate(prompt) {
  if (busy || !prompt.trim()) return;
  busy = true;
  elements.send.disabled = true;
  beginConversation();
  appendUserMessage(prompt);
  const loader = appendLoader();
  const settings = getSettings();
  elements.input.value = "";
  autoResize();
  saveConversation(prompt);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, ...settings }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `请求失败（${response.status}）`);
    }

    replaceWithImage(loader, await response.blob(), prompt, settings);
  } catch (error) {
    replaceWithError(loader, error.message || "网络连接异常，请稍后再试。");
  } finally {
    busy = false;
    elements.send.disabled = false;
    elements.conversation.scrollTop = elements.conversation.scrollHeight;
  }
}

function resetConversation() {
  currentConversation = null;
  elements.messages.innerHTML = "";
  elements.messages.style.display = "none";
  elements.welcome.hidden = false;
  elements.input.value = "";
  autoResize();
  renderHistory();
  elements.input.focus();
}

function toggleSettings(force) {
  const open = force ?? !elements.settingsPanel.classList.contains("open");
  elements.settingsPanel.classList.toggle("open", open);
  elements.settingsPanel.setAttribute("aria-hidden", String(!open));
  elements.settingsToggle.setAttribute("aria-expanded", String(open));
}

function closeSidebar() {
  elements.sidebar.classList.remove("open");
  elements.scrim.classList.remove("open");
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  generate(elements.input.value.trim());
});

elements.input.addEventListener("input", autoResize);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});

elements.settingsToggle.addEventListener("click", () => toggleSettings());
elements.steps.addEventListener("input", () => { elements.stepsValue.value = elements.steps.value; });
elements.guidance.addEventListener("input", () => { elements.guidanceValue.value = elements.guidance.value; });
elements.aspect.addEventListener("change", () => {
  const ratios = {
    "1024x1024": "1:1",
    "1152x896": "4:3",
    "896x1152": "3:4",
    "1344x768": "16:9",
    "768x1344": "9:16",
  };
  elements.ratioShortcut.textContent = ratios[elements.aspect.value] || "自定义";
});
elements.ratioShortcut.addEventListener("click", () => toggleSettings(true));

$$('.suggestion').forEach((button) => button.addEventListener("click", () => generate(button.dataset.prompt)));
$("#randomPrompt").addEventListener("click", () => {
  elements.input.value = ideas[Math.floor(Math.random() * ideas.length)];
  autoResize();
  elements.input.focus();
});
$("#newChat").addEventListener("click", () => { resetConversation(); closeSidebar(); });

elements.history.addEventListener("click", (event) => {
  const button = event.target.closest(".history-item");
  if (!button) return;
  const item = conversations.find((entry) => entry.id === button.dataset.id);
  if (!item) return;
  currentConversation = item.id;
  renderHistory();
  elements.input.value = item.prompt;
  autoResize();
  elements.input.focus();
  closeSidebar();
  showToast("提示词已填入，可以再次生成");
});

$("#openSidebar").addEventListener("click", () => {
  elements.sidebar.classList.add("open");
  elements.scrim.classList.add("open");
});
$("#closeSidebar").addEventListener("click", closeSidebar);
elements.scrim.addEventListener("click", closeSidebar);

$("#themeToggle").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  localStorage.setItem("lumen-theme", dark ? "dark" : "light");
});

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    resetConversation();
  }
  if (event.key === "Escape") { toggleSettings(false); closeSidebar(); }
});

document.documentElement.dataset.theme = localStorage.getItem("lumen-theme") || "light";
renderHistory();
autoResize();
