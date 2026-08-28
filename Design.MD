---
name: "微博 Design.MD"
version: "1.0.0"
last_updated: "2026-07-01"
---

# 微博 Design.MD

## Colors

品牌色以 `#FF8200` 为唯一锚点，通过透明度衍生 5 个色阶；灰度系统按语义分为文字、边框、背景三类；功能色仅 3 类。所有变量名统一，无 `-dark` 后缀。

```yaml
colors:
  brand:
    primary:
      light: "#FF8200"
      dark:  "#EA8011"

  brand-opacity:
    brand-80p:
      light: "rgba(255, 130, 0, 0.80)"
      dark:  "#F49A3D"
    brand-60p:
      light: "rgba(255, 130, 0, 0.60)"
      dark:  "#DC7C18"
    brand-40p:
      light: "rgba(255, 130, 0, 0.40)"
      dark:  "#9F6221"
    brand-20p:
      light: "rgba(255, 130, 0, 0.20)"
      dark:  "#674827"
    brand-10p:
      light: "rgba(255, 130, 0, 0.10)"
      dark:  "#483827"

  interaction:
    hover:
      light: "rgba(255, 255, 255, 0.10)"
      dark:  "rgba(255, 255, 255, 0.12)"
    pressed:
      light: "rgba(0, 0, 0, 0.10)"
      dark:  "rgba(0, 0, 0, 0.20)"
    disabled:
      light: "0.40"
      dark:  "0.30"

  text:
    primary:
      light: "#333333"
      dark:  "#D3D3D3"
    secondary:
      light: "#636363"
      dark:  "#999999"
    tertiary:
      light: "#939393"
      dark:  "#888888"
    disabled:
      light: "#BDBDBD"
      dark:  "#3A3A3A"
    inverse: "#FFFFFF"

  border:
    light:
      light: "#EEEEEE"
      dark:  "#333333"
    medium:
      light: "#E6E6E6"
      dark:  "#2A2A2A"
    strong:
      light: "#CCCCCC"
      dark:  "#444444"

  bg:
    page:
      light: "#F5F5F5"
      dark:  "#151515"
    card:
      light: "#FFFFFF"
      dark:  "#1E1E1E"
    surface:
      light: "#F8F8F8"
      dark:  "#181818"

  functional:
    warning:
      light: "#E14123"
      dark:  "#D33635"
    success:
      light: "#10B524"
      dark:  "#2AA045"
    link:
      light: "#507DAF"
      dark:  "#7691B9"
```

---

## Typography

系统字体栈作为 UI 字体，覆盖所有平台。共 14 个排版级别，按语义分为 5 类：

- **Display**, `display/large` (28px): 唯一使用 28px 的级别。
- **Headlines**, `headline/large` 至 `headline/small` (22px → 17px): 仅有的 4 个使用 Medium 500 字重的 Token。
- **Body**, `body/large` 至 `body/small` (16px → 14px): 多行正文，行高较宽松；Regular 400。
- **Labels**, `label/large` 至 `label/small` (14px → 12px): 单行功能性文字；Regular 400。
- **Captions**, `caption/large` 至 `caption/xsmall` (13px → 10px): 辅助元信息；`small` 和 `xsmall` 使用 0.2px 字间距。

`body/large` 和 `caption/medium` 覆盖大部分场景。字重 3 档：400（默认）、500（仅限 Headlines 和 Display）、700（仅限数据数字）。行高 ≤ 2 行取 `size × 1.4`，> 2 行取 `size × 1.5`，向上取偶。深色模式下仅颜色切换。

```yaml
typography:
  fontFamily:
    ui: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif"
    mono: "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', 'Courier New', monospace"

  display/large:     { size: 28, weight: 500, lineHeight: 1.43, letterSpacing: 0 }
  headline/large:    { size: 22, weight: 500, lineHeight: 1.45, letterSpacing: 0 }
  headline/medium:   { size: 20, weight: 500, lineHeight: 1.4,  letterSpacing: 0 }
  headline/small:    { size: 17, weight: 500, lineHeight: 1.41, letterSpacing: 0 }
  body/large:        { size: 16, weight: 400, lineHeight: 1.5,  letterSpacing: 0 }
  body/medium:       { size: 15, weight: 400, lineHeight: 1.47, letterSpacing: 0 }
  body/small:        { size: 14, weight: 400, lineHeight: 1.43, letterSpacing: 0 }
  label/large:       { size: 14, weight: 400, lineHeight: 1.43, letterSpacing: 0 }
  label/medium:      { size: 13, weight: 400, lineHeight: 1.38, letterSpacing: 0 }
  label/small:       { size: 12, weight: 400, lineHeight: 1.5,  letterSpacing: 0 }
  caption/large:     { size: 13, weight: 400, lineHeight: 1.38, letterSpacing: 0 }
  caption/medium:    { size: 12, weight: 400, lineHeight: 1.5,  letterSpacing: 0 }
  caption/small:     { size: 11, weight: 400, lineHeight: 1.45, letterSpacing: 0.2 }
  caption/xsmall:    { size: 10, weight: 400, lineHeight: 1.4,  letterSpacing: 0.2 }
```

