---
name: zhihuishu-auto-watch
description: 智慧树(zhihuishu.com)课程学习页自动值守助手。视频播放中自动检测并作答弹题（单选/判断选A，多选全选），答完点关闭；右侧目录当前小节出现蓝色勾完成标记后自动切换到下一个未完成、有时长的小节并点击画面开始播放。全程使用鼠标坐标模拟点击（禁止 JS element.click()），每次操作后截图查验。当用户要求在智慧树/知到/zhihuishu 上自动刷课、自动看视频、自动答题、自动切换下一节、保持监控不遗漏弹题时使用。
---

# 智慧树自动值守

## 前置条件

- 浏览器已打开智慧树学习页（URL 形如 `https://studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=...`）
- 用户已完成登录（如需登录，用 `interaction.request_action(type="browserControl")` 交接给用户）
- 使用 `computer_use_tool` with `plane="bu"`，代码内 `import seed_browser_use as bu`

## 🖥️ 跨机器适配（换电脑第一件事）

**坐标类操作在不同电脑上会失效**，因为：分辨率、窗口大小、**浏览器缩放**、页面改版都不同。

### 本 skill 的做法：不硬编码任何屏幕坐标

| 要点的位置 | 怎么算出来 |
|---|---|
| **视频画面中央** | 读 `<video>` 的 `getBoundingClientRect()` → 取中心 |
| **右侧目录区域** | 把所有「有时长的小节 `li`」按 x 坐标聚类 → 取整体包围盒 |
| **选项 / 按钮 / X** | 读该元素的 `getBoundingClientRect()` → 取中心 |

换算：`归一化 = 像素 / 视口尺寸 × 1000`（0~1000）

> **只要元素能在 DOM 里被找到，坐标就永远是对的。**

### ⚠️ 换机器后必须先跑 `scripts/probe.py`

**这是只读探测脚本**——不点鼠标、不滚动、不发请求。它打印：

1. 视口尺寸 + `devicePixelRatio`（看有没有系统缩放）
2. `<video>` 的矩形和**算出来的中心归一化坐标**
3. 右侧目录识别到多少小节、x 中位数、当前高亮是哪节、未完成候选有几个
4. 弹题弹窗的结构（题干、选项数、「关闭」按钮数）

**尾部会给出结论**：`✓ 可以运行 watch_loop.py` 或 `✗ 有元素识别失败`。

**probe 通过后再跑 `watch_loop.py`。**

### 识别不到时的三个调节旋钮

`watch_loop.py` 顶部：

| 参数 | 默认 | 什么时候调 |
|---|---|---|
| `MIN_SECTION_W` | 100 | 小屏幕 / 大缩放下识别不到小节 → **调小** |
| `MIN_SECTION_H` | 14 | 同上 |
| `CATALOG_X_TOLERANCE` | 0.15 | 目录栏识别不准 / 混进别的列表 → **调小**；一栏都没识别到 → 调大 |

`watch_loop.py` 启动时也会打印一次**几何自检**（`SELF_CHECK = True`），内容和 probe 类似。

---

## 核心规则（用户锁定，不要改）

### 🚨 红线：只用鼠标模拟，不用爬虫

| ✅ 只能用这三个 | 用途 |
|---|---|
| `bu.click_xy(nx, ny)` | 点击（坐标 **0~1000 归一化**） |
| `bu.scroll(x, y, dir, amount=...)` | 滚动 |
| `bu.screenshot(tag=...)` | 截图 |

| ❌ 禁止 | 说明 |
|---|---|
| `element.click()` / `bu.click(ref)` | **实测对弹题选项无效** |
| `element.dispatchEvent(...)` | 直接触发 DOM 事件 |
| `element.value = ...` / `setAttribute` / `classList` 写操作 | 改动页面 |
| `form.submit()` | 提交表单 |
| `requests` / `urllib` / `httpx` / `aiohttp` | **网络请求 = 爬虫** |
| `fetch(...)` / `XMLHttpRequest` | 页面内发请求 |
| 直接调智慧树任何接口 | 爬虫 |

