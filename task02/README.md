# 一箭又一箭

基于 **Python + Pygame** 的点击式箭头解谜小游戏。观察箭头朝向与阻挡关系，按合适的顺序点击，让所有箭头飞出棋盘。

当前版本支持随机生成的直线与折线箭头、四方向路径检测、飞出和碰撞动画、失误限制、关卡切换、重新开始、计时与棋盘缩放。每个随机关卡在展示前都会检查是否存在完整解法。

[GitHub 仓库](https://github.com/LYanl7/FZU-SE2701) · [开发博客](blog.md)

## 游戏截图

| 开始界面 | 游戏过程 |
| --- | --- |
| ![开始界面](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task02/images/start.png) | ![游戏过程](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task02/images/gameplay.png) |

| 通关界面 | 失败界面 |
| --- | --- |
| ![通关界面](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task02/images/success.png) | ![失败界面](https://raw.githubusercontent.com/LYanl7/FZU-SE2701/main/task02/images/failure.png) |

## 开发环境

| 项目 | 要求或说明 |
| --- | --- |
| Python | 3.10 及以上，实际验证版本为 3.13.12 |
| 图形库 | Pygame `>=2.5,<3.0`，实际验证版本为 2.6.1 |
| 操作系统 | 本次在 Windows 环境验证；其他系统尚未实际验证 |
| 依赖管理 | 推荐 uv，也支持 Python venv + pip |
| 窗口 | 960 × 720，目标帧率 60 FPS |
| 字体 | 优先使用系统中文字体宋体、黑体或微软雅黑；字体文件不随仓库分发 |

运行游戏需要图形桌面环境。其他系统若显示中文方框，需要安装程序可识别的中文字体，或调整 `src/presentation/app.py` 中的字体候选列表。

## 安装和运行

先获取仓库并进入游戏目录；已有本地仓库时，直接进入 `task02` 即可。

```bash
git clone https://github.com/LYanl7/FZU-SE2701.git
cd FZU-SE2701/task02
```

### 方式一：uv（推荐）

已安装 uv 时执行：

```bash
uv sync
uv run python main.py
```

`uv sync` 根据项目配置与锁文件建立本地 `.venv`。首次安装依赖需要联网；游戏本身不需要账号、API Key 或在线服务。

### 方式二：venv + pip

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

macOS / Linux 对应命令（尚未在这些系统验证界面）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

若提示 `No module named pygame`，请确认安装依赖和启动游戏使用的是同一个虚拟环境。若提示找不到 `main.py`，请检查当前目录是否为 `task02`。

## 游戏规则与操作

1. 点击首页的“开始游戏”进入第一关，每关有 **3 次失误机会**。
2. 鼠标左键点击箭头的线条。箭头朝向由箭头尖端决定，折线的拐弯不改变其出口方向。
3. 箭头尖端到棋盘边界的前进路径上没有其他箭头时，播放飞出动画并消除该箭头。
4. 前方被其他箭头的线段阻挡时，箭头前移、碰撞晃动后返回，保留在棋盘中，同时扣除 1 次失误机会。
5. 本关箭头全部消除且飞出动画完成后，显示通关界面；点击“下一关”生成新关卡。
6. 第 3 次失误后显示失败界面，点击“重新开始”重试当前关卡。

| 操作或界面元素 | 作用 |
| --- | --- |
| 左键点击箭头线条 | 尝试消除该箭头 |
| 左键点击空白处 | 不消除箭头，也不扣失误机会 |
| 左上方“重新开始” | 恢复当前关卡原始布局、3 次失误机会和计时；不会重新随机布局 |
| 鼠标滚轮 / 棋盘下方 `－`、`＋` | 缩放内部棋盘内容，外框保持不变，范围约为 70%～240% |
| 顶部关卡编号 | 显示当前关卡 |
| 顶部爱心 | 显示剩余失误机会 |
| 右上角箭头图标及数字 | 显示尚未消除的箭头数量 |
| 时钟图标及时间 | 显示当前关卡用时；通关或失败后停止累计 |
| 关闭窗口 | 退出游戏 |

上、右、下、左分别使用青绿、珊瑚红、黄色、紫色，便于辨认方向。当前版本没有存档，退出后重新启动会从新的第一关开始。

## 项目结构

```text
task02/
├── main.py              # 游戏入口
├── src/model/           # 箭头、坐标与游戏状态
├── src/logic/           # 游戏规则和随机关卡生成
├── src/presentation/    # 界面、动画与资源
├── tests/               # 自动化测试
├── tools/               # 截图与交互验证脚本
├── images/              # 游戏截图
├── pyproject.toml       # 项目与依赖配置
├── requirements.txt     # pip 依赖列表
├── uv.lock              # uv 依赖锁文件
├── README.md            # 使用说明
└── blog.md              # 开发与测试记录
```

## 运行测试

在 `task02` 目录执行：

```bash
uv run python -m unittest discover -s tests -v
```

详细测试结果、实现思路和 AIGC 协作记录见 [开发博客](blog.md)。

## 资源说明

箭头、棋盘、爱心和按钮由 Pygame 绘图代码生成，计时图标位于 `src/presentation/assets/clock.svg`，界面截图由项目运行生成。中文字体使用系统字体，不随仓库分发。Pygame 是本项目使用的第三方图形库。