---

## Spacing

基于 2px 网格，10 档间距：

```yaml
spacing:
  xs:   2px
  sm:   4px
  md:   6px
  lg:   8px
  xl:  10px
  2xl: 12px
  3xl: 14px
  4xl: 16px
  5xl: 20px
  6xl: 24px
```

---

## Radius

共 7 档：

```yaml
radius:
  none:    0px
  xs:      2px
  sm:      4px
  md:      6px
  lg:      8px
  xl:     12px
  full:   50%
```

---

## Iconography

全局线性风格，底部导航选中态为实心：

```yaml
iconography:
  style: linear
  bottomNav-selected: filled
  strokeWidth: 1.6px
  lineCap: round
  lineJoin: round

  sizes:
    xs: 12px
    sm: 18px
    md: 24px
    lg: 30px
    xl: 40px

  color:
    default:   text.secondary
    active:    text.primary
    bottomNav: text.primary
    inverse:   text.inverse
```

---

## Components

### Card

```yaml
card:
  padding: 3xl 3xl 0 3xl
  radius: none
  bg: bg.card
  divider: 0.5px border.medium
  direction: vertical

  header:
    direction: horizontal
    align: center
    justify: space-between
    gap: lg
    avatar:
      size: 42px
      radius: full
      v-badge: { size: 14px, color: yellow-400 }
    text-group:
      direction: vertical
      gap: xs
      name: { font: body/large, color: text.primary }
      meta: { font: caption/medium, color: text.tertiary }
    more: { icon: xs }

  risk-tag:
    bg: blue-100/80
    radius: xl
    padding: 4px 10px 4px 14px
    icon: { size: xs }
    text: { font: caption/medium }
    gap: sm

  body:
    font: body/large
    lineHeight: 1.5
    color: text.primary
    topic: { color: functional.link }
    mention: { color: functional.link }

  media:
    single-image:
      ratio: { square: "1:1", horizontal: 267×197, vertical: 267×367 }
      width: 267px
      radius: md
    multi-image:
      grid: [2, 3, 4, 5, 6, 7, 8, 9]
      max: 18
      gap: sm
      radius: md
    video:
      ratio: { horizontal: 402×226, vertical: 267×357 }
      radius: md
    badge:
      position: overlay
      optional: true

  attachment:
    gum-card:
      bg: bg.surface
      radius: xs
      padding: lg
      gap: xl
      thumbnail: { size: 36px, radius: xs }
      title: { font: body/small, color: text.primary }
      button:
        size: 56×24
        radius: full
        font: label/small
        color: functional.link
        outline: functional.link

  footer:
    height: 44px
    direction: horizontal
    justify: space-evenly
    action:
      icon: { size: sm }
      count: { font: caption/medium, color: text.primary }
      gap: md
```

### Button

```yaml
button:
  gradient:
    default: { from: "#FF8200", to: "#FFBC33" }
    pressed: { from: "#EB7922", to: "#EFB234" }
  secondary:
    default: "#F6F6F6"
    pressed: "#EAEAEA"
  tertiary:
    outline-gray: "rgba(147, 147, 147, 0.40)"
    bg-pressed: "rgba(255, 130, 0, 0.05)"
    bg-pressed-gray: "rgba(147, 147, 147, 0.05)"

  sizes:
    large:
      min-width: 120px
      min-height: 40px
      padding: 16px × 8px
      font: label/large
      gap: 4px
    medium:
      min-width: 60px
      min-height: 28px
      padding: 12px × 4px
      font: label/medium
      gap: 2px
    small:
      min-width: 40px
      min-height: 20px
      padding: 10px × 2px
      font: caption/xsmall
      gap: 2px

  shape:
    pill: 50%
    rounded:
      large:  lg
      medium: sm
      small:  xs

  hierarchy:
    primary:
      style: gradient
      bg: button.gradient.default
      text: text.inverse
      icon: text.inverse
    secondary:
      style: filled
      bg: button.secondary.default
      text: text.secondary
      icon: text.secondary
    tertiary:
      style: outlined
      outline: 0.5px brand.primary
      bg: transparent
      text: brand.primary
      icon: brand.primary

  states:
    default: { opacity: 1.0 }
    pressed:
      primary:
        bg: button.gradient.pressed
        opacity: 0.75
      secondary:
        bg: button.secondary.pressed
        opacity: 0.75
      tertiary:
        bg: button.tertiary.bg-pressed
        opacity: 1.0
    disabled:
      opacity: 0.50

  icon:
    with-text:
      size: 16px
      gap: 2px
    icon-only:
      size: 16px
      padding: 8px

  follow:
    followed:
      secondary:
        style: filled
        bg: button.secondary.default
        text: text.secondary
        icon: checkmark
      tertiary:
        style: outlined
        outline: 0.5px button.tertiary.outline-gray
        bg: transparent
        text: text.secondary
        icon: checkmark
```

