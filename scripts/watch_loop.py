"""
智慧树自动值守 —— 监控循环脚本（可移植版）

============================================================
🎯 移植到别的 AI 环境：只改「环境适配层」4 行
============================================================

本 skill 只需要你的环境提供 **4 个能力**：

  | 原语 | 签名 | 要求 |
  |---|---|---|
  | `js`         | `js(code) -> Any`            | 在**已打开的页面**里执行 JS，返回 JSON 可序列化的值。**只读用途** |
  | `click_xy`   | `click_xy(nx, ny)`           | 鼠标**点击**，坐标是 **0~1000 归一化值** |
  | `scroll`     | `scroll(nx, ny, dir, amount)`| 鼠标**滚动**，坐标同上 |
  | `screenshot` | `screenshot(tag)`            | 截图（可选，可空实现） |

**只要你的 AI 能做到这 4 件事，这个脚本就能跑。**

往下找到「环境适配层」，把那 4 个函数体改成你自己环境的调用。
**其余代码一行都不用动。**

常见环境的适配示例见 `references/porting.md`。

============================================================
🚨 红线规则（任何改动都不得违反）
============================================================

【1】所有操作一律通过「模拟鼠标」完成，只用上面那 3 个写操作
      （click_xy / scroll / screenshot）

【2】禁止任何形式的「直接操作 DOM」：

      ✗ element.click()
      ✗ element.dispatchEvent(new MouseEvent(...))
      ✗ element.value = ...
      ✗ element.setAttribute(...) / classList.add|remove(...)
      ✗ form.submit()

    原因：智慧树的弹题选项对 element.click() 无效，实测走不通（见 SKILL.md）。

【3】禁止任何形式的爬虫 / 网络请求：

      ✗ requests / urllib / httpx / aiohttp
      ✗ fetch(...) / XMLHttpRequest
      ✗ 直接请求智慧树的任何接口

【4】js(...) 只允许「只读」用途：

      ✓ getBoundingClientRect()   → 算坐标
      ✓ innerText / className     → 判断状态
      ✓ getComputedStyle()        → 判断可见性
      ✓ querySelector*            → 定位元素
      ✗ 任何写操作（见【2】）

============================================================
🖥️ 跨机器适配
============================================================
不同电脑的分辨率、窗口大小、浏览器缩放都不同。
**本脚本不硬编码任何屏幕坐标**，全部从 DOM 实时探测：

  | 要点的位置 | 怎么算 |
  |---|---|
  | 视频画面中央 | 读 <video> 的 getBoundingClientRect()，取中心 |
  | 右侧目录区域 | 把所有「有时长的小节 li」按 x 聚类，取整体包围盒 |
  | 选项 / 按钮 / X | 读该元素的 getBoundingClientRect()，取中心 |

换算：`归一化 = 像素 / 视口尺寸 × 1000`

**换机器后先跑 `scripts/probe.py`（只读探测），确认几何信息正确再跑本脚本。**

============================================================
修订记录（2026-10-08）
============================================================
  · 新增「环境适配层」——移植只需改 4 行
  · 去掉全部硬编码屏幕坐标，改为 DOM 实时探测
  · 修复 多选误判：只匹配 .topic-title，不再扫全文
  · 修复 .dialog-test 为 null 时崩溃
  · 新增「未做答不能关闭」提示框处理
  · 修复 视频 ended 后点中央导致重播
  · 修复 options 为空时仍点关闭 → 触发死循环
  · 修复 break 导致每次只处理一个事件
  · 新增 播放前校验「当前小节必须未完成」
"""

# ===== 复制开始 =====
import time

# ============================================================
# 环境适配层  ⚠️ 移植时【只改这一段】
# ============================================================

# --- 默认实现：Doubao / 通用 browser-use 运行时 ---
try:
    import seed_browser_use as _rt
except ImportError:                     # 换环境时这里会失败 —— 正常，见下
    _rt = None


def js(code):
    """在页面里执行只读 JS，返回 JSON 可序列化的值。"""
    if _rt is None:
        raise RuntimeError("请先在「环境适配层」里接入你自己环境的 js()")
    return _rt.js(code)


def click_xy(nx, ny):
    """按 0~1000 归一化坐标模拟鼠标点击。"""
    if _rt is None:
        raise RuntimeError("请先在「环境适配层」里接入你自己环境的 click_xy()")
    _rt.click_xy(nx, ny)


