"""
智慧树页面只读探测脚本 —— 换电脑 / 换分辨率后先跑这个。

============================================================
用途
============================================================
不同电脑的分辨率、窗口大小、浏览器缩放都不一样。
本脚本 **不点任何鼠标、不做任何修改**，只把页面几何信息打印出来，
用来确认：

  1. 能不能找到 <video>         → 决定「点画面中央」的坐标对不对
  2. 能不能识别出右侧目录        → 决定切换小节的逻辑能不能跑
  3. 当前高亮的是哪一节          → 决定「未完成校验」有没有读数
  4. 弹题弹窗 / 提示框的结构      → 决定选择器还灵不灵

**跑通这个，再跑 watch_loop.py。**

============================================================
红线（同样适用）
============================================================
· 只读：全部 js(...) 调用都是 querySelector / getBoundingClientRect / innerText
· 不点鼠标、不滚动、不截图
· 不发起任何网络请求

============================================================
用法
============================================================
把 "===== 复制开始 =====" 到 "===== 复制结束 =====" 之间的代码
复制到 computer_use_tool(plane="bu") 的 code 中运行。
"""

# ===== 复制开始 =====
# ============================================================
# 环境适配层  ⚠️ 移植时【只改这一段】（和 watch_loop.py 保持一致）
# ============================================================
try:
    import seed_browser_use as _rt
except ImportError:                     # 换环境时这里会失败 —— 正常
    _rt = None


def js(code):
    """在页面里执行只读 JS，返回 JSON 可序列化的值。"""
    if _rt is None:
        raise RuntimeError("请先在「环境适配层」里接入你自己环境的 js()")
    return _rt.js(code)


# 其余三个原语 probe.py 用不到（它只读，不点鼠标）
# 见 references/porting.md

bu = _rt

LOG = []


def log(*a):
    line = " ".join(str(x) for x in a)
    LOG.append(line)
    print(line, flush=True)


log("=" * 60)
log("智慧树页面只读探测")
log("=" * 60)

# ---------- 1. 视口 ----------
s = js("return {w: window.innerWidth, h: window.innerHeight, dpr: devicePixelRatio};")
log("")
log("【1】视口")
log("  innerWidth  = %s" % s.get('w'))
log("  innerHeight = %s" % s.get('h'))
log("  devicePixelRatio = %s   （>1 说明系统有缩放）" % s.get('dpr'))
log("  → 归一化坐标 = 像素 / 视口 × 1000，所以视口大小不影响坐标")

# ---------- 2. video ----------
log("")
log("【2】视频区域")
v = js(r"""
const v = document.querySelector('video');
if (!v) return null;
const r = v.getBoundingClientRect();
return {x: r.x, y: r.y, w: r.width, h: r.height,
        currentTime: v.currentTime, duration: v.duration,
        paused: !!v.paused, ended: !!v.ended};
""")
if v:
    cx = v['x'] + v['w'] / 2
    cy = v['y'] + v['h'] / 2
    log("  rect = x=%.0f y=%.0f w=%.0f h=%.0f" % (v['x'], v['y'], v['w'], v['h']))
    log("  中心像素 = (%.0f, %.0f)" % (cx, cy))
    log("  中心归一化 = (%d, %d)" % (round(cx / s['w'] * 1000), round(cy / s['h'] * 1000)))
    log("  currentTime=%.1f  duration=%.0f  paused=%s  ended=%s"
        % (v['currentTime'], v['duration'], v['paused'], v['ended']))
    log("  → 「点画面中央」会用这个坐标，不是写死的 (500,500)")
else:
    log("  [!!] 页面里没有 <video>")
    log("       可能原因：还没进入学习页 / 页面没加载完 / 视频在 iframe 里")

# ---------- 3. 右侧目录 ----------
log("")
log("【3】右侧目录（小节列表）")
cat = js(r"""
const vw = window.innerWidth, vh = window.innerHeight;
const raw = [];
document.querySelectorAll('li').forEach((li) => {
  const t = (li.innerText || '').trim();
  if (!t) return;
  const r = li.getBoundingClientRect();
  if (!/00:\d{2}:\d{2}/.test(t)) return;
  const cs = getComputedStyle(li);
  const bg = cs.backgroundColor;
  raw.push({
    text: t.replace(/\n/g, ' | ').slice(0, 46),
    w: Math.round(r.width), h: Math.round(r.height),
    x: Math.round(r.x), y: Math.round(r.y),
    finish: !!li.querySelector('.time_icofinish'),
    progress: !!li.querySelector('.progress-num'),
    highlighted: !!(bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'rgb(255, 255, 255)'),
    bg: bg
  });
});
const xs = raw.map(o => o.x).sort((a, b) => a - b);
const medianX = xs.length ? xs[Math.floor(xs.length / 2)] : null;
return {raw: raw, medianX: medianX, vw: vw, vh: vh};
""")

