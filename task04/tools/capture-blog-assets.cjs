// Run: node task04/tools/capture-blog-assets.cjs D:/mayoimono
const { createRequire } = require("node:module");
const { spawn } = require("node:child_process");
const {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  copyFileSync,
  rmSync,
} = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const root = path.resolve(process.argv[2] || "D:/mayoimono");
const requireProject = createRequire(path.join(root, "package.json"));
const { chromium } = requireProject("@playwright/test");
const output = path.resolve(__dirname, "../images");
mkdirSync(output, { recursive: true });
const dataDir = mkdtempSync(path.join(tmpdir(), "task04-blog-preview-"));
const baseURL = "http://127.0.0.1:3002";
const service = spawn(
  process.execPath,
  [path.join(root, "apps/web/dist-server/server.js")],
  {
    cwd: path.join(root, "apps/web"),
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      HOST: "127.0.0.1",
      PORT: "3002",
      DATA_DIR: dataDir,
      FRONTEND_ORIGIN: baseURL,
      COOKIE_SECURE: "false",
      LOG_LEVEL: "warn",
    },
  },
);
let logs = "";
service.stdout.on("data", (d) => {
  logs = (logs + d).slice(-3000);
});
service.stderr.on("data", (d) => {
  logs = (logs + d).slice(-3000);
});
const stopped = new Promise((resolve) => service.once("exit", resolve));
const esc = (s) =>
  s.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