def scroll(nx, ny, direction, amount=2):
    """按 0~1000 归一化坐标模拟滚动。"""
    if _rt is None:
        raise RuntimeError("请先在「环境适配层」里接入你自己环境的 scroll()")
    _rt.scroll(nx, ny, direction, amount=amount)


def screenshot(tag=""):
    """截图（可选）。没有这个能力时空实现即可。"""
    if _rt is None:
        return
    _rt.screenshot(tag=tag)


# 下面这些名字在旧版脚本里用过，保留以免破坏兼容
bu = _rt

# ============================================================
# 可调参数（换机器主要调这里）
# ============================================================
RUN_SECONDS = 270        # 单次运行上限（秒），需小于外层工具超时
LOOP_SLEEP = 8           # 每轮间隔（秒）
DEBUG = True

# 判定「这是一个小节条目」的最小尺寸（像素）。
# 屏幕特别小 / 缩放很大时，如果识别不到小节，把这两个值调小。
MIN_SECTION_W = 100
MIN_SECTION_H = 14

# 目录聚类：所有小节 li 的 x 坐标中位数，允许偏离多少比例算同一栏。
# 布局改版导致目录识别不准时，调这个值。
CATALOG_X_TOLERANCE = 0.15

# 启动时打印一次探测到的几何信息（换机器时看这个判断对不对）
SELF_CHECK = True


# ============================================================
# 基础工具
# ============================================================
def log(*args):
    print(*args, flush=True)


def vp_size():
    """视口尺寸。归一化坐标全靠它。"""
    return js("return {w: window.innerWidth, h: window.innerHeight};")


def rect_center(rect):
    """像素矩形 → 中心点（像素坐标）。"""
    return (rect['x'] + rect['w'] / 2, rect['y'] + rect['h'] / 2)


def click_rect(rect, label=""):
    """
    点矩形的中心。
    ⚠️ 不使用 element.click()，只用归一化坐标 + 模拟鼠标。
    """
    if not rect or rect.get('w', 0) <= 0 or rect.get('h', 0) <= 0:
        log("  [warn] click_rect 收到无效矩形 %s %s" % (label, rect))
        return False
    s = vp_size()
    cx, cy = rect_center(rect)
    nx = round(cx / s['w'] * 1000)
    ny = round(cy / s['h'] * 1000)
    nx = max(0, min(999, nx))          # 截断，否则报 y outside 0-1000
    ny = max(0, min(999, ny))
    if DEBUG and label:
        log("  click %s  px=(%.0f,%.0f)  norm=(%d,%d)" % (label, cx, cy, nx, ny))
    click_xy(nx, ny)
    return True


# ============================================================
# 几何探测（跨机器适配的核心）
# ============================================================
VIDEO_RECT_JS = r"""
const v = document.querySelector('video');
if (!v) return null;
const r = v.getBoundingClientRect();
if (r.width < 50 || r.height < 50) return null;
return {x: r.x, y: r.y, w: r.width, h: r.height};
"""


def video_rect():
    """视频播放区域的矩形。用它算「点画面中央」，不硬编码 (500,500)。"""
    return js(VIDEO_RECT_JS)


def click_video_center(label="video-center"):
    """点视频画面正中央（开始/恢复播放）。位置从 <video> 元素实时算。"""
    r = video_rect()
    if not r:
        # 兜底：点视口正中。
        # 注意 500,500 是【归一化坐标】(0~1000) 的正中，等价于"屏幕 50% 位置"，
        # 不是像素值 —— 换分辨率依然成立。仅在找不到 <video> 时走这里。
        log("  [warn] 找不到 <video>，退化为点视口正中（归一化 500,500）")
        click_xy(500, 500)
        return
    click_rect(r, label)