raw = cat.get('raw', [])
log("  含时长的 li 共 %d 个" % len(raw))
if raw:
    log("  x 坐标中位数 = %s   （用于自动判断哪一栏是目录）" % cat.get('medianX'))
    log("")
    log("  %-46s %6s %6s %6s  %s" % ("文本", "x", "y", "w", "状态"))
    log("  " + "-" * 84)
    for o in raw[:25]:
        flags = []
        if o['highlighted']:
            flags.append("★当前")
        if o['finish']:
            flags.append("已完成")
        if o['progress']:
            flags.append("进行中")
        log("  %-46s %6d %6d %6d  %s" % (o['text'], o['x'], o['y'], o['w'], " ".join(flags) or "-"))
    if len(raw) > 25:
        log("  ... 还有 %d 个" % (len(raw) - 25))
else:
    log("  [!!] 一个都没识别到")
    log("       可能原因：目录在 iframe 里 / 时长格式不是 00:00:00 / 页面没加载完")

# 当前高亮
cur = [o for o in raw if o.get('highlighted')]
log("")
log("  当前高亮小节：%s" % (cur[0]['text'] if cur else "(未识别到)"))
if not cur:
    log("  [!!] 「未完成校验」需要这个读数 —— 识别不到就无法判断当前播的是哪节")

# 未完成候选
cands = [o for o in raw if not o['finish'] and not o['progress']]
log("  未完成的候选小节：%d 个" % len(cands))
for o in cands[:5]:
    log("    · %s" % o['text'])

# ---------- 4. 弹题弹窗 ----------
log("")
log("【4】弹题弹窗")
dlg = js(r"""
const dlg = document.querySelector('.dialog-test');
if (!dlg) return {present: false};
const r = dlg.getBoundingClientRect();
const cs = getComputedStyle(dlg);
const titleEl = dlg.querySelector('.topic-title');
const opts = [];
dlg.querySelectorAll('.topic-item').forEach((li) => {
  const rr = li.getBoundingClientRect();
  opts.push({text: (li.innerText || '').trim().replace(/\n/g, ' ').slice(0, 40),
             w: Math.round(rr.width), h: Math.round(rr.height)});
});
const closeBtn = Array.from(dlg.querySelectorAll('button, span, a, div'))
  .filter(e => (e.innerText || '').trim() === '关闭');
return {
  present: true,
  w: Math.round(r.width), h: Math.round(r.height),
  visible: r.width > 100 && r.height > 100 && cs.display !== 'none'
           && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.1,
  title: titleEl ? titleEl.innerText.trim().slice(0, 60) : '(无 .topic-title)',
  optionCount: opts.length,
  options: opts,
  closeBtnCount: closeBtn.length
};
""")

if not dlg.get('present'):
    log("  .dialog-test 不存在（当前没有弹题）—— 正常")
else:
    log("  存在  w=%s h=%s  可见=%s" % (dlg['w'], dlg['h'], dlg['visible']))
    log("  题干: %s" % dlg['title'])
    log("  选项数: %s   「关闭」按钮数: %s" % (dlg['optionCount'], dlg['closeBtnCount']))
    if dlg['optionCount'] == 0:
        log("  [!!] 选项数为 0 —— .topic-item 选择器可能失效")
    if dlg['closeBtnCount'] == 0:
        log("  [!!] 找不到「关闭」按钮 —— 文案可能变了")

# ---------- 5. 汇总 ----------
log("")
log("=" * 60)
log("结论")
log("=" * 60)
ok = True
if not v:
    log("  ✗ 找不到 <video>")
    ok = False
if not raw:
    log("  ✗ 识别不到目录小节")
    ok = False
if not cur:
    log("  ✗ 识别不到当前高亮小节")
    ok = False
if ok:
    log("  ✓ 关键元素都能识别 —— 可以运行 watch_loop.py")
else:
    log("  ✗ 有元素识别失败 —— 先解决上面的 [!!] 再跑 watch_loop.py")
log("")
log("提示：如果目录识别不全，回到 watch_loop.py 调这三个参数：")
log("  MIN_SECTION_W / MIN_SECTION_H   （判定「是小节」的最小尺寸）")
log("  CATALOG_X_TOLERANCE             （判断哪一栏是目录的 x 容差）")
# ===== 复制结束 =====
