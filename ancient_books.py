import json
import re
from enum import Enum

import math
import os
import random
import shutil
from multiprocessing import Pool
from pprint import pprint

from opencc import OpenCC
from PIL import ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter
from logger import Logger

LOGGER = Logger('ancient-books')
LOGGER.setLevel('INFO')


class TextType(Enum):
    """
    文本类型枚举
    """
    CHAPTER = 'chapter'
    CONTENT = 'content'
    ANNOTATION = 'annotation'


def convert_to_traditional_chinese(lines):
    """
    将简体中文文本转换为繁体中文文本
    :param lines: 待转换的文本列表
    :return: 繁体中文文本
    """
    cc = OpenCC('s2t')
    return [cc.convert(line) for line in lines]


def convert_number_to_chinese(number: int) -> str:
    """
    转换阿拉伯数字为中文数字
    :param number: 待转换的阿拉伯数
    :return: 中文数字
    """
    number_dict = {
        '0': '零',
        '1': '一',
        '2': '二',
        '3': '三',
        '4': '四',
        '5': '五',
        '6': '六',
        '7': '七',
        '8': '八',
        '9': '九'
    }
    number_str = str(number)
    return ''.join([number_dict.get(x) for x in number_str])


def load_font_for_char(char: str, fonts: list, font_size: int):
    """
    从字体列表中为指定字符查找合适的字体
    :param char: 指定字符
    :param fonts: 字体列表
    :param font_size: 字体大小
    :return: 包含该字符的字体
    """
    for font_path in fonts:
        try:
            font = ImageFont.truetype(font_path, font_size)

            if font.getmask(char).getbbox():
                return font
        except Exception as e:
            LOGGER.exception(e)
    return None


def cut(text: str, length: int) -> list:
    """
    按指定长度分割字符串为字符串列表
    :param text: 待分割的字符串
    :param length: 指定字符串长度
    :return: 分割后的字符串列表
    """
    if not text:
        return []
    return [text[i:i + length] for i in range(0, len(text), length)]


def calculate_remain_char_space(remain_height: int, char_height: int, char_space: int,
                                is_annotation=False) -> int:
    """
    计算每行剩余可容纳的字符数量
    :param remain_height: 行剩余像素
    :param char_height: 字符高度
    :param char_space: 字间距
    :param is_annotation: 是否为批注标志符
    :return: 可容纳的字符数量
    """
    if is_annotation:
        return remain_height // (char_height + char_space) * 2
    return remain_height // (char_height + char_space)


def calculate_remain_height(line: list, valid_height: int, chapter_char_height: int,
                            content_char_height: int, content_char_space: int,
                            annotation_char_height: int, annotation_char_space: int) -> int:
    """
    计算每行剩余像素
    :param line: 代表每行文本的字典列表
    :param valid_height: 有效文本框高度
    :param chapter_char_height: 章节名字体高度
    :param content_char_height: 正文字体高度
    :param content_char_space: 正文字间距
    :param annotation_char_height: 批注字体高度
    :param annotation_char_space: 批注字间距
    :return: 行剩余像素
    """
    used_height = 0
    for item in line:
        match item.get('type'):
            case 'chapter':
                used_height += chapter_char_height * len(item.get('value'))
            case 'content':
                used_height += (content_char_height + content_char_space) * len(item.get('value'))
            case 'annotation':
                used_height += (annotation_char_height + annotation_char_space) * math.ceil(
                    len(item.get('value')) / 2)
    return valid_height - used_height