# ============================================================
# 右侧目录
# ============================================================
SECTION_JS = r"""
const vw = window.innerWidth, vh = window.innerHeight;
const raw = [];
document.querySelectorAll('li').forEach((li) => {
  const t = (li.innerText || '').trim();
  if (!t) return;
  const r = li.getBoundingClientRect();
  if (r.width < %(minw)d || r.height < %(minh)d) return;
  if (!/00:\d{2}:\d{2}/.test(t)) return;      // 必须含时长 → 排除章节标题行
  const cs = getComputedStyle(li);
  const bg = cs.backgroundColor;
  raw.push({
    text: t.replace(/\n/g, ' | ').slice(0, 60),
    finish: !!li.querySelector('.time_icofinish'),
    progress: !!li.querySelector('.progress-num'),
    highlighted: !!(bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'rgb(255, 255, 255)'),
    x: r.x, y: r.y, w: r.width, h: r.height
  });
});
if (!raw.length) return {items: [], catalog: null};

// ---- 自动判断哪些是「右侧目录」：按 x 聚类，取最大的一簇 ----
// 不写死 vw*0.7，这样换分辨率/布局也能自适应
const xs = raw.map(o => o.x).sort((a, b) => a - b);
const medianX = xs[Math.floor(xs.length / 2)];
const tol = vw * %(tol)f;
let items = raw.filter(o => Math.abs(o.x - medianX) <= tol);
if (!items.length) items = raw;            // 兜底：聚不出来就全用

let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
items.forEach(o => {
  minX = Math.min(minX, o.x);  maxX = Math.max(maxX, o.x + o.w);
  minY = Math.min(minY, o.y);  maxY = Math.max(maxY, o.y + o.h);
});
items.forEach(o => { o.inView = o.y > -o.h && o.y < vh; });

return {
  items: items,
  catalog: {x: minX, y: minY, w: maxX - minX, h: maxY - minY},
  medianX: medianX,
  droppedCount: raw.length - items.length
};
"""


def read_catalog():
    return js(SECTION_JS % {
        'minw': MIN_SECTION_W,
        'minh': MIN_SECTION_H,
        'tol': CATALOG_X_TOLERANCE,
    })


def get_current_section():
    """当前高亮的小节 = 正在播放的那一节。"""
    cat = read_catalog()
    for s in cat.get('items', []):
        if s['highlighted']:
            return s
    return None


def pick_next_unfinished(avoid_text=None):
    """
    下一个可用小节：
      · 未完成（无 .time_icofinish）
      · 未在进行中（无 .progress-num）
      · 在视口内
      · 不是 avoid_text 这一节（防原地打转）
    """
    cat = read_catalog()
    for s in cat.get('items', []):
        if s['finish'] or s['progress']:
            continue
        if not s['inView']:
            continue
        if avoid_text and s['text'] == avoid_text:
            continue
        return s
    return None


def scroll_catalog():
    """滚动右侧目录。滚动点从目录包围盒实时算。"""
    cat = read_catalog()
    c = cat.get('catalog')
    if not c:
        log("  [warn] 探测不到目录区域，跳过滚动")
        return False
    s = vp_size()
    nx = max(0, min(999, round((c['x'] + c['w'] / 2) / s['w'] * 1000)))
    ny = max(0, min(999, round((c['y'] + c['h'] / 2) / s['h'] * 1000)))
    if DEBUG:
        log("  scroll 目录 norm=(%d,%d)  目录盒=%s" % (nx, ny, c))
    scroll(nx, ny, "down", amount=2)
    return True


def switch_to_section(sec, reason=""):
    """切到指定小节并开始播放，切换后校验它确实是未完成的。"""
    log("  >>> 切换小节 [%s]: %s" % (reason, (sec.get('text') or '')[:40]))
    click_rect(sec, "section")
    time.sleep(3)
    click_video_center("play-after-switch")
    time.sleep(2)

    cur = get_current_section()
    if cur is None:
        log("  [warn] 切换后读不到当前小节")
        return False
    if cur['finish']:
        log("  [warn] 切换后这一节仍是已完成：%s" % cur['text'][:40])
        return False
    log("  [ok] 当前小节未完成：%s" % cur['text'][:40])
    return True


def goto_next_unfinished():
    """切到下一个未完成小节。找不到就滚目录再找。"""
    cur = get_current_section()
    avoid = cur['text'] if cur else None

    for attempt in range(3):
        nxt = pick_next_unfinished(avoid)
        if nxt:
            return switch_to_section(nxt, reason="下一未完成")
        log("  第 %d 次找不到，滚动目录" % (attempt + 1))
        scroll_catalog()
        time.sleep(1)

    log("  >>> 找不到未完成小节 —— 可能已全部完成，或需人工检查")
    return False