function diagram(title, subtitle, width, height, nodes, edges) {
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10" fill="#64748b"/></marker></defs><rect width="100%" height="100%" fill="#f8fafc"/><g font-family="Microsoft YaHei, sans-serif"><text x="35" y="47" fill="#0f172a" font-size="27" font-weight="700">${title}</text><text x="35" y="79" fill="#64748b" font-size="15">${subtitle}</text>`;
  for (const [points, label, lx, ly] of edges) {
    svg += `<polyline points="${points}" fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#a)"/>`;
    if (label)
      svg += `<text x="${lx}" y="${ly}" text-anchor="middle" font-size="14" fill="#475569">${esc(label)}</text>`;
  }
  for (const [x, y, w, h, lines, color = "#ffffff"] of nodes) {
    svg += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="${color}" stroke="#cbd5e1" stroke-width="1.5"/>`;
    lines.forEach((line, i) => {
      svg += `<text x="${x + w / 2}" y="${y + h / 2 + (i - (lines.length - 1) / 2) * 25 + 6}" text-anchor="middle" fill="#0f172a" font-size="${i === 0 ? 18 : 15}" font-weight="${i === 0 ? 600 : 400}">${esc(line)}</text>`;
    });
  }
  return svg + "</g></svg>";
}
async function main() {
  let browser;
  try {
    const deadline = Date.now() + 30000;
    while (true) {
      try {
        if ((await fetch(baseURL + "/api/health")).ok) break;
      } catch {}
      if (Date.now() > deadline || service.exitCode !== null)
        throw Error("Preview startup failed: " + logs);
      await new Promise((r) => setTimeout(r, 200));
    }
    browser = await chromium.launch();
    const owner = await browser.newContext({
      baseURL,
      viewport: { width: 390, height: 844 },
    });
    const peer = await browser.newContext({
      baseURL,
      viewport: { width: 390, height: 844 },
    });
    for (const [context, name] of [
      [owner, "林同学"],
      [peer, "陈同学"],
    ]) {
      const res = await context.request.post("/api/users/register", {
        data: {
          email: `blog-${randomUUID()}@example.com`,
          password: "blogpreview123",
          name,
        },
      });
      if (res.status() !== 201) throw Error("Registration failed");
    }
    const base = {
      category: "keys",
      location: "图书馆二楼",
      occurredAt: new Date(Date.now() - 3600000).toISOString(),
      description:
        "银色钥匙串，带一个蓝色挂件，约三把钥匙。请通过站内消息核对细节。",
      contact: "站内联系",
      status: "active",
      lat: 26.0588,
      lng: 119.1968,
    };
    const res = await owner.request.post("/api/posts", {
      data: { ...base, type: "lost", title: "银色钥匙串" },
    });
    if (res.status() !== 201) throw Error("Post creation failed");
    const post = (await res.json()).post;
    await peer.request.post("/api/posts", {
      data: {
        ...base,
        type: "found",
        category: "umbrella",
        title: "蓝色折叠雨伞",
        location: "教学楼一层",
        description: "拾到一把蓝色折叠伞，请核对伞柄特征。",
      },
    });
    const page = await owner.newPage(),
      finder = await peer.newPage();
    async function capture(target, url, name, ready) {
      await target.goto(url);
      if (ready)
        await target.getByText(ready, { exact: false }).first().waitFor();
      await target
        .locator(".empty")
        .filter({ hasText: "正在加载" })
        .waitFor({ state: "hidden" });
      await target.evaluate(() => document.fonts.ready);
      await target.screenshot({
        path: path.join(output, name + ".png"),
        fullPage: true,
      });
    }
    await capture(page, "/", "home", "银色钥匙串");
    await capture(page, "/publish", "publish", "物品名称");
    await page.goto("/search");
    await page.getByRole("textbox", { name: "搜索关键词" }).fill("钥匙");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByText("找到 1 条相关信息").waitFor();
    await page.screenshot({
      path: path.join(output, "search.png"),
      fullPage: true,
    });
    await capture(finder, `/posts/${post.id}`, "detail", "物品信息");
    await finder.getByRole("button", { name: "联系发布者" }).click();
    await finder
      .getByRole("textbox", { name: "联系内容" })
      .fill("你好，我捡到了带蓝色挂件的钥匙，可以到服务台核对吗？");
    await finder.getByRole("button", { name: "发送消息", exact: true }).click();
    await finder.waitForURL("**/messages/*");
    await finder
      .getByText("你好，我捡到了带蓝色挂件的钥匙，可以到服务台核对吗？", {
        exact: true,
      })
      .waitFor();
    const conversationId = new URL(finder.url()).pathname.split("/").pop();
    await page.goto("/messages/" + conversationId);
    await page
      .getByText("你好，我捡到了带蓝色挂件的钥匙，可以到服务台核对吗？", {
        exact: true,
      })
      .waitFor();
    await page
      .getByRole("textbox", { name: "发送消息", exact: true })
      .fill("谢谢！我会带上钥匙对应物品，到图书馆服务台核对。");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await finder
      .getByText("谢谢！我会带上钥匙对应物品，到图书馆服务台核对。", {
        exact: true,
      })
      .waitFor();
    await finder.reload();
    await finder
      .getByText("谢谢！我会带上钥匙对应物品，到图书馆服务台核对。", {
        exact: true,
      })
      .waitFor();
    await finder.screenshot({
      path: path.join(output, "chat.png"),
      fullPage: true,
    });
    await capture(page, "/my-posts", "my-posts", "银色钥匙串");
    await owner.request.post(`/api/posts/${post.id}/complete`);
    await page.reload();
    await page.getByRole("button", { name: /已完成/ }).click();
    await page.getByRole("heading", { name: "银色钥匙串" }).waitFor();
    await page.screenshot({
      path: path.join(output, "completed.png"),
      fullPage: true,
    });
    // Existing captures use the real Baidu SDK; they intentionally have no demonstration posts.
    for (const name of ["nearby", "publish-location-panel"])
      copyFileSync(
        path.join(root, "docs/screenshots", name + ".png"),
        path.join(output, name + ".png"),
      );
    const diagrams = [
      [
        "architecture",
        diagram(
          "从页面操作到数据保存",
          "普通请求与实时推送共用一个 Node 服务；数据库只由服务端访问",
          1080,
          680,
          [
            [
              280,
              115,
              520,
              85,
              [
                "浏览器：页面、表单、聊天界面",
                "HTTP 客户端 / IndexedDB 本地记录",
              ],
              "#fef3c7",
            ],
            [
              50,
              270,
              450,
              80,
              ["Next.js Route Handlers", "解析请求 / 认证 / 校验 / 统一错误"],
            ],
            [650, 270, 350, 80, ["WebSocket /ws", "连接管理 / 消息推送 / ACK"]],
            [
              50,
              410,
              450,
              100,
              [
                "业务模块",
                "user · message · interaction",
                "private-chat · infrastructure",
              ],
              "#dbeafe",
            ],
            [
              650,
              410,
              350,
              100,
              ["进程共享 runtime", "数据库连接 + 实时推送函数"],
              "#dbeafe",
            ],
            [
              200,
              570,
              680,
              70,
              ["Drizzle 仓储 → SQLite / 上传文件"],
              "#dcfce7",
            ],
          ],
          [
            ["410,200 275,270", "HTTP", 290, 230],
            ["720,200 825,270", "WebSocket", 810, 230],
            ["275,350 275,410", "", 0, 0],
            ["825,350 825,410", "", 0, 0],
            ["500,460 650,460", "共享上下文", 574, 444],
            ["275,510 400,570", "", 0, 0],
            ["825,510 680,570", "", 0, 0],
          ],
        ),
      ],
      [
        "publish-flow",
        diagram(
          "发布、校验与交接完成",
          "草稿只对作者可见；完成状态需要发布者主动确认",
          1080,
          890,
          [
            [320, 110, 440, 65, ["用户填写信息：寻物 / 招领"], "#fef3c7"],
            [320, 225, 440, 65, ["提交草稿或正式发布"]],
            [
              320,
              345,
              440,
              75,
              ["登录认证与输入校验", "正式发布检查必填项、时间及照片归属"],
            ],
            [
              30,
              345,
              230,
              75,
              ["返回错误提示", "补全资料或重新登录"],
              "#fee2e2",
            ],
            [320, 480, 440, 65, ["服务层检查作者权限和既有状态"]],
            [
              320,
              605,
              440,
              65,
              ["仓储写入 SQLite", "草稿 draft / 公开 active"],
              "#dbeafe",
            ],
            [800, 605, 240, 65, ["草稿：我的发布", "补全后重新提交"]],
            [
              320,
              755,
              440,
              75,
              ["查找 → 联系核对 → 实际交接", "发布者标记 completed"],
              "#dcfce7",
            ],
          ],
          [
            ["540,175 540,225", "", 0, 0],
            ["540,290 540,345", "", 0, 0],
            ["320,385 260,385", "失败", 290, 369],
            ["145,345 145,140 320,140", "返回修改", 215, 125],
            ["540,420 540,480", "通过", 570, 452],
            ["540,545 540,605", "", 0, 0],
            ["760,637 800,637", "草稿", 780, 622],
            ["920,605 920,258 760,258", "编辑", 955, 410],
            ["540,670 540,755", "公开发布", 590, 715],
          ],
        ),
      ],
      [
        "chat-flow",
        diagram(
          "聊天：先保存，再确认",
          "ACK 表示本地已持久化；已读仅表示聊天页实际展示的消息",
          1080,
          900,
          [
            [
              40,
              115,
              440,
              80,
              ["发送端：IndexedDB", "分配 deviceId / seqId，保存发送队列"],
              "#fef3c7",
            ],
            [
              600,
              115,
              430,
              80,
              ["发送端 HTTP 提交", "响应丢失时沿用原标识重试"],
            ],
            [
              600,
              280,
              430,
              85,
              ["服务端事务", "四元组去重 → 保存消息 → 更新会话"],
              "#dbeafe",
            ],
            [
              600,
              460,
              430,
              85,
              ["WebSocket 推送 / HTTP 补拉", "设备未确认时继续重投"],
            ],
            [
              40,
              460,
              440,
              85,
              ["接收端：写入 IndexedDB", "本地事务提交成功后发送 ACK"],
              "#dcfce7",
            ],
            [40, 650, 440, 85, ["聊天页可见且实际展示", "按消息 ID 标记已读"]],
            [
              600,
              650,
              430,
              85,
              ["服务端保存设备 ACK", "停止向该设备重投这条消息"],
            ],
            [
              230,
              800,
              620,
              60,
              ["默认 7 天后清理服务端正文；本地记录继续保留"],
            ],
          ],
          [
            ["480,155 600,155", "提交", 540, 137],
            ["815,195 815,280", "", 0, 0],
            ["815,365 815,460", "", 0, 0],
            ["600,500 480,500", "交付", 540, 482],
            ["260,545 260,650", "", 0, 0],
            ["480,530 540,530 540,690 600,690", "ACK", 566, 601],
            [
              "40,500 15,500 15,405 815,405 815,460",
              "本地失败：不 ACK，等待重投",
              350,
              394,
            ],
            ["815,735 700,800", "", 0, 0],
            ["260,735 380,800", "", 0, 0],
          ],
        ),
      ],
    ];
    const canvas = await browser.newPage();
    for (const [name, svg] of diagrams) {
      await canvas.setContent(
        '<html><body style="margin:0">' + svg + "</body></html>",
      );
      await canvas
        .locator("svg")
        .screenshot({ path: path.join(output, name + ".png") });
    }
    const testLines = readFileSync(
      path.resolve(__dirname, "../evidence/npm-test.txt"),
      "utf8",
    )
      .split(/\r?\n/)
      .filter((l) => /^ℹ /.test(l));
    const partnerLines = readFileSync(
      path.resolve(__dirname, "../evidence/partner-tests.txt"),
      "utf8",
    )
      .split(/\r?\n/)
      .filter((l) =>
        /^# (tests|pass|fail|cancelled|skipped|todo|duration_ms)/.test(l),
      );
    const e2e = readFileSync(
      path.resolve(__dirname, "../evidence/e2e.txt"),
      "utf8",
    )
      .split(/\r?\n/)
      .find((l) => /10 passed/.test(l));
    await canvas.setViewportSize({ width: 1080, height: 740 });
    await canvas.setContent(
      `<html><body style="margin:0;padding:44px;background:#0f172a;color:#e2e8f0;font:18px Consolas,Microsoft YaHei,monospace"><h2>2026-10-09 · task04 验证结果</h2><p>本地快照 de86be3：npm test</p><pre>${esc(testLines.join("\n"))}</pre><p>同一快照：生产构建浏览器测试</p><pre>${esc(e2e || "See evidence/e2e.txt")}</pre><p>PR #1 新增纯函数测试（独立快照）</p><pre>${esc(partnerLines.join("\n"))}</pre><p style="font-size:14px;color:#94a3b8">摘录自实际运行日志；两个快照分别验证，未宣称合并后整套回归通过。</p></body></html>`,
    );
    await canvas.screenshot({
      path: path.join(output, "test-results.png"),
      fullPage: true,
    });
    console.log(
      JSON.stringify({
        output,
        temporaryDatabase: dataDir,
        applicationSnapshot: "de86be3",
        screenshotsCreated: true,
      }),
    );
  } finally {
    await browser?.close();
    service.kill("SIGTERM");
    await stopped;
    const temporaryRoot = path.resolve(tmpdir());
    const cleanupTarget = path.resolve(dataDir);
    const child = path.relative(temporaryRoot, cleanupTarget);
    if (
      !child ||
      child.startsWith("..") ||
      path.isAbsolute(child) ||
      !path.basename(cleanupTarget).startsWith("task04-blog-preview-")
    )
      throw Error(
        "Refusing to clean a directory outside the temporary preview area",
      );
    rmSync(cleanupTarget, {
      recursive: true,
      force: true,
      maxRetries: 5,
      retryDelay: 200,
    });
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