def adjust_font(params):
    """
    根据参数判断当前指定字体大小是否合适，字体超大则自动适配为适合当前参数的最大字体
    :param params: 程序参数字典
    :return: 更新后的参数字典
    """
    chapter_font_size = params.get('chapter_font_size')
    content_font_size = params.get('content_font_size')
    annotation_font_size = params.get('annotation_font_size')
    content_char_space = params.get('content_char_space')
    annotation_char_space = params.get('annotation_char_space')
    margin = params.get('margin')
    border = params.get('border')
    line_space = params.get('line_space')

    text_box_width = params.get('width') - margin[2] - margin[3] - border * 2 - 6
    text_box_height = params.get('height') - margin[0] - margin[1] - border * 2 - 6
    tz_line_count = 2 * params.get('line_count') + 1
    chapter_font_size, chapter_char_width, chapter_char_height = calculate_font_size(
        params.get('chapter_font_paths')[0],
        chapter_font_size,
        text_box_width,
        line_count=tz_line_count,
        line_space=line_space)
    content_font_size, content_char_width, content_char_height = calculate_font_size(
        params.get('content_font_paths')[0],
        content_font_size,
        text_box_width,
        line_count=tz_line_count,
        line_space=line_space)
    annotation_font_size, annotation_char_width, annotation_char_height = calculate_font_size(
        params.get('annotation_font_paths')[0], annotation_font_size, text_box_width,
        line_count=tz_line_count,
        line_space=line_space, is_annotation=True,
        annotation_line_space=params.get('annotation_line_space'))

    if content_char_height < 2 * annotation_char_height:
        content_char_space = 2 * annotation_char_height - content_char_height
    elif content_char_height > 2 * annotation_char_height:
        annotation_char_space = (content_char_height - 2 * annotation_char_height) // 2
    useless_height = text_box_height % (content_char_height + content_char_space)
    if useless_height % 2 == 0:
        inner_margin = (useless_height // 2, useless_height // 2)
    else:
        inner_margin = (useless_height // 2, useless_height - useless_height // 2)
    max_chapter_chars_per_line = text_box_height // chapter_char_height
    max_content_chars_per_line = (text_box_height - inner_margin[0] - inner_margin[1]) // (content_char_height + content_char_space)
    max_annotation_chars_per_line = (text_box_height - inner_margin[0] - inner_margin[1]) // (annotation_char_height + annotation_char_space) * 2
    params['chapter_font_size'] = chapter_font_size
    params['content_font_size'] = content_font_size
    params['annotation_font_size'] = annotation_font_size
    params['chapter_char_width'] = chapter_char_width
    params['chapter_char_height'] = chapter_char_height
    params['content_char_width'] = content_char_width
    params['content_char_height'] = content_char_height
    params['annotation_char_width'] = annotation_char_width
    params['annotation_char_height'] = annotation_char_height
    params['text_box_width'] = text_box_width
    params['text_box_height'] = params.get('height') - margin[0] - margin[1] - border * 2 - 6
    params['content_char_space'] = content_char_space
    params['annotation_char_space'] = annotation_char_space
    params['inner_margin'] = inner_margin
    params['max_chapter_chars_per_line'] = max_chapter_chars_per_line
    params['max_content_chars_per_line'] = max_content_chars_per_line
    params['max_annotation_chars_per_line'] = max_annotation_chars_per_line

    return params


def split_paragraph(chapter_name, paragraph, params):
    """
    将段落文本进一步分割为行
    :param chapter_name: 章节名
    :param paragraph: 文本段落
    :param text_box_height: 文本框高度
    :param content_char_height: 正文字体高度
    :param content_char_space: 正文字间距
    :param annotation_char_height: 批注字体高度
    :param annotation_char_space: 批注字间距
    :return: 分割后的文本行列表
    """
    content_char_height = params.get('content_char_height')
    content_char_space = params.get('content_char_space')
    annotation_char_height = params.get('annotation_char_height')
    annotation_char_space = params.get('annotation_char_space')
    max_content_chars_per_line = params.get('max_content_chars_per_line')
    # 双行夹注
    max_annotation_chars_per_line = params.get('max_annotation_chars_per_line')
    text_box_height = params.get('text_box_height')
    inner_margin = params.get('inner_margin')
    valid_height = text_box_height - inner_margin[0] - inner_margin[1]

    sentences = paragraph.get('texts')
    annotations = paragraph.get('annotations')
    lines = []
    remain_height = valid_height
    for i in range(len(sentences)):
        sentence = sentences[i]
        annotation = None
        if i < len(annotations):
            annotation = annotations[i]
        if remain_height < valid_height:
            remain_content_char_space = remain_height // (content_char_height + content_char_space)
            if remain_content_char_space == 0:
                remain_height = valid_height
            elif remain_content_char_space < len(sentence):
                lines[-1].get('line').append(
                    dict(type=TextType.CONTENT, value=sentence[0:remain_content_char_space]))
                remain_height = valid_height
                sentence = sentence[remain_content_char_space:]
            else:
                lines[-1].get('line').append(dict(type=TextType.CONTENT, value=sentence))
                remain_height -= len(sentence) * (content_char_height + content_char_space)
                sentence = None
        for part in cut(sentence, max_content_chars_per_line):
            lines.append(dict(chapter=chapter_name, line=[dict(type=TextType.CONTENT, value=part)]))
            if len(part) < max_content_chars_per_line:
                remain_height -= len(part) * (content_char_height + content_char_space)
            else:
                remain_height = valid_height
        if annotation:
            if remain_height < valid_height:
                remain_annotation_char_space = remain_height // (
                        annotation_char_height + annotation_char_space) * 2
                if remain_annotation_char_space == 0:
                    remain_height = valid_height
                elif remain_annotation_char_space < len(annotation):
                    lines[-1].get('line').append(dict(type=TextType.ANNOTATION,
                                          value=annotation[0:remain_annotation_char_space]))
                    remain_height = valid_height
                    annotation = annotation[remain_annotation_char_space:]
                else:
                    lines[-1].get('line').append(dict(type=TextType.ANNOTATION, value=annotation))
                    remain_height -= (math.ceil(len(annotation) / 2)) * (
                            annotation_char_height + annotation_char_space)
                    if math.ceil(len(annotation) / 2) % 2 != 0:
                        remain_height -= (annotation_char_height + annotation_char_space)
                    annotation = None
        for part in cut(annotation, max_annotation_chars_per_line):
            lines.append(dict(chapter=chapter_name, line=[dict(type=TextType.ANNOTATION, value=part)]))
            if len(part) < max_annotation_chars_per_line - 1:
                remain_height -= math.ceil(len(part) / 2) * (
                        annotation_char_height + annotation_char_space)
            else:
                remain_height = valid_height
    return lines


def split_text(texts, params):
    """
    对加载的文本进一步分割成行
    :param texts:
    :param params:
    :return:
    """
    text_box_height = params.get('text_box_height')
    chapter_char_height = params.get('chapter_char_height')
    content_char_height = params.get('content_char_height')
    annotation_char_height = params.get('annotation_char_height')
    content_char_space = params.get('content_char_space')
    annotation_char_space = params.get('annotation_char_space')
    line_count = params.get('line_count')
    bookname = params.get('bookname')
    inner_margin = params.get('inner_margin')
    max_chapter_chars_per_line = params.get('max_chapter_chars_per_line')
    max_content_chars_per_line = params.get('max_content_chars_per_line')
    max_annotation_chars_per_line = params.get('max_annotation_chars_per_line')
    valid_height = text_box_height - inner_margin[0] - inner_margin[1]

    text_lines = []
    for chapter in texts:
        # 分割章节名及批注
        chapter_name = chapter.get('chapter')
        chapter_annotation = chapter.get('annotation')
        for chapter_sec in cut(chapter_name, max_chapter_chars_per_line):
            line = [{'type': TextType.CHAPTER, 'value': chapter_sec}]
            text_lines.append(dict(chapter=chapter_name, line=line))
        if chapter_annotation:
            remain_height = calculate_remain_height(text_lines[-1].get('line'), valid_height,
                                                    chapter_char_height, content_char_height,
                                                    content_char_space, annotation_char_height,
                                                    annotation_char_space)
            remain_annotation_char_space = calculate_remain_char_space(remain_height,
                                                                       annotation_char_height,
                                                                       annotation_char_space,
                                                                       is_annotation=True)
            if len(chapter_annotation) <= remain_annotation_char_space:
                text_lines[-1].get('line').append({'type': TextType.ANNOTATION, 'value': chapter_annotation})
            else:
                text_lines[-1].get('line').append(
                    {'type': TextType.ANNOTATION,
                     'value': chapter_annotation[0:remain_annotation_char_space]})
                chapter_annotation = chapter_annotation[remain_annotation_char_space:]
                for annotation_sec in cut(chapter_annotation, max_annotation_chars_per_line):
                    line = [{'type': TextType.ANNOTATION, 'value': annotation_sec}]
                    text_lines.append(dict(chapter=chapter_name, line=line))
        contents = chapter.get('content')
        for paragraph in contents:
            lines = split_paragraph(chapter_name, paragraph, params)
            text_lines.extend(lines)

        if len(text_lines) % line_count != 0:
            text_lines.extend([dict(chapter=chapter_name, line=[]) for _ in range(line_count - (len(text_lines) % line_count))])
            # text_lines.append([dict(type=TextType.CHAPTER, value=f'{bookname} {chapter_name}')])
    return text_lines


def load_text(file_path):
    """
    载入TXT文本文件，提取书名以及包含章节名、正文和批注的章节字典列表
    :param file_path: TXT文本文件路径
    :return: 书名，章节字典列表
    """
    file_path_without_ext, ext = os.path.splitext(file_path)
    bookname = os.path.basename(file_path_without_ext)

    sections = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 跳过空白行
            if not line.strip():
                continue
            # 以#开头的行为章节名
            elif line.startswith('#'):
                chapter_name = line.strip('#')
                # 检查是否有批注
                match = re.search(r'【(.*?)】$', chapter_name)
                if match:
                    annotation = match.group(1)
                    chapter_name = chapter_name[:match.start()].strip()
                else:
                    annotation = None
                sections.append({
                    'chapter': chapter_name,
                    'annotation': annotation,
                    'content': []
                })
            else:
                # 提取正文和批注
                pattern = r'([^【]*)(?:【(.*?)】)*'
                matches = re.findall(pattern, line)
                contents = []
                annotations = []
                for match in matches:
                    content_part = match[0].strip()
                    annotation_part = match[1] if match[1] else None
                    if content_part:
                        contents.append(content_part.strip())
                    if annotation_part:
                        annotations.append(annotation_part.strip())
                if sections:
                    sections[-1]['content'].append({'texts': contents, 'annotations': annotations})
        return bookname, sections


def calculate_font_size(font_path, font_size, text_box_width, line_count=10, line_space=5,
                        is_annotation=False,
                        annotation_line_space=5):
    """
    根据初始字体字号判断是否文本框是否能容纳该字号的文本，如果超出文本框，则计算一个合适的字体字号
    :param font_path: 字体文件路径
    :param font_size: 初始字体字号
    :param text_box_width: 文本框宽度
    :param line_count: 文本框分行数
    :param line_space: 行间距
    :param is_annotation: 是否是批注文字
    :param annotation_line_space: 双行夹批行间距， is_annotation为True时有效
    :return: 最终计算出的字体字号，文字宽度，文字高度
    """
    size = font_size
    char_width = 0
    char_height = 0
    for size in range(font_size, 0, -1):
        font = ImageFont.truetype(font_path, size)
        char_width, char_height = font.getbbox('字')[2], font.getbbox('字')[3]
        if is_annotation:
            if line_count * (
                    2 * char_width + annotation_line_space + line_space) - line_space > text_box_width:
                continue
            else:
                break
        else:
            if line_count * (char_width + line_space) - line_space > text_box_width:
                continue
            else:
                break

    return size, char_width, char_height


def add_noise(image, noise_level=0.01):
    """
    为图片添加噪点 (目前效果不理想)
    :param image:
    :param noise_level:
    :return:
    """
    LOGGER.info('为图片添加噪点')
    width, height = image.size
    pixels = image.load()

    for i in range(width):
        for j in range(height):
            if random.random() < noise_level:
                noise_color = random.randint(0, 255)
                pixels[i, j] = (noise_color, noise_color, noise_color)
    return image


def apply_vintage_effect(image, blur_radius=1, contrast_factor=0.8, color_factor=0.7):
    """
    应用做旧效果，包括模糊处理，降低对比度和降低饱和度
    :param image: 待处理的图像
    :param blur_radius: 模糊像素
    :param contrast_factor: 对比度降低比例
    :param color_factor: 饱和度降低比例
    :return: 做旧之后的图像
    """
    LOGGER.info('为图片添加做旧效果')
    # 应用高斯模糊效果
    image = image.filter(ImageFilter.GaussianBlur(blur_radius))

    # 调整对比度
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast_factor)

    # 调整饱和度
    enhancer = ImageEnhance.Color(image)
    enhancer.enhance(color_factor)

    return image