# ============================================================
# 弹题处理
# ============================================================
QUIZ_JS = r"""
const dlg = document.querySelector('.dialog-test');
if (!dlg) return null;                       // ← 防 null

const opts = [];
dlg.querySelectorAll('.topic-item').forEach((li, i) => {
  const r = li.getBoundingClientRect();
  opts.push({i: i,
             text: (li.innerText || '').trim().replace(/\n/g, ' ').slice(0, 60),
             x: r.x, y: r.y, w: r.width, h: r.height});
});

const titleEl = dlg.querySelector('.topic-title');
const closeBtn = Array.from(dlg.querySelectorAll('button, span, a, div'))
  .filter(e => (e.innerText || '').trim() === '关闭')
  .map(e => { const r = e.getBoundingClientRect();
              return {x: r.x, y: r.y, w: r.width, h: r.height}; })
  .filter(r => r.w > 0 && r.h > 0)[0] || null;

return {
  title: titleEl ? titleEl.innerText.trim() : '',
  options: opts,
  closeRect: closeBtn
};
"""

TIP_JS = r"""
const KEY = '未做答的弹题不能关闭';
const hits = Array.from(document.querySelectorAll('div, section, article'))
  .filter((e) => {
    if (!(e.innerText || '').includes(KEY)) return false;
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return r.width > 50 && r.height > 30
        && cs.display !== 'none' && cs.visibility !== 'hidden'
        && parseFloat(cs.opacity) > 0.1;
  });
if (!hits.length) return null;
hits.sort((a, b) => {
  const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
  return ra.width * ra.height - rb.width * rb.height;
});
const tip = hits[0];
const tr = tip.getBoundingClientRect();
const x = Array.from(tip.querySelectorAll('i, span, button, div, a'))
  .map((e) => ({r: e.getBoundingClientRect(),
                t: (e.innerText || '').trim(),
                cls: (e.className || '').toString()}))
  .filter((o) => o.r.width >= 8 && o.r.height >= 8
              && (['×','✕','x','X','✖','╳'].includes(o.t) || /close|cls/i.test(o.cls)))
  .sort((a, b) => (a.r.y - b.r.y) || (b.r.x - a.r.x))[0];
return {
  tipRect: {x: tr.x, y: tr.y, w: tr.width, h: tr.height},
  closeRect: x ? {x: x.r.x, y: x.r.y, w: x.r.width, h: x.r.height} : null,
  tipText: (tip.innerText || '').slice(0, 120)
};
"""


def read_quiz():
    return js(QUIZ_JS)


def read_tip():
    return js(TIP_JS)


def click_all_options(options):
    n = 0
    for opt in options:
        if opt['w'] > 0 and opt['h'] > 0:
            click_rect(opt, "opt%d" % opt['i'])
            n += 1
            time.sleep(0.45)
    return n


def click_close(close_rect):
    if not close_rect:
        log("  [warn] 找不到「关闭」按钮")
        return False
    click_rect(close_rect, "close")
    time.sleep(1.2)
    return True


def handle_quiz():
    q = read_quiz()
    if q is None:
        log("  [skip] 弹窗已消失")
        return True

    log("题目:", q['title'][:50], "| 选项数:", len(q['options']))

    # ⚠️ 多选判定只看题干（全文包含题干，扫全文只会误判）
    is_multi = '多选' in q['title']

    # ⚠️ options 为空 → 绝不点关闭（否则触发「未做答不能关闭」死循环）
    if not q['options']:
        log("  [error] 读不到选项 —— 选择器可能失效，跳过，不点关闭")
        return True

    if is_multi:
        log("  多选：点了 %d 个" % click_all_options(q['options']))
    else:
        click_rect(q['options'][0], "opt0")
        time.sleep(0.6)

    time.sleep(1.0)
    screenshot(tag="after-answer")

    click_close(q['closeRect'])

    # ---- 检查「未做答不能关闭」提示框 ----
    tip = read_tip()
    if tip is not None:
        log("  [!] 出现提示框：%s" % (tip.get('tipText') or '').replace('\n', ' ')[:60])
        if tip['closeRect']:
            click_rect(tip['closeRect'], "tip-X")
        else:
            log("  [warn] 提示框内找不到 X，改点其外侧")
            click_video_center("outside-tip")
        time.sleep(0.8)

        q2 = read_quiz()
        if q2 is None:
            log("  [ok] 弹窗已关闭")
            return True

        if q2['options']:
            if '多选' in q2['title']:
                click_all_options(q2['options'])
            else:
                click_rect(q2['options'][0], "opt0")
            time.sleep(1.0)
            screenshot(tag="retry-answer")

        click_close(q2['closeRect'])

        if read_tip() is not None:
            log("  [error] 提示框仍在 —— 需人工介入，本轮结束")
            return True

    # ---- 关掉后若暂停，点视频中央恢复 ----
    v = js("const v=document.querySelector('video'); return v?{paused:!!v.paused}:null;")
    if v and v['paused']:
        click_video_center("resume-after-quiz")
        time.sleep(1.5)

    screenshot(tag="after-close")
    log("  [ok] 弹题处理完毕")
    return True


