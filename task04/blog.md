| 项目 | 内容 |
| --- | --- |
| 这个作业属于哪个课程 | [202601 软件工程](https://edu.cnblogs.com/campus/fzu/202601SofwareEngineering) |
| 这个作业要求在哪里 | [作业要求](https://edu.cnblogs.com/campus/fzu/202601SofwareEngineering/homework/16744) |
| 这个作业的目标 | 将第一次结对作业的校园失物招领原型实现为网页，完成“发布信息—浏览或搜索—查看详情—联系发布者—更新状态”的流程，并进行测试与复盘。 |
| 本人 | [052402132 郑嘉文](https://www.cnblogs.com/LYanl7) |
| 结对同学的博客 | [102401507 李宗欣](https://www.cnblogs.com/asdllx) |
| GitHub 项目地址 | [LYanl7/052402132-102401507](https://github.com/LYanl7/052402132-102401507) |



## 目录

- [一、具体分工](#division)
- [二、PSP 表格](#psp)
- [三、解题思路与设计实现](#implementation)
- [四、附加特点：地图找线索与可靠私聊](#features)
- [五、目录组织与使用说明](#usage)
- [六、单元测试与简易教程](#tests)
- [七、GitHub 代码签入记录](#commits)
- [八、遇到的问题、尝试与收获](#problems)
- [九、评价队友](#partner-review)

<a id="division" name="division"></a>

## 一、具体分工

| 成员 | 主要负责内容 |
| --- | --- |
| 郑嘉文 | 负责项目整体搭建和主要功能开发，处理数据存储、实时通信等技术问题，并整理相关文档。 |
| 李宗欣 | 参与页面交互与功能完善，协助测试和问题修复，并补充相关说明。 |

<a id="psp" name="psp"></a>

## 二、PSP 表格


| PSP | Personal Software Process Stages | 预估耗时（分钟） | 实际耗时（分钟） |
| --- | --- | ---: | ---: |
| Planning | 计划 | 30 | 40 |
| Estimate | 估计这个任务需要多少时间 | 30 | 40 |
| Development | 开发 | 1560 | 1970 |
| Analysis | 需求分析（包括学习新技术） | 120 | 180 |
| Design Spec | 生成设计文档 | 90 | 100 |
| Design Review | 设计复审 | 60 | 80 |
| Coding Standard | 代码规范（为目前的开发制定合适的规范） | 30 | 40 |
| Design | 具体设计 | 180 | 220 |
| Coding | 具体编码 | 720 | 840 |
| Code Review | 代码复审 | 120 | 150 |
| Test | 测试（自我测试，修改代码，提交修改） | 240 | 360 |
| Reporting | 报告 | 180 | 210 |
| Test Report | 测试报告 | 60 | 80 |
| Size Measurement | 计算工作量 | 30 | 30 |
| Postmortem & Process Improvement Plan | 事后总结，并提出过程改进计划 | 90 | 100 |
| 合计 |  | **1770** | **2220** |


<a id="implementation" name="implementation"></a>

## 三、解题思路与设计实现

### 1. 代码实现思路

**前后端分离。** 前端负责页面展示、表单输入和交互反馈，后端负责身份验证、业务规则和数据存储，两者通过 HTTP 接口交换数据，聊天消息通过 WebSocket 实时推送。这样划分可以让界面调整与业务逻辑修改各有明确的位置，也方便单独测试接口。权限和数据校验统一在服务端执行，用户即使绕过页面调用接口，也受到相同规则的约束。

项目使用 Next.js 同时提供页面和后端接口，前后端按职责分离。结合单机部署的要求，页面、API 和 WebSocket 运行在同一个 Node 服务中，SQLite 保存业务数据。

**按业务划分模块。** 我们按照功能处理的数据和业务职责，将后端分为五个模块：

| 模块 | 主要职责 |
| --- | --- |
| 用户模块 `user` | 注册登录、用户资料与会话管理 |
| 互动模块 `interaction` | 收藏、浏览历史与个人统计 |
| 私聊模块 `private-chat` | 双人会话、消息保存与实时投递 |
| 消息模块 `message` | 寻物和招领信息的发布、查询与状态管理 |
| 基础设施模块 `infrastructure` | 数据库连接、上传、日志与通用请求处理 |

同一模块内再按文件职责拆分：模型描述数据结构，校验文件检查输入，仓储封装数据库操作，服务层处理业务规则，请求处理函数连接接口与业务。这样可以把一个功能的相关代码放在一起，同时分清数据定义和执行逻辑。

**抽象可复用的公共逻辑。** 多个接口都会用到登录检查、参数处理和错误响应，因此将这些共同步骤封装到统一的 `endpoint()` 中；数据库读写通过 Drizzle 仓储封装；日志和上传等能力放入基础设施模块。发布者权限、草稿可见性、会话成员判断等规则则保留在各自业务模块中。抽象的依据是实际复用需求，让接口行为一致，也方便集中修改和测试。

### 2. 关键实现的数据流图与流程图

下面的数据流图展示一次页面操作如何进入接口、调用业务模块并保存数据。浏览器通过接口访问服务端，HTTP 接口与 WebSocket 通过共享运行时连接数据库和实时推送能力。

![页面、HTTP 接口、业务模块、共享运行时和数据库的数据流图](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task04/images/architecture.png)

发布信息的流程如下。服务端先进行登录认证和输入校验，再检查图片归属；修改已有信息时还需要检查作者身份和当前状态。校验通过后写入数据库，失败则返回错误提示。

![发布、输入校验、草稿保存、正式发布及交接完成流程图](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task04/images/publish-flow.png)

草稿 `draft` 允许资料不完整，只对作者可见；正式发布 `active` 需要填写名称、地点、时间和描述；完成交接后由发布者标记为 `completed`，保留详情和已有会话，关闭编辑及新建联系入口。

### 3. 关键代码及说明

**统一请求入口与业务调用。** 以下代码来自 [`message/handlers.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/src/modules/message/handlers.ts)：

```ts
export const createPost = endpoint(
  async (req, ctx) => {
    return { post: savePost(ctx.db, postInputSchema.parse(req.body), userId(req)) };
  },
  { auth: true, status: 201 },
);
```

`endpoint()` 根据配置执行登录检查并统一处理响应和异常；`postInputSchema.parse()` 校验发布内容；`userId(req)` 取得已认证的用户身份；`savePost()` 执行保存业务。请求入口只负责连接这些步骤，通用处理和具体业务各有归属，其他接口也可以复用相同的封装。

**在服务层执行作者权限和状态检查。** 以下节选自 [`message/service.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/src/modules/message/service.ts)：

```ts
export function ownedPost(db: Database, id: string, owner: string) {
  const post = getPost(db, id, owner);
  if (post.userId !== owner) throw new AppError(403, '只有发布者可以修改信息');
  return post;
}

// savePost() 中修改已有信息的分支
if (id) {
  const existing = ownedPost(db, id, owner);
  if (existing.status === 'completed') throw new AppError(409, '已完成的信息不能编辑');
  updatePostData(db, id, input, now);
}
```

`ownedPost()` 集中检查作者身份，可供修改、完成和删除等操作复用。保存修改前还要检查信息是否已经完成，最后才调用仓储更新数据。`403` 表示当前用户没有修改权限，`409` 表示当前状态不允许编辑。这体现了业务规则放在服务层、数据库操作交给仓储的划分。

<a id="features" name="features"></a>

## 四、附加特点：地图找线索与可靠私聊

### 1. 地图找线索：把“附近”变成可筛选的信息范围

物品遗失通常与地点相关。如果只按发布时间排列，用户可能先看到很多与自己活动范围无关的记录。因此，我们把原型中的附近页实现为百度地图，让用户围绕当前位置或手动浏览的位置查找，还可以切换寻物、招领和查询范围。

实现分为三步：发布时选点并保存坐标；附近页确定查询中心；服务端计算距离并返回范围内的进行中信息。地图标记和下方列表使用同一批结果，点击标记进入对应详情。

这里需要统一坐标系。浏览器 GPS 坐标先通过百度转换接口转为 BD-09，再用于附近查询或保存。旧示意坐标被标记为 `legacy`，保留原信息，重新选点前不参与附近查询。初始地图中心只是浏览位置，页面不会将它当成用户真实定位。

关键代码节选自 [`message/handlers.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/src/modules/message/handlers.ts)：

```ts
export const nearbyPosts = endpoint(async (req, ctx) => {
  const p = nearbyQuerySchema.parse(req.query);
  const items = findNearbyPosts(ctx.db, p.type, req.user?.id)
    .map((post) => ({
      ...post,
      distance: distanceMeters(p.lat, p.lng, post.lat!, post.lng!),
    }))
    .filter((pst) => pst.distance <= p.radius)
    .sort((a, b) => a.distance - b.distance);
  return { items, total: items.length };
});
```

仓储先筛选未删除、进行中、经纬度完整且坐标系为 BD-09 的记录。`distanceMeters()` 使用 Haversine 公式估算两点距离，接口再按半径过滤并由近到远排序。这里返回的是地理距离估算，不能当成步行路线距离。当前查询会在内存中计算候选信息的距离，适合课程项目规模；数据量扩大后需要增加空间预筛选或索引。

| 附近：真实地图与空结果提示 | 发布：地址搜索与地图选点 |
| --- | --- |
| ![真实百度地图，空数据库没有物品标记](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task04/images/nearby.png) | ![发布表单的地图选点面板](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task04/images/publish-location-panel.png) |

这两张图沿用项目 10 月 3 日真实百度 SDK 的验证截图，展示的是空数据库状态。地图标记、选点保存、类型筛选和移动地图查询由浏览器测试验证；自动化测试替换外部地图 SDK，以避免网络和配额影响应用流程测试。真实 SDK 的选点与坐标转换另有 [预览验证记录](https://github.com/LYanl7/052402132-102401507/blob/de86be3/docs/screenshots/map-preview-report.json)，其中 GPS 输入是浏览器模拟值。

### 2. 可靠私聊：网络异常后仍能继续核对线索

联系发布者是失物招领流程中的关键环节。设计时，我们进一步考虑了“服务器已经收到，但响应丢失”“收到消息后本地保存失败”“刷新时还有消息没发送完”等情况，采用本地发送队列、服务端去重和接收确认来处理。

![消息从本地发送队列、服务端去重到本地持久化与接收确认的流程图](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task04/images/chat-flow.png)

发送端先把消息写入 IndexedDB，并在事务中分配设备标识 `deviceId` 和会话内序号 `seqId`。重试沿用原标识，服务端以 `(conversationId, senderId, deviceId, seqId)` 识别同一条消息，重复请求返回原记录，避免出现多条相同消息。

接收端先保存，再发 ACK。以下节选自 [`private-chat/sync.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/src/modules/private-chat/sync.ts)：

```ts
while (received.length && !disposed) {
  const batch = received.splice(0, 50);
  await saveMessages(user, batch); // Commit locally before acknowledging delivery.
  if (!disposed && socket?.readyState === WebSocket.OPEN)
    socket.send(JSON.stringify({ type: "ack", ids: batch.map((m) => m.id) }));
  if (!disposed) events.message(batch.at(-1)!);
}
```

如果本地事务失败，代码不会走到 ACK，服务端可以继续重投。ACK 只表示当前设备已保存消息；已读则由聊天页针对实际展示的消息单独上报。每批 50 条是传输批次，离线积压可以分批继续接收。

![两个账号实时对话，刷新后仍显示本地聊天记录](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task04/images/chat.png)

截图展示两个账号通过真实网页完成对话，并在接收端刷新后保留记录。断线重试、本地写入失败、超过 50 条积压以及多标签页序号分配另由自动化测试检查。

服务器默认保留消息正文 7 天，用于短期交付；浏览器已保存的历史不会随服务端清理而删除。这个方案的限制也很明确：清除浏览器站点数据或更换设备后，已经超过服务端保留期的记录无法恢复。

<a id="usage" name="usage"></a>

## 五、目录组织与使用说明

### 1. 目录如何组织

```text
mayoimono/
├── apps/web/
│   ├── server.ts                  # 启动 Next.js，并挂载 WebSocket
│   ├── .env.example               # 环境配置示例
│   ├── src/
│   │   ├── app/                   # 页面、布局与样式
│   │   │   ├── api/               # HTTP 接口路由
│   │   │   └── uploads/[filename]/ # 图片读取入口
│   │   ├── components/            # 表单、导航、地图与聊天组件
│   │   ├── lib/                   # 浏览器 HTTP 客户端、地图 SDK 辅助
│   │   ├── server/runtime.ts      # 共享数据库与实时推送上下文
│   │   └── modules/
│   │       ├── user/              # 用户、会话与身份验证
│   │       ├── message/           # 发布、搜索、附近查询及状态
│   │       ├── interaction/       # 收藏、浏览记录与统计
│   │       ├── private-chat/      # 私聊、投递与本地同步
│   │       └── infrastructure/    # 数据库、迁移、上传、日志和请求处理
│   └── test/                      # 纯函数、业务及接口测试
├── tests/                         # Playwright 浏览器流程测试
├── scripts/                       # 截图及测试报告辅助脚本
├── docs/                          # 架构、API、部署、验证记录及截图
├── data/                          # 本地 SQLite 与上传文件，不入 Git
├── package.json                   # 根目录统一启动、构建和测试命令
├── package-lock.json              # 锁定依赖版本
└── README.md                      # 项目概览与快速启动
```

这样组织后，页面负责交互，业务模块负责规则，仓储负责数据库访问。修改一条发布规则时，可以沿着 `route → handler → service → repository` 找到对应位置。博客与配图另存放在课程仓库的 `task04/`，与应用代码仓库分开。

### 2. 测试人员如何运行网页

准备 Node.js **22.16 或更高版本**和 npm 11，在 PowerShell 中运行：

```powershell
git clone https://github.com/LYanl7/052402132-102401507.git
cd 052402132-102401507
npm ci
npm run dev
```

浏览器打开 [http://localhost:3000](http://localhost:3000)。已有本地代码时，可直接进入 `D:\mayoimono` 安装依赖并启动。第一次启动会自动创建空数据库，需要自己注册账号和发布信息。

若要体验真实地图，在启动前复制配置文件：

```powershell
Copy-Item apps/web/.env.example apps/web/.env.local
```

在 `.env.local` 中填写 `NEXT_PUBLIC_BAIDU_MAP_AK`，使用已开通 JavaScript API、且访问域名在 Referer 白名单中的百度地图浏览器 AK。修改后重启开发服务；生产环境需要重新构建。没有有效 AK 时，地图会提示配置或加载问题，普通发布、搜索和聊天仍可验证。

建议按下面的顺序进行人工验收：

1. 在浏览器 A 注册账号，发布一条寻物信息，填写过去的发生时间；需要附近展示时通过地图选点。
2. 在首页和搜索页找到该信息，打开详情，检查名称、地点、时间和描述。
3. 在浏览器 B 或无痕窗口注册另一个账号，收藏该信息并联系发布者。
4. 两个窗口互发消息，刷新后检查聊天记录是否仍存在。
5. 回到发布账号的“我的发布”，编辑信息，再标记找回，检查已完成记录与联系入口。
6. 另建一条资料不完整的草稿，刷新后进入编辑，检查草稿与照片是否保留。

两个账号应使用独立浏览器会话，同一浏览器普通标签页通常共享登录 Cookie。

生产运行方式：

```powershell
npm run build
npm start
```

请使用项目脚本启动，以同时挂载实时聊天服务。完整环境配置、局域网访问和持久化说明见 [部署文档](https://github.com/LYanl7/052402132-102401507/blob/master/docs/deployment.md)。

<a id="tests" name="tests"></a>

## 六、单元测试与简易教程

### 1. 选择了什么工具

我们使用 Node.js 自带的 **`node:test`** 组织测试，使用 **`node:assert/strict`** 编写断言，通过 **tsx** 运行 TypeScript 测试文件。浏览器操作使用 **Playwright Test**，验证真实页面、HTTP 请求和双账号聊天流程。

不同层次的测试各有职责：`isActiveTab()`、`buildSearchQuery()` 和 HTTP 客户端等可以独立验证，属于单元测试；调用 Route Handler、操作临时 SQLite 或建立 WebSocket 的测试属于集成测试；打开网页并点击表单的测试属于端到端测试。`npm test` 包含前两类，不能将它输出的总数全部称为纯单元测试。

测试方法按“阅读工具的最小示例—找出函数的输入和预期结果—构造正常与异常数据—执行断言—将修复补成回归测试”的顺序整理。相关工具用法参考 [Node.js 测试文档](https://nodejs.org/docs/latest-v22.x/api/test.html) 和 [Playwright 编写测试文档](https://playwright.dev/docs/writing-tests)。

### 2. 单元测试简易教程

编写单元测试，可以按“明确规则—设计用例—准备环境—执行断言—清理与回归”的步骤进行：

1. **明确测试目标。** 确定被测函数或模块的输入、预期输出和异常行为，每个用例围绕一个明确的规则展开。
2. **设计测试用例。** 同时考虑正常、异常和边界情况，检查可达分支，以及循环执行零次、一次和多次时的行为。
3. **准备独立环境。** 复用基础数据的初始化逻辑，由各用例补充自己的附加数据；需要时模拟外部依赖或包含请求方法、请求体和 Cookie 的 Web 请求，避免用例相互影响。
4. **执行并验证结果。** 使用断言检查返回值、状态变化和错误信息。非法输入应产生可识别的校验或逻辑错误，不能只以“没有崩溃”判断测试通过。
5. **清理并持续回归。** 测试结束后释放资源、清理测试数据；修复问题后保留对应用例，并检查覆盖情况，防止同类问题再次出现。

### 3. 异常流程：区分逻辑异常和系统异常

我的理解是，异常流程也应有明确的预期结果。输入参数不合法、用户没有权限或信息状态不允许操作，都是可以预判的逻辑错误，应通过明确的异常类型和错误信息通知上层调用代码。参数错误应在校验阶段被识别，避免继续执行后产生空值访问、数据库约束失败等系统异常。

项目使用自定义的 `AppError` 表达业务错误，定义在 [`infrastructure/context.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/src/modules/infrastructure/context.ts)：

```ts
export class AppError extends Error {
  constructor(
    public statusCode: number,
    message: string,
  ) {
    super(message);
  }
}
```

业务层可以抛出 `new AppError(403, '只有发布者可以修改信息')`，由统一请求入口转换为对应的响应；参数校验产生的 `ZodError` 则转换为 `400` 和具体校验信息。真正未预期的系统异常另行记录并返回 `500`。测试时既要检查操作失败，也要检查异常类型、状态码和错误信息是否符合预期，例如非法参数应返回 `400`，不能因内部处理失误变成 `500`。

下面的客户端测试继续验证：上层调用代码能否收到明确的错误，而不是把异常响应当成正常数据。

以下节选自 [`client-api.test.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/test/client-api.test.ts)，测试 `api()` 的失败响应处理：

```ts
test("Unreadable error responses still report the HTTP failure", async (t) => {
  for (const body of ["<html>server error</html>", "", "null"]) {
    t.mock.method(
      globalThis,
      "fetch",
      async () => new Response(body, { status: 503 }),
    );
    await assert.rejects(
      api("/posts"),
      (error) =>
        error instanceof ApiError &&
        error.status === 503 &&
        error.message === "请求失败，请稍后重试",
    );
    t.mock.restoreAll();
  }
});
```

测试把 `fetch` 替换为可控响应，分别构造 HTML、空正文和 JSON `null`。即使错误正文无法按预期解析，函数仍应保留 HTTP 状态并拒绝请求。`assert.rejects()` 需要 `await`，这样测试才能等待异步断言结束。

### 4. 项目测试代码：重试不能产生重复消息

以下节选自 [`chat-delivery.test.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/test/chat-delivery.test.ts)。`fixture()` 创建隔离数据和会话，`f.input(1)` 生成固定设备、序号为 1 的消息输入。

```ts
const first = f.send(1);
assert.equal(
  sendMessage(f.ctx.db, f.conversation.id, f.a, f.input(1)).message.id,
  first.id,
);
assert.throws(
  () => sendMessage(f.ctx.db, f.conversation.id, f.a, f.input(1, "different")),
  /消息序号已被使用/,
);
```

它验证 `sendMessage()` 及仓储去重逻辑：同一个消息标识重试时应返回原 ID；沿用原标识却改变正文，应被拒绝。该用例实际访问临时 SQLite，属于业务集成测试。

### 5. 如何构造数据，如何考虑测试人员的刁难

**分别构造正常、边界和极端数据。** 正常数据用于验证功能的基本行为，边界数据检查规则允许范围的临界位置，极端数据检查空输入、大批量数据及异常组合。输入参数的边界需要单独测试，并检查返回值的内容和结构，不能只判断“函数没有报错”。

例如，附近查询的半径范围为 50～50000 米，设计用例时应分别考虑 `49`、`50`、`51` 和 `49999`、`50000`、`50001`；对于最大长度为 60 的标题，可以检查空字符串、全空格、长度 59、60、61 等情况。合法边界应返回正确有效的结果，越界参数应返回明确的校验错误。

| 维度 | 数据与操作 | 重点检查 |
| --- | --- | --- |
| 正常流程 | 两个独立账号；寻物、招领各一条；发布后搜索和联系 | 页面、接口和持久化能否形成完整流程 |
| 参数边界 | 标题长度临界值、经纬度上下限、查询半径上下限及其两侧 | 合法输入的输出有效，非法输入返回明确错误 |
| 输入异常 | 空标题、全空格、未来时间、非数字坐标、只填一个坐标 | 校验错误不演变为系统异常；草稿与正式发布规则不同 |
| 查询参数 | 中文与空格、SQL 特殊字符、空筛选、多项筛选、分页 | 关键词按字面处理，编码及筛选条件不丢失 |
| 导航路径 | `/`、`/me`、`/messages`、会话子路由、`/messages-old` | 避免多个标签同时高亮，避免错误前缀匹配 |
| 权限隔离 | 未登录；作者；其他用户；会话之外的第三人 | 不能编辑他人信息、查看他人草稿或读取私聊 |
| 业务状态 | 草稿、进行中、已完成、软删除 | 状态转换、列表可见性和联系入口符合规则 |
| 重复操作 | 重复收藏、重复发起联系、重复提交同一条消息 | 不生成重复记录或重复会话 |
| 地图查询 | 同一点、范围内外、无坐标、缺经度、legacy 坐标 | 距离为零也有效；不能把缺失经度当成零计算 |
| 循环与分批 | 空集合、单条、多条；49、50、51、125 条积压消息 | 检查循环进入、重复执行、退出和跨批次行为 |
| 网络与存储故障 | 响应丢失、WebSocket 不可用、本地写入失败、刷新 | 原消息标识保留，未持久化不 ACK，恢复后可重试 |
| 并发与过期 | 两个标签页同时发送；消息过期后重试 | 序号分配不冲突，过期正文不能被旧请求复活 |
| 文件上传 | 伪装 PNG、超过 5 MB、引用他人图片 | 检查文件头、大小、归属及失败回滚 |

**逐项覆盖分支和循环。** 编写测试时，应对照代码列出每个可达条件的成立与不成立情况，包括正常返回、提前返回、逻辑异常、异常捕获及清理路径。循环需要检查零次、一次、多次迭代，以及 `break`、`continue` 和分批处理的退出条件。每条可达流程都应有相应的测试用例和结果断言。

这里的目标是避免遗漏可达分支与循环的关键行为。循环次数可以不断增加，不能把所有次数和路径组合都穷举；分支被执行也不等于结果已验证正确。因此还需要结合输出断言和覆盖率报告检查遗漏。目前项目没有测量覆盖率百分比，不能仅凭现有测试通过就宣称已经实现全部分支覆盖。上表包含现有场景和后续补充用例的设计方向。

针对测试人员可能构造的情况，我会特别考虑绕过页面直接调用接口、切换身份、传入边界参数、重复请求和执行中途失败，检查系统在这些条件下能否返回预期结果并保持数据一致。

### 6. Web 请求模拟与测试数据隔离

**Web 系统需要验证完整的请求信息。** 测试既要能模拟 GET 查询，也要能构造 POST、PUT、DELETE 等方法，并携带请求体、Cookie 和其他请求头，才能验证登录、权限和参数解析。项目的 [`invokeRoute()`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/test/route-harness.ts) 根据这些信息构造 Web `Request`，调用真实 Route Handler 并读取响应；它不经过真实网络，实际 HTTP 路由和服务启动由浏览器测试补充验证。

以下节选自 [`nearby.test.ts`](https://github.com/LYanl7/052402132-102401507/blob/de86be3/apps/web/test/nearby.test.ts)，省略了运行时初始化及后续用例：

```ts
const call = (method: string, url: string, payload?: unknown, cookie?: string) =>
  invokeRoute({ method, url, payload, headers: cookie ? { cookie } : {} });

const registered = await call('POST', '/api/users/register', {
  email: 'nearby@example.com',
  password: 'password123',
  name: '地图测试',
});
const cookie = registered.headers['set-cookie'].split(';')[0];

async function create(title: string, overrides: object = {}) {
  const response = await call('POST', '/api/posts', { ...input, title, ...overrides }, cookie);
  assert.equal(response.statusCode, 201);
  return response.json().post;
}
```

这里先模拟 POST 注册，取得响应中的会话 Cookie，再携带 Cookie 和 JSON 请求体创建信息。`input` 是用例中定义的合法发布参数，`overrides` 用于构造不同状态或坐标。去掉 Cookie 可以验证未登录场景，更换其他用户的 Cookie 可以验证权限隔离；除了检查状态码，还应断言返回数据和数据库变更是否正确。

**将基础数据与附加数据分开。** 基础数据是多个 testcase 共同需要的初始化内容，例如发布者、联系者和无关用户这几种测试身份，可放进统一的 fixture。附加数据由各 testcase 自己建立，例如某个用例需要的草稿、已完成信息、特殊坐标或积压消息。

“共享基础数据”指复用初始化逻辑，每次测试仍应建立独立的数据副本，避免共享可变状态。对于使用数据库的独立用例，期望的执行顺序是：

1. 清空专用测试数据库，或新建等价的空内存、临时数据库。
2. 导入基础数据，建立测试身份和必要的公共记录。
3. 在当前 testcase 中导入附加数据。
4. 执行被测函数或模拟请求。
5. 验证返回值、逻辑异常及数据库结果。
6. 关闭连接并清理测试资源。

当前私聊测试通过 `fixture()` 为每个独立用例创建临时数据库、测试用户和会话，再由用例添加消息等附加数据；附近测试使用新的内存数据库。部分完整 API 流程中的子测试仍共享前置状态，后续可按上述方式拆成独立 fixture，进一步减少执行顺序依赖。纯函数测试则只需要准备输入，不必初始化数据库。

<a id="commits" name="commits"></a>

## 七、GitHub 代码签入记录

![GitHub master 分支提交记录，包含双方提交与 PR 合并](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task04/images/github-commits.png)

<a id="problems" name="problems"></a>

## 八、遇到的问题、尝试与收获

### 1. 请求封装导致部分操作失败

**问题：** 联调时，收藏、浏览记录和已读操作被后端拒绝。**尝试：** 检查请求后发现，没有请求体的操作也设置了 JSON 请求头，于是调整封装，只在发送 JSON 内容时设置对应请求头。**结果：** 修改后完整流程测试通过。**收获：** 公共封装需要考虑不同请求形式，排查接口问题时应同时检查请求头和请求体。

### 2. 模型与业务逻辑的拆分方式不符合预期

**问题：** 最初将模型和校验集中到共享包中，与希望按业务模块组织代码的思路不一致。**尝试：** 重新明确模块边界，把模型、校验和仓储归回各自业务模块，在模块内部按文件职责分离。**结果：** 调整后类型检查、构建和相关测试通过。**收获：** 拆分代码前应先明确职责和归属，目录组织也要便于理解和维护。

<a id="partner-review" name="partner-review"></a>

## 九、评价队友

**值得学习的地方：**

【待填写】

**需要改进的地方：**

【待填写】