def create_gradient_mask(size):
    """创建一个渐变遮罩，边缘颜色为黄色，中间为白色"""
    mask = Image.new('L', size, 0)  # 灰度图
    draw = ImageDraw.Draw(mask)

    width, height = size
    center_x, center_y = width // 2, height // 2
    max_radius = min(center_x, center_y)

    for i in range(max_radius):
        # 计算每个环的颜色值，边缘更深
        value = int(255 * (1 - i / max_radius))
        draw.ellipse((center_x - i, center_y - i, center_x + i, center_y + i), fill=value)

    return mask


def apply_yellowed_page_effect_with_gradient(image):
    """应用带渐变的书页发黄效果"""
    # 生成渐变遮罩
    mask = create_gradient_mask(image.size)

    # 将图像转换为RGBA格式
    image = image.convert("RGBA")

    # 获取每个像素
    data = image.getdata()
    new_data = []

    for item in data:
        r, g, b, a = item
        # 调整颜色，使其变黄
        r = int(r * 1.3)
        g = int(g * 1.3)
        b = int(b * 0.7)

        r = min(255, r)
        g = min(255, g)
        b = min(255, b)

        new_data.append((r, g, b, a))

    # 更新图像数据
    image.putdata(new_data)

    # 应用渐变遮罩
    yellowed_image = Image.new("RGBA", image.size)
    yellowed_image.putdata(new_data)

    # 将原图像与发黄效果结合，使用遮罩控制
    final_image = Image.composite(yellowed_image, image, mask)

    return final_image