**`bu.js(...)` 只允许只读用途**：
`getBoundingClientRect()` / `innerText` / `className` / `getComputedStyle()` / `querySelector*`
→ **拿来算坐标、判状态；不允许任何写操作。**

### 具体规则

1. **作答规则**：
   - 单选题、判断题 → 选第一个选项（A）
   - 多选题 → 依次点击所有选项（全选）
   - 选完后点弹窗底部「关闭」按钮
   - **多选判定只看 `.topic-title`**（不要扫 `dlg.innerText` 全文，会误判）
2. **点击方式**：全程用 `bu.click_xy(nx, ny)` 鼠标坐标模拟点击，**禁止** `element.click()` / `bu.click(ref)`。先用 `bu.js` 调 `getBoundingClientRect()` 拿到像素矩形，再换算成视口归一化坐标（0-1000）。3. **截图查验**：每次作答后、关闭弹窗后都要 `bu.screenshot(tag="...")` 截图确认。
4. **目录校验 + 切换**（**每一轮都要做**）：
   - 读右侧目录的**当前高亮小节**（即正在播的那一节）
   - **若它已有蓝色勾（`b.time_icofinish`）→ 立即切走**，绝不继续播
   - 切换目标必须是：**没勾 + 没进度环 + 有时长 + 在视口内 + 不是当前这节**
   - 切完**再校验一次**：新的高亮项必须是未完成的
   - 找不到就 `bu.scroll(850,500,"down",amount=2)` 滚动目录再找（连滚两次仍无 → 可能已全部完成，报出来）

   > **核心原则：播放的项目必须始终是"未完成"的。已完成的一律不播。**

5. **视频暂停**：检测到 `video.paused===true` 且非弹窗导致时，点画面中央继续。
   **但 `video.ended===true` 时不要点中央**——那可能是"重播"按钮，会从头再播一遍。**等目录打勾后由规则 4 切换。**
6. **循环不中断**：处理完弹题或切换后 **`continue`**，不要 `break`。否则每次只能处理一个事件，中间有值守空窗期。
7. **浏览器窗口不要关闭**，值守结束后保留界面供用户检查。

## 关键 DOM 选择器（已踩坑验证）

| 元素 | 选择器 | 说明 |
|---|---|---|
| 弹题弹窗根节点 | `.dialog-test` | fixed 定位，判断可见性不要用 offsetParent |
| 选项列表 | `.topic-item`（`<li>`） | 单选/判断只有 2 个，多选 3-5 个 |
| 题干 | `.topic-title` | 判断是否多选看题干含"多选" |
| 关闭按钮 | 文本为「关闭」的 button/span/div | 在弹窗底部 |
| 右侧目录完成图标 | `b.time_icofinish` | 蓝色勾，打勾=完成 |
| 右侧目录进行中 | `span.progress-num` | 显示 "XX%" |
| 右侧目录未开始 | 无图标 | 最右端空 |
| 当前高亮项 | `backgroundColor` 非 rgba(0,0,0,0) 且非 rgb(255,255,255) | 蓝色背景行 |

### 弹窗可见性判定（不要用 offsetParent）

```js
const dlg = document.querySelector('.dialog-test');
let open = false;
if (dlg) {
  const r = dlg.getBoundingClientRect();
  const cs = getComputedStyle(dlg);
  open = r.width>100 && r.height>100
      && cs.display!=='none' && cs.visibility!=='hidden'
      && parseFloat(cs.opacity)>0.1;
}
```

## 坐标换算

```python
s = bu.js("return {w: window.innerWidth, h: window.innerHeight};")
def click_center_of(rect):
    nx = round((rect['x'] + rect['w']/2) / s['w'] * 1000)
    ny = round((rect['y'] + rect['h']/2) / s['h'] * 1000)
    nx = max(0, min(999, nx)); ny = max(0, min(999, ny))
    bu.click_xy(nx, ny)
```

- `bu.click_xy` / `bu.scroll` 坐标必须是 **0-1000 归一化值**，传像素会报 `BU_COORDINATE_SPACE`。
- 像素 y 接近视口底部时，归一化后可能 >1000，必须 `min(999, ...)` 截断，否则报 `ValueError: y=... is outside the 0-1000 viewport coordinate space`。

## 监控循环（直接复用）

