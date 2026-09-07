# Lumen

一个对话式的写实图像生成页面，使用 Hugging Face Inference Providers 调用 `XLabs-AI/flux-RealismLora`。

## 本地运行

1. 安装依赖：`npm install`
2. 将 `.env.example` 复制为 `.env`
3. 在 `.env` 中填入具备 **Inference Providers** 权限的 Hugging Face token
4. 启动：`npm run dev`
5. 打开 <http://localhost:3000>

## 安全设计

- token 仅由 Node.js 服务端读取，不会进入浏览器代码。
- `.env` 已被 `.gitignore` 排除。
- 服务端会清理错误信息中可能出现的 token。

## 许可

该 LoRA 基于 FLUX.1-dev，模型权重受 FLUX.1-dev Non-Commercial License 约束。使用前请阅读 Hugging Face 模型页中的最新许可条款。