def gen_image_with_fixed_size(lines, params, output_dir, page):
    """
    生成排版好的图片
    :return:
    """
    margin = params.get('margin')
    border = params.get('border')
    inner_margin = params.get('inner_margin')

    LOGGER.info("开始生成图片")

    image, draw, line_width = init_image(params)

    # 逐个字符绘制图像
    LOGGER.info('开始绘制文本')
    for line_index, line in enumerate(lines):
        # 筒子页中间行不绘制正文
        if line_index >= params.get('line_count'):
            line_index += 1
        x = params.get('width') - margin[3] - (
                line_index + 1) * line_width - border - 3 + params.get('line_space') / 2
        y = margin[0] + border + 3 + inner_margin[0]
        y_anno_start = 0
        y_anno_end = 0
        font_paths = []
        font_size = 0
        font_color = 'black'
        char_height = 0
        char_space = 0
        for i in range(len(line.get('line'))):
            item = line.get('line')[i]
            x_offset = 0
            text_type = item.get('type')
            text = item.get('value')

            match text_type:
                case TextType.CHAPTER:
                    font_paths = params.get('chapter_font_paths')
                    font_size = params.get('chapter_font_size')
                    font_color = params.get('chapter_font_color')
                    char_height = params.get('chapter_char_height')
                    y = margin[0] + border + 3
                case TextType.CONTENT:
                    font_paths = params.get('content_font_paths')
                    font_size = params.get('content_font_size')
                    font_color = params.get('content_font_color')
                    char_height = params.get('content_char_height')
                    char_space = params.get('content_char_space')
                case TextType.ANNOTATION:
                    font_paths = params.get('annotation_font_paths')
                    font_size = params.get('annotation_font_size')
                    font_color = params.get('annotation_font_color')
                    char_height = params.get('annotation_char_height')
                    char_space = params.get('annotation_char_space')
                    x_offset = params.get('annotation_char_width') + params.get(
                        'annotation_line_space') - params.get('line_space')
                    x = x + x_offset
                    y_anno_start = y

            text_length = len(text)
            for i in range(text_length):
                char = text[i]
                font = load_font_for_char(char, font_paths, font_size)
                if font:
                    draw.text((x, y), char, font=font, fill=font_color)
                if text_type == TextType.ANNOTATION and i == math.ceil(text_length / 2) - 1:
                    x = x - x_offset
                    y_anno_end = y + char_height + char_space
                    y = y_anno_start
                else:
                    y += char_height + char_space
            if text_type == TextType.ANNOTATION:
                y = y_anno_end
                if math.ceil(text_length / 2) % 2 != 0:
                    y = y + char_height + char_space

    chapter_name = lines[0].get('chapter')
    draw_middle_line(draw, params.get('bookname'), chapter_name, convert_number_to_chinese(page), line_width, params)
    output_path = os.path.join(output_dir,
                               f'第{convert_number_to_chinese(page)}頁.png')
    LOGGER.info(f'文本绘制完成, 圖片保存至{output_path}')
    image.save(output_path)


