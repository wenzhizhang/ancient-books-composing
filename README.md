# 古籍排版工具 v0.0.2
根据包含特定标记的输入文本自动进行古籍排版，双行夹注，可多色排版

## 输入文本示例

```
#章节名称
章节正文内容示例【行内批注】
```

## 标记说明
- `#` 为章节名称标记，表示一个章节的开始
- `【】`为批注标记，`【】`包围的内容为批注文本

## 程序参数说明
- `chapter_font_paths`：章节名称字体文件路径列表
- `chapter_font_size`：章节名称字体大小
- `chapter_font_color`：章节名称字体颜色
- `content_font_paths`：正文字体文件路径列表
- `content_font_size`：正文字体大小
- `content_font_color`：正文字体颜色
- `annotation_font_paths`：批注字体文件路径列表
- `annotation_font_size`：批注字体大小
- `annotation_font_color`：批注字体颜色
- `output_dir`：图片输出路径
- `width`：图片宽度（像素）
- `height`：图片高度（像素）
- `line_count`：单页行数
- `line_space`：行间距
- `annotation_line_space`：双行夹注行间距
- `margin`：筒子页页边距(上, 下, 左, 右)
- `border`：文本框线条宽度
- `border_color`：文本框颜色
- `background`：背景图片路径
- `line_sep`：是否绘制行分隔线标志符，默认为`True`
- `line_sep_color`：行分隔线颜色
- `line_sep_width`：行分隔线宽度
- `with_noise`：是否添加噪点标志符，默认为`False`
- `noise_level`：噪点等级
- `older`：是否添加做旧效果标志符，默认为`False` 
- `bg_color`：背景颜色

## 输出图片示例

![alt text](第一頁.png)
