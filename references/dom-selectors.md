# 智慧树 DOM 结构与踩坑记录

## 页面结构

学习页 URL：`https://studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=...`

布局：
- 左侧大区域：视频播放器（`<video>` 元素）
- 右侧目录栏：章节列表，每个小节是一个 `<li>`
- 弹题弹窗：覆盖在视频上方，fixed 定位

## video 元素

```js
const v = document.querySelector('video');
// v.currentTime  当前播放秒数
// v.duration     总时长
// v.paused       是否暂停
// v.ended        是否播放结束
```

## 弹题弹窗 `.dialog-test`

出现时机：视频播放过程中随机弹出，不影响作业成绩。

结构：
```
.dialog-test
├── .topic-title        题干（含【判断题】/【单选题】/【多选题】）
├── ul > li.topic-item  选项列表
│   ├── A. xxx
│   ├── B. xxx
│   └── ...
└── button "关闭"       底部关闭按钮
```

作答后会在题干左侧显示"正确"（绿勾）或"错误"（红叉），并显示"正确答案：X"。

## 右侧目录 li 结构

每个小节 li：
```
li (蓝色背景=当前高亮)
├── 编号文字（如 "5.2.5"）
├── 标题文字（如 "信息化作战平台发展对现代战争的影响"）
├── 时长（如 "00:05:29"）
└── 最右端状态图标：
    ├── b.time_icofinish   蓝色勾（已完成）
    ├── svg + span.progress-num  蓝色进度环 + "XX%"（进行中）
    └── 空（未开始）
```

章节标题行（如 "5.2 信息化作战平台"）不含时长，用 `/00:\d{2}:\d{2}/` 正则排除。

## 弹窗可见性判定

**不要用** `offsetParent !== null`，因为 `.dialog-test` 是 fixed 定位，offsetParent 恒为 null。

正确做法：
```js
const r = dlg.getBoundingClientRect();
const cs = getComputedStyle(dlg);
const open = r.width>100 && r.height>100
          && cs.display!=='none'
          && cs.visibility!=='hidden'
          && parseFloat(cs.opacity)>0.1;
```

## 多选题"未做答不能关闭"陷阱

多选题如果点选项没选中（坐标点偏了），直接点关闭会弹出一个小提示框：
- 标题"提示"
- 内容"未做答的弹题不能关闭"
- 右上角有 X 按钮

处理流程：
1. 先点提示框右上角 X 关闭提示
2. 重新读取所有选项矩形
3. 依次坐标点击每个选项（确保选中）
4. 截图确认所有选项都打勾
5. 再点"关闭"按钮

### 怎么检测这个提示框（选择器未固定，用启发式）

提示框的 class 名不稳定，用**文本 + 可见性**来定位，并**取面积最小的那层**
（否则会命中它的祖先容器，导致 X 按钮找不到）：

```js
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
  return ra.width * ra.height - rb.width * rb.height;   // 面积从小到大
});
const tip = hits[0];
```

**X 按钮也靠启发式找**：在提示框内找文本为 `×` / `✕` / `x` / `✖`，
或 class 含 `close` 的元素，**按"最上 + 最右"排序取第一个**：

```js
const x = Array.from(tip.querySelectorAll('i, span, button, div, a'))
  .map((e) => ({ e, t: (e.innerText || '').trim(),
                 cls: (e.className || '').toString(),
                 r: e.getBoundingClientRect() }))
  .filter((o) => o.r.width >= 8 && o.r.height >= 8
              && (['×','✕','x','X','✖','╳'].includes(o.t) || /close|cls/i.test(o.cls)))
  .sort((a, b) => (a.r.y - b.r.y) || (b.r.x - a.r.x))[0];
```

> ⚠️ **这是启发式，不是稳定选择器。首次在某门课上跑时，先人工看一眼 X 的位置对不对。**
> 若找不到 X，退而求其次：点提示框外区域，或直接截图报警让人介入。

### 防死循环的硬规则

| 规则 | 原因 |
|---|---|
| **`options` 为空时绝不点「关闭」** | 必然触发这个提示框，从而进入死循环 |
| **重选一次仍关不掉 → 报错退出本轮** | 不要无限重试，会卡死 |
| **处理完弹题用 `continue` 而不是 `break`** | `break` 会退出整个值守循环 |

## 坐标点击注意事项

- `bu.click_xy(nx, ny)` 的 nx/ny 范围是 0-1000，代表视口宽/高的百分比 * 10
- 像素坐标换算：`归一化 = 像素 / 视口像素 * 1000`
- 点击元素中心：先 `getBoundingClientRect()` 拿到 `{x, y, width, height}`，中心点 = `(x+width/2, y+height/2)`
- 点击视频中央开始播放：固定用 `bu.click_xy(500, 500)`
- 滚动右侧目录：`bu.scroll(842, 575, "down", amount=2)`（842,575 是右侧目录区域的归一化坐标）

## 常见异常

| 现象 | 原因 | 处理 |
|---|---|---|
| `BU_COORDINATE_SPACE` | bu.scroll/click_xy 传了像素值 | 归一化到 0-1000 |
| `ValueError: y=1017 is outside 0-1000` | 元素在视口底部，归一化后超 1000 | `min(999, ny)` 截断，或先滚动目录 |
| `NameError: name 'x' is not defined` | Python 字典 `{x: ...}` 中 x 被当变量 | 写 `{'x': ...}` 字符串键 |
| 点选项没反应 | 坐标点到 LI 外部 | 必须先 getBoundingClientRect 再点中心 |
| 弹题关不掉 | 多选题没选上 | 见上面"未做答不能关闭"陷阱 |
| 切换小节后视频没自动播 | 新小节需要手动开始 | 点画面中央 (500,500) |
| 找不到下一节 | 下一节在视口外 | `bu.scroll(842,575,"down",amount=2)` 滚动目录 |