def gen_images(texts, params):
    """
    并发生成多页
    :param texts: 待输入的文本
    :param params: 程序参数字典
    :return:
    """
    output_dir = params.get('output_dir')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    elif not os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
        os.makedirs(output_dir)

    text_lines = split_text(texts, params)
    line_count = params.get('line_count')

    # pprint(text_lines)
    page = 1
    with Pool(processes=10) as pool:
        tasks = []
        for i in range(math.ceil(len(text_lines) / (line_count * 2))):
            part = text_lines[i * line_count * 2: line_count * 2 * (i + 1)]
            tasks.append(pool.apply_async(
                gen_image_with_fixed_size, (part, params, output_dir, page)))
            page += 1

        for task in tasks:
            try:
                task.get()
            except Exception as e:
                LOGGER.exception(e)


def init_image(params):
    """
    根据参数绘制底图
    :param params: 程序参数字典
    :return:
    """
    scale_factor = params.get('scale_factor')
    width = params.get('width')
    height = params.get('height')
    margin = params.get('margin')
    border = params.get('border')

    LOGGER.debug('计算文本边框尺寸')
    # 文本框宽度为内框宽度
    text_box_width = width - margin[2] - margin[3] - border * 2 - 6

    # 筒子页是两页对折，中间一行是书口，一个筒子页总行数为 line_count * 2 + 1
    line_width = (text_box_width) / (params.get('line_count') * 2 + 1)

    if params.get('background'):
        LOGGER.debug('生成带背景的底图')
        bg_image = Image.open(params.get('background')).resize(width, height)
        image = Image.new('RGB', (width, height))
        image.paste(bg_image)
    else:
        LOGGER.debug('生成底图')
        image = Image.new('RGB', (width, height), color=params.get('bg_color'))

    image_fishtail = Image.new('RGB', (scale_factor * width, scale_factor * height),
                               color=params.get('bg_color'))

    fishtail_draw = ImageDraw.Draw(image_fishtail)

    fishtail_top = params.get('fishtail_top')
    fishtail_height = params.get('fishtail_height')
    fishtail_line_space = params.get('fishtail_line_space')
    fishtail_break_point = params.get('fishtail_break_point')
    center_x = width - margin[3] - border - 3 - line_width * params.get('line_count')
    center_y = margin[0] + border + 3 + fishtail_top
    draw_fishtail(fishtail_draw, scale_factor, center_x, center_y, line_width, fishtail_height, fishtail_line_space, fishtail_break_point)
    layer_fishtail = image_fishtail.resize((width, height), Image.Resampling.LANCZOS)

    image.paste(layer_fishtail)

    draw = ImageDraw.Draw(image)

    LOGGER.debug('绘制边框')
    draw.rectangle([margin[2], margin[0], width - (margin[3]), height - margin[1]],
                   outline=params.get('border_color'),
                   width=border)
    draw.rectangle([margin[2] + border + 2, margin[0] + border + 2, width - margin[3] - border - 2,
                    height - margin[1] - border - 2], outline=params.get('border_color'), width=1)

    if params.get('line_sep'):
        LOGGER.debug('绘制行分隔线')
        for i in range(params.get('line_count') * 2):
            x = width - margin[3] - (i + 1) * line_width - border - 3
            draw.line([(x, margin[0] + border + 3), (x, height - margin[1] - border - 3)],
                      fill=params.get('line_sep_color'), width=params.get('line_sep_width'))

    return image, draw, line_width


