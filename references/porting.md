# 移植到别的 AI 环境

> **目标**：别人的 AI 下载这个 skill 后，**只改 4 个函数**就能跑出一样的效果。

---

## 一、这个 skill 需要什么

**只有 4 个原语：**

| 原语 | 签名 | 要求 |
|---|---|---|
| **`js(code)`** | `-> Any` | 在**已打开的页面**里执行 JS 并返回结果。**只读用途** |
| **`click_xy(nx, ny)`** | `-> None` | 鼠标**点击**，坐标 **0~1000 归一化** |
| **`scroll(nx, ny, dir, amount)`** | `-> None` | 鼠标**滚动**，坐标同上 |
| **`screenshot(tag)`** | `-> None` | 截图，**可选**，没有就空实现 |

**只要这 4 件事能做到，脚本就能跑。**

```
你的 AI 环境  →  【适配层】  →  watch_loop.py
  (任意 API)      4 个函数        (业务逻辑，不用改)
```

---

## 二、怎么改

打开 `scripts/watch_loop.py`，找到 **「环境适配层」** 那一段：

```python
# --- 默认实现：Doubao / 通用 browser-use 运行时 ---
try:
    import seed_browser_use as _rt
except ImportError:
    _rt = None

def js(code):       return _rt.js(code)
def click_xy(nx,ny):_rt.click_xy(nx, ny)
def scroll(nx,ny,d,amount=2): _rt.scroll(nx, ny, d, amount=amount)
def screenshot(tag=""):       _rt.screenshot(tag=tag)
```

**把那 4 个函数体，换成你自己环境的调用即可。**

---

## 三、常见环境的适配示例

### ① Doubao / `seed_browser_use`（默认）

```python
import seed_browser_use as rt

def js(code):        return rt.js(code)
def click_xy(nx, ny):rt.click_xy(nx, ny)          # 已是 0~1000
def scroll(nx,ny,d,amount=2): rt.scroll(nx, ny, d, amount=amount)
def screenshot(tag=""):       rt.screenshot(tag=tag)
```

**不需要改。**

---

### ② Playwright（人写脚本 / 自动化）

> ⚠️ `page.evaluate` 用来**读**是允许的；**点击必须用 `page.mouse.click`**，不能用 `locator.click()`。

```python
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9222")   # 连已开的浏览器
page = browser.contexts[0].pages[0]


def js(code):
    # 包成函数体，直接 return 的写法可原样用
    return page.evaluate("() => { " + code + " }")


def click_xy(nx, ny):
    vw = page.evaluate("() => window.innerWidth")
    vh = page.evaluate("() => window.innerHeight")
    page.mouse.click(nx / 1000 * vw, ny / 1000 * vh)


def scroll(nx, ny, direction, amount=2):
    vw = page.evaluate("() => window.innerWidth")
    vh = page.evaluate("() => window.innerHeight")
    page.mouse.move(nx / 1000 * vw, ny / 1000 * vh)
    page.mouse.wheel(0, 300 * amount if direction == "down" else -300 * amount)


def screenshot(tag=""):
    page.screenshot(path=f"{tag or 'shot'}.png")
```

**⚠️ 注意**：`page.evaluate` 里传的 `code` 在本项目里**都是 `return ...;` 结尾的语句块**，
所以要用 `() => { ... }` 包起来。**如果某段代码没有 `return`，会返回 `None`。**

---

### ③ Claude Computer Use / OpenAI computer-use

**这类环境通常是"截图 + 坐标点击"，没有 `js()`。**

**你需要额外解决 `js()`**：
- 若浏览器开着远程调试端口 → 用 CDP（见 Playwright 示例）
- 否则 → **给浏览器装一个能执行 JS 的扩展**，或改用 Playwright 连接

```python
def js(code):
    # 例：通过 CDP 执行
    return cdp_session.send("Runtime.evaluate", {
        "expression": f"(() => {{ {code} }})()",
        "returnByValue": True,
    })["result"]["value"]


def click_xy(nx, ny):
    vw, vh = get_viewport()          # 你环境里拿视口尺寸的方法
    computer_click(int(nx / 1000 * vw), int(ny / 1000 * vh))


def scroll(nx, ny, direction, amount=2):
    vw, vh = get_viewport()
    computer_scroll(int(nx / 1000 * vw), int(ny / 1000 * vh),
                    0, 300 * amount * (1 if direction == "down" else -1))


def screenshot(tag=""):
    pass                              # 这些环境自带截图
```

---

### ④ 没有 `scroll` 原语的环境

**可以用键盘 PageDown 代替**（在目录区域先点一下获得焦点）：

```python
def scroll(nx, ny, direction, amount=2):
    click_xy(nx, ny)          # 先聚焦到目录
    for _ in range(amount):
        press_key("PageDown" if direction == "down" else "PageUp")
```

**注意**：这算"模拟输入"，不违反红线（仍然不是操作 DOM）。

---

## 四、移植后必须做的三件事

### ① 先跑 `probe.py`（只读探测）

```python
# 同样是先改 probe.py 顶部的适配层，再运行
```

**它会打印**：视口尺寸、`<video>` 矩形和算出的中心坐标、目录识别到几个小节、当前高亮是哪节、弹题结构。

**尾部给结论**：`✓ 可以运行 watch_loop.py` 或 `✗ 有元素识别失败`。

### ② 看 `watch_loop.py` 启动时的「几何自检」

同样内容，输出在脚本开头。

### ③ 若识别不到，调这三个参数

| 参数 | 默认 | 什么时候调 |
|---|---|---|
| `MIN_SECTION_W` | 100 | 小屏幕 / 大缩放识别不到小节 → **调小** |
| `MIN_SECTION_H` | 14 | 同上 |
| `CATALOG_X_TOLERANCE` | 0.15 | 混进别的列表 → **调小**；一栏都没识别到 → **调大** |

---

## 五、红线（移植时同样不能破）

| ✅ 允许 | ❌ 禁止 |
|---|---|
| 模拟鼠标点击 / 滚动 / 键盘 | `element.click()` / `dispatchEvent` |
| 只读 JS（`querySelector` / `getBoundingClientRect`） | JS 写操作（`value =` / `setAttribute`） |
| — | 任何网络请求（`requests` / `fetch` / 直连接口） |

**理由**：
1. **实测 `element.click()` 对智慧树的弹题选项无效** —— 不是规范问题，是根本不管用
2. **网络请求属于爬虫**，不是这个 skill 的定位

---

## 六、一句话

> **这个 skill 的全部逻辑都建立在「能读 DOM、能用鼠标点」这两件事上。**
> **你的 AI 只要能做这两件事，改 4 行就能跑。**
