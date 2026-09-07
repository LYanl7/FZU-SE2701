import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { InferenceClient } from "@huggingface/inference";
import "dotenv/config";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const publicDir = join(__dirname, "public");
const port = Number(process.env.PORT || 3000);
const model = "XLabs-AI/flux-RealismLora";

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

function sendJson(response, status, payload) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(payload));
}

async function readJson(request) {
  const chunks = [];
  let size = 0;

  for await (const chunk of request) {
    size += chunk.length;
    if (size > 32_768) throw new Error("请求内容过大");
    chunks.push(chunk);
  }

  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function cleanError(error) {
  const status = error?.httpResponse?.status;
  const raw = error?.message || "图像生成失败";

  if (status === 401 || status === 403) {
    return "Hugging Face 身份验证失败。请检查 HF_TOKEN 是否有效，并具备 Inference Providers 权限。";
  }
  if (status === 429) return "推理额度或请求频率已达上限，请稍后再试。";
  if (/gated|access/i.test(raw)) return "该模型需要先在 Hugging Face 页面接受许可条款。";
  return raw.replace(/hf_[A-Za-z0-9]+/g, "[已隐藏 token]").slice(0, 500);
}

async function generateImage(request, response) {
  if (!process.env.HF_TOKEN) {
    return sendJson(response, 503, {
      error: "服务端尚未配置 HF_TOKEN。请复制 .env.example 为 .env 并填入 token。",
    });
  }

  try {
    const body = await readJson(request);
    const prompt = String(body.prompt || "").trim();
    const negativePrompt = String(body.negativePrompt || "").trim();
    const width = Math.min(1440, Math.max(512, Number(body.width) || 1024));
    const height = Math.min(1440, Math.max(512, Number(body.height) || 1024));
    const steps = Math.min(50, Math.max(10, Number(body.steps) || 28));
    const guidance = Math.min(12, Math.max(1, Number(body.guidance) || 3.5));
    const seed = Number.isInteger(Number(body.seed)) ? Number(body.seed) : undefined;

    if (!prompt) return sendJson(response, 400, { error: "请输入图像描述。" });
    if (prompt.length > 2000) return sendJson(response, 400, { error: "提示词不能超过 2000 个字符。" });

    const client = new InferenceClient(process.env.HF_TOKEN);
    const image = await client.textToImage(
      {
        provider: "fal-ai",
        model,
        inputs: prompt,
        parameters: {
          width,
          height,
          num_inference_steps: steps,
          guidance_scale: guidance,
          ...(negativePrompt ? { negative_prompt: negativePrompt } : {}),
          ...(seed !== undefined ? { seed } : {}),
        },
      },
      { outputType: "blob" },
    );

    const bytes = Buffer.from(await image.arrayBuffer());
    response.writeHead(200, {
      "Content-Type": image.type || "image/jpeg",
      "Content-Length": bytes.length,
      "Cache-Control": "no-store",
      "X-Model": model,
    });
    response.end(bytes);
  } catch (error) {
    console.error("Generation failed:", cleanError(error));
    sendJson(response, error?.httpResponse?.status || 500, { error: cleanError(error) });
  }
}

async function serveStatic(request, response) {
  const requestPath = request.url === "/" ? "/index.html" : request.url.split("?")[0];
  const safePath = normalize(requestPath).replace(/^(\.\.[/\\])+/, "");
  const filePath = join(publicDir, safePath);

  if (!filePath.startsWith(publicDir)) {
    response.writeHead(403);
    return response.end("Forbidden");
  }

  try {
    const content = await readFile(filePath);
    response.writeHead(200, {
      "Content-Type": mimeTypes[extname(filePath).toLowerCase()] || "application/octet-stream",
      "Cache-Control": extname(filePath) === ".html" ? "no-cache" : "public, max-age=3600",
    });
    response.end(content);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
}

const server = http.createServer(async (request, response) => {
  if (request.method === "POST" && request.url === "/api/generate") {
    return generateImage(request, response);
  }
  if (request.method === "GET" && request.url === "/api/health") {
    return sendJson(response, 200, { ok: true, model, configured: Boolean(process.env.HF_TOKEN) });
  }
  if (request.method === "GET" || request.method === "HEAD") {
    return serveStatic(request, response);
  }
  response.writeHead(405, { Allow: "GET, HEAD, POST" });
  response.end();
});

server.listen(port, () => {
  console.log(`Lumen is ready at http://localhost:${port}`);
});