def draw_fishtail(draw, scale_factor, x, y, line_width, fishtail_height, fishtail_line_space, fishtail_break_point, color='black'):
    """
    绘制一个简单的对称鱼尾图案。
    :param draw: ImageDraw 对象
    :param scale_factor: 放大倍数
    :param x: 图案右顶点X坐标
    :param y: 图案右顶点Y坐标
    :param line_width: 中间行宽度
    :param fishtail_height: 鱼尾图案高度
    :param fishtail_line_space: 鲁鱼尾图上下直线距离鱼尾图案主体的距离
    :param fishtail_break_point: 鱼尾图案中间转折点距离鱼尾图案上边的距离
    :param color: 图案颜色
    """
    # 定义鱼尾的几个关键点（简单的对称多边形）
    x = x * scale_factor
    y = y * scale_factor
    line_width = line_width * scale_factor
    fishtail_break_point = fishtail_break_point * scale_factor
    fishtail_height = fishtail_height * scale_factor
    fishtail_line_space = fishtail_line_space * scale_factor


    points = [
        (x, y),  # 右上顶点
        (x, y + fishtail_height),  # 右下顶点
        (x - line_width / 2, y + fishtail_break_point),  # 中间转折点
        (x - line_width, y + fishtail_height),  # 左下顶点
        (x - line_width, y)  # 左上顶点
    ]

    # 绘制多边形
    draw.polygon(points, fill=color, outline=color)
    draw.line([(x, y - fishtail_line_space), (x - line_width, y - fishtail_line_space)], fill='black', width=scale_factor)
    draw.line([(x, y + fishtail_height + fishtail_line_space), (x - line_width / 2, y + fishtail_break_point + fishtail_line_space)], fill='black', width=scale_factor)
    draw.line([(x - line_width / 2, y + fishtail_break_point + fishtail_line_space), (x - line_width, y + fishtail_height + fishtail_line_space)], fill='black', width=scale_factor)