### Dialog

```yaml
dialog:
  width: 256px
  radius: xl
  bg: bg.card
  direction: vertical

  content:
    padding-x: 3xl
    padding-top: 5xl
    padding-bottom: 3xl
    gap: xl
    title:
      font: body/large
      color: text.primary
      align: center
    body:
      font: body/small
      color: text.primary
    image:
      height: 176px
      bg: bg.page
      radius: none
    checkbox:
      size: 16px
      radius: 3px
      border: 0.6px border.light
      checked: brand.primary
      label:
        font: caption/medium
        color: text.tertiary
    input:
      padding: 6px 10px 6px 28px
      border: 0.5px border.medium
      placeholder:
        font: body/small
        color: text.disabled

  footer:
    padding: 0
    divider-top: 0.5px border.medium
    direction: horizontal
    button:
      flex: 1
      padding: 10px 12px
      font: body/large
      cancel: { color: text.secondary }
      confirm: { color: brand.primary }
      divider-between: 0.5px border.medium
```

### Input

```yaml
input:
  width: 100%
  max-height: 160px
  padding: 3xl
  radius: lg
  direction: horizontal
  justify: space-between
  align: start

  text:
    font: body/large
    color: text.primary
    flex: 1

  placeholder:
    color: text.disabled

  clear:
    icon: { size: 16px }
    color: text.tertiary

  variants:
    default: { bg: bg.card }
    filled:  { bg: bg.page }
```

### NavBar

```yaml
navbar:
  height: 44px
  bg: bg.card
  shadow-bottom: 0.5px border.medium
  padding-x: 3xl

  left:
    back: { icon: lg }
    text: { font: body/large, color: text.primary }

  center:
    title: { font: body/large, color: text.primary, align: center, maxLines: 1 }
    title-subtitle:
      title: { font: body/large, color: text.primary }
      subtitle: { font: body/small, color: text.tertiary }

  right:
    icons: { icon: lg, gap: lg, max: 3 }
    text: { font: body/large, color: text.primary }
    button:
      size: 56×32 or 64×32
      shape: rounded
      font: label/large
      style: gradient

  search:
    height: 48px
    padding: 12px 3xl 2px
    bar:
      height: 40px
      radius: 20px
      outline: 1px border.medium
      placeholder: { font: body/small, color: text.tertiary }
      action: { font: label/large, color: brand.primary }
```


### TabBar

```yaml
tabbar:
  height: 48px
  bg: bg.card
  shadow-top: 0.5px border.medium

  tab:
    count: 5
    direction: vertical
    align: center
    icon:
      size: lg
      selected: filled
      unselected: linear
      color: text.primary
    label:
      font: caption/xsmall
      color: text.primary
```

### Avatar

```yaml
avatar:
  shape: full
  border: 1px rgba(0, 0, 0, 0.05)

  v-badge:
    scale: proportional
    min-size: 10×10
    color: yellow-400
    border: 1px bg.card
```


### constraints:  

  tabbar:
    "底部导航 TabBar 的图标和文字颜色必须严格遵循规范中的 color 定义，禁止自定义或自行衍生新的颜色值。"

  icon:
    "禁止使用 Emoji 符号替代图标占位。所有图标必须使用线性路径图标，未就绪的图标使用占位线框而非 Emoji。"

  color:
    "配色约束的核心是避免脏色。所有小面积 UI 色块必须使用干净、明确、通透的色相；禁止使用发灰、发旧、发闷、偏泥土感的综合色。尤其禁止用于 tag、角标、榜单头图和装饰色块。"

  fallback:
    "未定义场景下，宁可退回干净中性色或品牌浅底（brand-10p / brand-20p），禁止自行创造'综合色''脏金色''灰橙色''棕黄色'之类的过渡色。"

### Elevation:

```yaml
  strategy: flat
  rule: "不使用投影。层级通过背景色和 0.5px 分割线区分。"
  shadows: none
  
