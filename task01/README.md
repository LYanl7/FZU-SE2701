| 这个作业属于哪个课程 | [202601 软件工程](https://edu.cnblogs.com/campus/fzu/202601SofwareEngineering) |
| ----------------- | --------------- |
| 这个作业要求在哪里 | [第一次个人作业](https://edu.cnblogs.com/campus/fzu/202601SofwareEngineering/homework/15712) |
| 这个作业的目标 | 完成 Hugging Face 图像生成 API 与前端交互，建设 GitHub 个人主页，梳理技能与学习规划，熟悉 Markdown 和 Git/GitHub 协作流程 |
| 学号 | 052402132 |

---

# 第一次个人作业

## 一、准备工作

- GitHub ID：[LYanl7](https://github.com/LYanl7)
- 作业仓库：[FZU-SE2701](https://github.com/LYanl7/FZU-SE2701)
- 博客园个人主页： [LYanl7](https://www.cnblogs.com/LYanl7/)
- 班级：[202601 软件工程](https://edu.cnblogs.com/campus/fzu/202601SofwareEngineering)

## 二、Hugging Face API 调用

### 1. 项目简介

我完成了一个名为 **Lumen** 的对话式写实图像生成网页。用户可以输入提示词，设置画面比例、推理步数、引导强度、反向提示词和随机种子，再由 Node.js 服务端调用 Hugging Face Inference Providers 上的 [XLabs-AI/flux-RealismLora](https://huggingface.co/XLabs-AI/flux-RealismLora) 模型生成图片。

项目位于 [chat-app](https://github.com/LYanl7/FZU-SE2701/tree/main/task01/chat-app) 目录，使用 HTML、CSS、原生 JavaScript、Node.js、dotenv 和 @huggingface/inference。

### 2. 页面展示

![Lumen 前端首页](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task01/images/lumen-home.png)

页面实现了提示词输入、灵感提示、生成参数调整、加载与错误状态、图片下载、提示词复用、最近创作记录、明暗主题和移动端适配。

### 3. API 调用步骤

1. 在 [Hugging Face](https://huggingface.co/) 注册账号并创建 Access Token。
2. 安装依赖并启动项目：

   ~~~bash
   cd task01/chat-app
   npm install
   npm start
   ~~~

3. 启动前先将 .env.example 复制为 .env，并配置：

   ~~~dotenv
   HF_TOKEN=hf_xxxxxxxxxxxxxxxxx
   PORT=3000
   ~~~

4. 浏览器访问 http://localhost:3000，输入提示词并等待生成结果。


### 4. 核心代码

~~~javascript
const client = new InferenceClient(process.env.HF_TOKEN);
const image = await client.textToImage(
  {
    provider: "fal-ai",
    model: "XLabs-AI/flux-RealismLora",
    inputs: prompt,
    parameters: {
      width,
      height,
      num_inference_steps: steps,
      guidance_scale: guidance,
      negative_prompt: negativePrompt,
      seed,
    },
  },
  { outputType: "blob" },
);
~~~

服务端还实现了请求体大小限制、提示词长度校验、参数范围限制、状态码处理及 Token 脱敏。

### 5. 调用记录与体验

由于 ChatGPT 写完代码之后跑了三次 E2E 测试，导致我的余额用光了，所以这里就没有最终生成图像了。

## 三、GitHub 个人主页建设

我选择“创建个人资料自述文件”的方案，建立了与 GitHub ID 同名的 [LYanl7/LYanl7](https://github.com/LYanl7/LYanl7) 仓库。

![GitHub 个人主页](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task01/images/github-profile.png)

我的主页展示了技术栈、GitHub 统计、常用语言和 Steam 兴趣信息。

### 自我评估

| 能力 | 当前情况 | 仍需提升 |
| --- | --- | --- |
| Web 后端开发 | 能使用 Spring Boot、MyBatis 和常见数据库完成基础业务功能 | 系统设计、并发编程、性能分析和故障排查经验不足 |
| Web 前端开发 | 能 review AI 写的代码 | UI/UX 设计和审美 |

我目前最感兴趣的是游戏开发，但也希望在软件工程课程中学习到更多关于团队协作、项目管理和软件质量保障的知识。

### 未来三年规划

早日实习，除此之外希望能在原子弹爆炸之前做一些自己想做的事情。

## 四、技能树、代码量与课程期待

### 1. 当前技能树

我已经具备 Java/TypeScript 基础、Web 前后端开发、数据库与常用中间件使用能力，也能使用 Git 管理项目。当前短板主要是大型项目经验不足，对软件需求、架构权衡、自动化测试、持续交付和多人协作的理解还不够系统。

### 2. 代码量

用行来衡量代码量我觉得挺离谱的，我个人更倾向于用解决过的问题来衡量个人的水平，但是我由于我前两年只看了黑马程序员做了一些烂大街的玩具项目，所以我可以说基本是没有任何真实问题的解决能力的。

### 3. 课程期待

我最期待学习：

- 如何把模糊需求转化为可验证、可追踪的任务；
- 如何进行模块划分、接口设计和技术选型；
- 如何通过 Git 分支、Issue、代码评审和持续集成开展团队协作；
- 如何设计单元测试、集成测试并建立质量标准；
- 如何估算进度、识别风险并进行迭代复盘；
- 如何维护文档，使项目可理解、可运行和可扩展。

我希望课程结束时，不仅能写出可运行的程序，还能解释需求、设计、测试和协作过程，并对软件质量负责。

## 五、AI 生成的软件工程课程学习指南

本节选择 **ChatGPT（Codex）** 生成一份简要学习指南。

### AI 生成的指南

> #### 一、学习目标
>
> 完成课程后，你应能够：
>
> - 理解软件生命周期与常见开发模型
> - 分析需求并编写需求规格说明
> - 使用 UML 进行系统建模
> - 掌握模块化、低耦合与高内聚等设计原则
> - 运用 Git、测试和项目管理工具协作开发
> - 完成一个结构规范的小型软件项目
>
> #### 二、核心知识
>
> 1. **软件过程**：瀑布模型、迭代开发、敏捷开发、DevOps
> 2. **需求工程**：需求获取、用户故事、用例、需求验证
> 3. **软件设计**：架构设计、模块划分、接口设计、设计模式
> 4. **软件建模**：用例图、类图、时序图、活动图
> 5. **软件测试**：单元测试、集成测试、系统测试、验收测试
> 6. **项目管理**：任务分解、进度估算、风险管理、团队协作
> 7. **质量与维护**：代码审查、重构、版本控制、持续集成
>
> #### 三、推荐学习顺序
>
> ```text
> 软件过程
>    ↓
> 需求分析
>    ↓
> UML 建模
>    ↓
> 架构与详细设计
>    ↓
> 编码与版本控制
>    ↓
> 测试与质量保证
>    ↓
> 部署、维护与复盘
> ```
>
> #### 四、学习方法
>
> - **课前**：快速浏览概念，记录不理解的术语。
> - **课中**：重点理解“为什么这样设计”，不要只背定义。
> - **课后**：通过一个持续迭代的小项目应用所学知识。
> - **每周**：整理知识图谱，并复盘需求、设计、代码和测试之间的联系。
>
> #### 五、实践项目建议
>
> 选择一个规模适中的项目，如图书管理系统、记账应用或课程管理平台，并依次完成：
>
> - 项目计划与任务分工
> - 用户故事和需求规格说明
> - UML 用例图、类图及时序图
> - 系统架构与数据库设计
> - Git 分支协作和代码审查
> - 单元测试与集成测试
> - 项目演示、文档和总结
>
> #### 六、常用工具
>
> - 版本控制：Git、GitHub 或 GitLab
> - 建模：PlantUML、draw.io
> - 项目管理：Trello、Jira
> - 测试：JUnit、pytest
> - 持续集成：GitHub Actions、GitLab CI
>
> #### 七、考核准备
>
> - **概念题**：理解术语的含义、适用场景与优缺点。
> - **分析题**：练习从案例中识别需求、风险和开发模型。
> - **建模题**：确保 UML 元素、关系与业务逻辑一致。
> - **项目答辩**：能说明需求来源、设计取舍、测试方法及个人贡献。
>
> 学习软件工程的关键不是记住流程，而是建立“需求—设计—实现—测试—维护”的整体思维。

### 合理性分析

我比较认可实践优先的学习方案，我认为各样的技术都对应各样的具体情境，也就是对应具体的问题。