def draw_middle_line(draw, bookname, chapter_name, page, line_width, params):
    """
    绘制筒子页中间行
    :param draw:
    :param title_x: 中间行文字绘制起始X坐标
    :param title_y: 中间行文字绘制起始Y坐标
    :param bookname: 书籍名称
    :param chapter_name: 章节名
    :param page: 页码
    :param params: 程序参数字典
    :return:
    """
    font_paths = params.get('chapter_font_paths')
    font_size = params.get('middle_line_font_size')
    font = ImageFont.truetype(font_paths[0], font_size)
    char_width, char_height = font.getbbox('字')[2], font.getbbox('字')[3]

    title_x = params.get('width') - params.get('margin')[3] - params.get('border') - 3 - (params.get('line_count') + 0.5) * line_width - char_width / 2
    title_y = params.get('margin')[0] + params.get('border') + 3 + params.get('fishtail_top') + params.get('fishtail_height')

    bookname_length = len(bookname)
    for i in range(bookname_length):
        char = bookname[i]
        font = load_font_for_char(char, font_paths, font_size)
        if font:
            draw.text((title_x, title_y), char, font=font, fill='black')
            title_y += char_height

    chapter_x = title_x
    chapter_y = title_y + char_height
    for i in range(len(chapter_name)):
        char = chapter_name[i]
        font = load_font_for_char(char, font_paths, font_size)
        if font:
            draw.text((chapter_x, chapter_y), char, font=font, fill='black')
            chapter_y += char_height

    page_x = title_x
    page_y = params.get('height') - params.get('margin')[1] - params.get('border') - 3 - (len(page) + 1) * char_height
    for i in range(len(page)):
        char = page[i]
        font = load_font_for_char(char, font_paths, font_size)
        if font:
            draw.text((page_x, page_y), char, font=font, fill='black')
            page_y += char_height


def main():
    """
    程序入口
    :return:
    """
    input_path = 'input/孙子兵法.txt'
    with open(os.path.join('config', 'config.json'), encoding='utf-8') as f:
        params = json.load(f)

    bookname, texts = load_text(input_path)

    output_dir = os.path.join(params.get('output_dir'), bookname)
    params = adjust_font(params)
    params['output_dir'] = output_dir
    params['bookname'] = bookname
    gen_images(texts, params)


def check_font_for_char(char: str, fonts: list, font_size: int):
    """
    从字体列表中为指定字符查找合适的字体
    :param char: 指定字符
    :param fonts: 字体列表
    :param font_size: 字体大小
    :return: 包含该字符的字体
    """
    for font_path in fonts:
        try:
            font = ImageFont.truetype(font_path, font_size)

            bbox = font.getmask(char).getbbox()
            print(bbox)
            print(font.getbbox(char))
        except Exception as e:
            LOGGER.exception(e)
    return None


if __name__ == '__main__':
    main()
    # check_font_for_char('汉', ['fonts/ZiYue_Song_Keben_GBK_Updated.ttf'], 44)