每 8-10 秒一轮，每轮做四件事：读 video 状态 → 读弹窗可见性 → **读右侧目录并校验当前小节** → 按需操作。
完整脚本见 `scripts/watch_loop.py`。

**每轮顺序（重要）：**

1. 读 `video.currentTime / duration / paused / ended` + `.dialog-test` 可见性
2. **弹题优先**：弹窗可见 → 处理弹题 → `continue`
3. **目录校验**：读当前高亮小节
   - 读不到 → 等下一轮
   - **已完成 → 切到下一未完成小节 → `continue`**
   - 未完成 → 进第 4 步
4. **保证在播**：`paused` → 点中央；**`ended` → 什么都不做**（等打勾）

**循环要点：**
- 每轮打印 `rN / 秒 / ct / dur / paused / ended / dlg` 便于追踪
- 弹窗出现 → 读选项矩形 → 按规则坐标点击 → 截图 → 点关闭 → **检查是否弹出「未做答不能关闭」提示框** → 若有则关提示框、重选、再关
- 切换小节后**必须校验**新的高亮项是未完成的
- 找不到未完成小节 → 滚目录再找 → 连滚两次仍无 → 打印出来，**不要静默失败**

## pick_next_section 筛选规则

```js
// 右侧目录 li 同时满足：
// 1. x > window.innerWidth * 0.7  （只看右侧目录，排除左侧视频区）
// 2. 文本匹配 /00:\d{2}:\d{2}/    （有时长，排除章节标题行）
// 3. 不含 .time_icofinish          （没打勾）
// 4. 不含 .progress-num            （没在进行中）
// 5. y 在视口内 (0 < y < innerHeight)
// 取第一个满足的
```

## 操作者使用说明（给用户看）

1. 先在浏览器打开智慧树课程学习页，完成登录。
2. 告诉 agent「帮我自动刷智慧树这门课」即可启动值守。
3. 值守过程中不要手动操作浏览器窗口，让自动流程处理弹题和章节切换。
4. 弹题对错不计较（按规则乱选），只要不卡弹窗就行。
5. 如果想中途停下，直接说「停」或「暂停值守」。
6. 值守结束后浏览器窗口会保留，方便检查进度。
7. **值守会自动跳过已完成的小节** —— 只会播未完成的。

## 已修复的坑（2026-10-08）

| 坑 | 现象 | 修法 |
|---|---|---|
| **多选误判** | `'多选' in dlg.innerText` —— 全文包含题干，**只会误判不会帮忙** | 只匹配 `.topic-title` |
| **弹窗消失竞态** | 判完 `dialogOpen` 到读弹窗之间有往返延迟，`dlg` 可能为 null → `dlg.querySelectorAll` 抛错 → **脚本死** | JS 里加 `if (!dlg) return null;` |
| **未做答死循环** | 多选没选上 → 点关闭 → 弹提示框 → 点中央点到提示框上 → `break` → **每次重跑都卡同一处** | 实现「关提示框 → 重读选项 → 重选 → 再关」完整流程 |
| **播完重播** | `video.ended` 时点中央，若中央是"重播"按钮 → **整节白看** | `ended` 时什么都不做，等目录打勾 |
| **空选项静默失败** | `.topic-item` 读不到 → 不点选项 → 直接点关闭 → **触发死循环** | `options` 为空时**绝不点关闭**，报错并跳过 |
| **值守空窗期** | 处理完弹题就 `break` → 退出循环 → 第二道弹题没人管 | 改成 `continue` |

## 已验证走不通的做法（不要重试）

- `element.click()` 对弹题选项无效，必须坐标点击
- 凭像素估计坐标点选项 `<li>` 会点偏（点到 LI 外部），必须先 getBoundingClientRect
- `offsetParent!==null` 判断 fixed 弹窗不可靠（fixed 元素 offsetParent 为 null）
- `bu.scroll` 传像素坐标报 BU_COORDINATE_SPACE，必须归一化
- Python 字典字面量 `{x: ...}` 中 x 被当变量名导致 NameError，必须写 `{'x': ...}`
- 多选题没选就点关闭 → 弹"未做答不能关闭"，需先关提示框再重选
