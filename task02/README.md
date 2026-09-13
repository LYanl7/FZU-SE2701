# 一箭又一箭

基于 Python + Pygame 的小游戏项目。

## 项目分层

- `src/presentation`：表现层，负责用户输入、界面渲染与动画播放。
- `src/logic`：逻辑层，负责处理用户操作、碰撞检测及胜负判定。
- `src/model`：数据模型层，负责维护箭头、网格及游戏状态。

## 开发环境

- Python 3.10+
- Pygame 2.5+

## 启动

```bash
python -m pip install -r requirements.txt
python main.py
```

当前版本已支持基础玩法，包括多关卡、直线与分段箭头、箭头阻挡判定、失误次数管理、胜利/失败界面，以及箭头飞出动画和碰撞反馈动画。