# ============================================================
# 启动自检（换机器必看）
# ============================================================
if SELF_CHECK:
    s = vp_size()
    vr = video_rect()
    cat = read_catalog()
    c = cat.get('catalog')
    log("=" * 56)
    log("几何自检")
    log("  视口        : %sx%s" % (s['w'], s['h']))
    log("  video 区域  : %s" % (vr,))
    log("  目录盒      : %s" % (c,))
    log("  识别到小节  : %d 个（丢弃 %d 个）" % (len(cat.get('items', [])), cat.get('droppedCount', 0)))
    cur = get_current_section()
    log("  当前高亮小节: %s" % ((cur or {}).get('text', '(未识别到)')[:50],))
    if not vr:
        log("  [!!] 没找到 <video> —— 页面可能还没加载完，或不在学习页")
    if not c:
        log("  [!!] 没识别到目录 —— 调小 MIN_SECTION_W / MIN_SECTION_H，或调大 CATALOG_X_TOLERANCE")
    log("=" * 56)


# ============================================================
# 主循环
# ============================================================
start = time.time()
rounds = 0

while time.time() - start < RUN_SECONDS:
    rounds += 1
    elapsed = round(time.time() - start)

    state = js(r"""
    const v = document.querySelector('video');
    if (!v) return {err: 'no video'};
    const dlg = document.querySelector('.dialog-test');
    let open = false;
    if (dlg) {
      const r = dlg.getBoundingClientRect();
      const cs = getComputedStyle(dlg);
      open = r.width > 100 && r.height > 100
          && cs.display !== 'none' && cs.visibility !== 'hidden'
          && parseFloat(cs.opacity) > 0.1;
    }
    return {ct: v.currentTime, dur: v.duration,
            paused: !!v.paused, ended: !!v.ended, dialogOpen: open};
    """)

    if state.get('err'):
        log(elapsed, state)
        break

    ct = state['ct'] if state['ct'] is not None else -1
    dur = state['dur'] if state['dur'] is not None else -1
    log("r%d %ss  ct=%.0f/%.0f paused=%s ended=%s dlg=%s" % (
        rounds, elapsed, ct, dur, state['paused'], state['ended'], state['dialogOpen']))

    # ---- 1. 弹题优先 ----
    if state['dialogOpen']:
        log(">>> 弹题出现")
        handle_quiz()
        time.sleep(2)
        continue

    # ---- 2. 目录校验：当前小节必须「未完成」 ----
    cur = get_current_section()
    if cur is None:
        log("  [warn] 读不到当前高亮小节，等下一轮")
        time.sleep(LOOP_SLEEP)
        continue

    log("  当前: %s | done=%s progress=%s" % (
        cur['text'][:36], cur['finish'], cur['progress']))

    if cur['finish']:
        log(">>> 当前小节已完成，切到下一个未完成小节")
        goto_next_unfinished()
        time.sleep(2)
        continue

    # ---- 3. 未完成 → 保证在播 ----
    if state['ended']:
        log("  视频已结束，等目录打勾…")      # 不点中央（可能是重播按钮）
    elif state['paused']:
        log("  视频暂停，点画面中央恢复")
        click_video_center("resume")
        time.sleep(2)

    time.sleep(LOOP_SLEEP)

log("=== 本轮结束：%d 轮 / %s 秒 ===" % (rounds, round(time.time() - start)))
# ===== 复制结束 =====
