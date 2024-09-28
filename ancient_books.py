import cv2
import math
import os
import random
import shutil
import textwrap
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Pool
from opencc import OpenCC
from PIL import ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter
from logger import Logger

LOGGER = Logger('ancient-books')


def convert_to_traditional_chinese(lines):
    """
    将简体中文文本转换为繁体中文文本
    :param lines: 待转换的文本列表
    :return: 繁体中文文本
    """
    cc = OpenCC('s2t')
    return [cc.convert(line) for line in lines]


def load_font_for_char(char, fonts, font_size):
    """
    从字体列表中为指定字符查找合适的字体
    :param char: 指定字符
    :param fonts: 字体列表
    :param font_size: 字体大小
    :return: 包含该字符的字体
    """
    for font_path in fonts:
        font = ImageFont.truetype(font_path, font_size)
        if font.getmask(char).getbbox():
            return font
    return


def split_text(text, length):
    """
    将整段文本按每行字数分割成文本列表
    :param text: 要輸入的文本
    :param length: 每行字數
    :return: 文本列表
    """
    wrapped_lines = textwrap.wrap(text, width=length)
    return wrapped_lines


def refactor_lines(lines, length):
    """
    对多个段落文本按指定每行字数重新分割成文本列表
    :param lines: 要输入的文本段落列表
    :param length: 每行字数
    :return: 重新分割后的文本列表
    """
    formated_lines = []
    for line in lines:
        formated_line = textwrap.wrap(line, width=length)
        formated_lines.extend(formated_line)
    return formated_lines


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


def gen_image_with_flexible_size(lines, font_paths, font_size, output_path, line_space=20, margin=[200, 200, 50, 50],
                                 border=3,
                                 backgroud=None, line_sep=False, line_color=None, line_width=1, with_noise=False,
                                 noise_level=0.005,
                                 older=False, bg_color='white'):
    """
    生成排版好的图片
    :param lines: 包含多行文字的列表
    :param font_paths: 字体文件路径列表
    :param font_size： 字体大小
    :param output_path: 输出图片路径
    :param line_space: 行间距
    :param margin: 页面边距（上， 下， 左， 右）
    :param border: 图像的边框大小
    :param backgroud: 背景图片路径
    :param line_sep: 是否添加行分隔线
    :param line_color: 行分隔线的颜色，line_sep为True时有效
    :param line_width: 行分隔线宽度，line_sep为True时有效
    :param with_noise: 是否添加噪点
    :param noise_level: 噪点等级
    :param older: 是否做旧
    :param bg_color: 背景颜色
    :return:
    """
    output_dir, output_file_name = os.path.split(output_path)
    if not os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
        os.makedirs(output_dir)

    # 根据主要字体确定字符尺寸
    primary_font = ImageFont.truetype(font_paths[0], font_size)
    char_width, char_height = primary_font.getbbox('字')[2], primary_font.getbbox('字')[3]

    max_line_length = max(len(line) for line in lines)
    image_width = (char_width + line_space) * len(lines) + margin[2] + margin[3]
    image_height = char_height * max_line_length + margin[0] + margin[1]

    # 生成带背景图片的图片，如果有的话
    if backgroud:
        LOGGER.info('生成带背景图片的图片')
        bg_image = Image.open(backgroud).resize(image_width, image_height)
        image = Image.new('RGB', (image_width, image_height))
        image.paste(bg_image)
    else:
        image = Image.new('RGB', (image_width, image_height), color=bg_color)

    draw = ImageDraw.Draw(image)

    # 添加边框
    LOGGER.info('绘制边框')
    draw.rectangle([margin[2] - 10, margin[0], image_width - (margin[3]), image_height - margin[1] + 10],
                   outline='black', width=border)

    # 逐个字符绘制图像
    for line_index, line in enumerate(lines):
        x = image_width - margin[2] - (line_index + 1) * (char_width + line_space) + border
        y = margin[0] + border
        for char in line:
            font = load_font_for_char(char, font_paths, font_size)
            if font:
                draw.text((x, y), char, font=font, fill='black')
            y += char_height

        # 添加行分隔线
        if line_sep:
            LOGGER.info('绘制行分隔线')
            if line_index < len(lines) - 1:
                line_x = x - line_space // 2
                draw.line([(line_x, margin[0] + border), (line_x, image_height - margin[1] + 10)],
                          fill=line_color, width=line_width)

    # 添加噪点
    if with_noise:
        image = add_noise(image, noise_level=noise_level)

    # 添加做旧效果
    if older:
        image = apply_vintage_effect(image)

    # 模拟书页发黄效果
    # if older:
    #     print('添加书页发黄效果')
    #     image = apply_yellowed_page_effect_with_gradient(image)

    image.save(output_path)


def gen_image_with_fixed_size(lines, font_paths, font_size, output_path, width=720, height=1120, line_count=10,
                              line_space=20,
                              margin=[200, 200, 50, 50], border=3, backgroud=None, line_sep=False, line_sep_color=None,
                              line_sep_width=1, with_noise=False, noise_level=0.005, older=False, bg_color='white'):
    """
    生成排版好的图片
    :param lines: 包含多行文字的列表
    :param font_paths: 字体文件路径列表
    :param font_size： 字体大小
    :param output_path: 输出图片路径
    :param width: 图片宽度
    :param height: 图片高度
    :param line_count: 第页行数
    :param line_space: 行间距
    :param margin: 页面边距（上， 下， 左， 右）
    :param border: 图像的边框大小
    :param backgroud: 背景图片路径
    :param line_sep: 是否添加行分隔线
    :param line_sep_color: 行分隔线的颜色，line_sep为True时有效
    :param line_sep_width: 行分隔线宽度，line_sep为True时有效
    :param with_noise: 是否添加噪点
    :param noise_level: 噪点等级
    :param older: 是否做旧
    :param bg_color: 背景颜色
    :return:
    """
    LOGGER.info("开始生成图片")
    output_dir, output_file_name = os.path.split(output_path)
    if not os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
        os.makedirs(output_dir)

    # 根据主要字体确定字符尺寸
    primary_font = ImageFont.truetype(font_paths[0], font_size)
    char_width, char_height = primary_font.getbbox('字')[2], primary_font.getbbox('字')[3]

    # max_line_length = max(len(line) for line in lines)
    # width = (char_width + line_space) * len(lines) + margin[2] + margin[3]
    # height = char_height * max_line_length + margin[0] + margin[1]

    # 生成带背景图片的图片，如果有的话
    if backgroud:
        LOGGER.info('生成带背景的底图')
        bg_image = Image.open(backgroud).resize(width, height)
        image = Image.new('RGB', (width, height))
        image.paste(bg_image)
    else:
        LOGGER.info('生成底图')
        image = Image.new('RGB', (width, height), color=bg_color)

    draw = ImageDraw.Draw(image)

    # 添加边框
    LOGGER.info('计算文本边框尺寸')
    text_box_width = width - margin[2] - margin[3]
    text_box_height = height - margin[0] - margin[1]

    LOGGER.info('绘制边框')
    draw.rectangle([margin[2], margin[0], width - (margin[3]), height - margin[1]], outline='black', width=border)

    # 判断文本行是否能容纳指定字号的文字
    line_width = char_width + line_space
    if line_count * line_width > text_box_width:
        raise ValueError(f"字体字号{font_size}过大，请指定合适字号")

    # 根据字体字号计算每行最多容纳的字数
    chars_per_line = abs(text_box_height // char_height)

    # 绘制行分隔符
    if line_sep:
        LOGGER.info('绘制行分隔线')
        for i in range(line_count - 1):
            x = width - margin[2] - (i + 1) * (char_width + line_space) + border
            line_x = x - line_space // 2
            draw.line([(line_x, margin[0] + border), (line_x, height - margin[1])],
                      fill=line_sep_color, width=line_sep_width)

    # 逐个字符绘制图像
    LOGGER.info('开始绘制文本')
    for line_index, line in enumerate(lines):
        x = width - margin[2] - (line_index + 1) * (char_width + line_space) + border
        y = margin[0] + border
        for char in line:
            font = load_font_for_char(char, font_paths, font_size)
            if font:
                draw.text((x, y), char, font=font, fill='black')
            y += char_height
    LOGGER.info('文本绘制完成')

    # 添加噪点
    if with_noise:
        image = add_noise(image, noise_level=noise_level)

    image.save(output_path)
    LOGGER.info(f'图片保存至{output_path}')


def gen_images(texts, font_paths, font_size, output_dir, width=720, height=1120, line_count=10, line_space=20,
               margin=[200, 200, 50, 50], border=3, backgroud=None, line_sep=False, line_sep_color=None,
               line_sep_width=1, with_noise=False, noise_level=0.005, older=False, bg_color='white'):
    """
    并发生成多页
    :param texts: 待输入的文本
    :param font_paths: 字体文件路径列表
    :param font_size: 字体大小
    :param output_dir: 图片生成目录
    :param width: 图片的宽（像素）
    :param height: 图片的高（像素）
    :param line_count: 每页的行数
    :param line_space: 行间距
    :param margin: 页而边距
    :param border: 边框宽度
    :param backgroud: 背景图片
    :param line_sep: 是否绘制行分隔线
    :param line_sep_color: 行分隔线颜色，line_sep为True时有效
    :param line_sep_width: 行分隔线宽度，line_sep为True时有效
    :param with_noise: 是否添加噪点
    :param noise_level: 噪点等级，with_noise为True时有效
    :param older: 是否添加做旧效果
    :param bg_color: 背景底图颜色
    :return:
    """
    # 根据主要字体确定字符尺寸
    primary_font = ImageFont.truetype(font_paths[0], font_size)
    char_width, char_height = primary_font.getbbox('字')[2], primary_font.getbbox('字')[3]

    # 添加边框
    LOGGER.info('计算文本边框尺寸')
    # text_box_width = width - margin[2] - margin[3]
    text_box_height = height - margin[0] - margin[1]

    # 根据字体字号计算每行最多容纳的字数
    chars_per_line = abs(text_box_height // char_height)

    lines = refactor_lines(texts, chars_per_line)
    if len(lines) > line_count:
        with Pool() as pool:
            tasks = []
            for i in range(math.ceil(len(lines) / line_count)):
                part = lines[i * line_count: line_count * (i + 1)]
                output_path = os.path.join(output_dir, f'page-{i + 1}.png')
                tasks.append(pool.apply_async(
                    gen_image_with_fixed_size, (
                    part, font_paths, font_size, output_path, width, height, line_count, line_space, margin, border,
                    backgroud, line_sep, line_sep_color, line_sep_width, with_noise, noise_level, older, bg_color,)))

            for task in tasks:
                try:
                    task.get()
                except Exception as e:
                    LOGGER.exception(e)
    else:
        output_path = os.path.join(output_dir, 'page-1.png')
        gen_image_with_fixed_size(lines, font_paths, font_size, output_path, width=width, height=height,
                                  line_count=line_count,
                                  line_space=line_space, margin=margin, border=border, backgroud=backgroud,
                                  line_sep=line_sep,
                                  line_sep_color=line_sep_color, line_sep_width=line_sep_width, with_noise=with_noise,
                                  noise_level=noise_level, older=older, bg_color=bg_color)


if __name__ == '__main__':
    with open('input/传习录.txt', 'r', encoding='utf-8') as f:
        texts = f.readlines()

    font_paths = ['fonts/ZiYue_Song_Keben_GBK_Updated.ttf', 'fonts/ZiYue_Song_Keben_Tranditional_Supplimentary.otf', 'fonts/WenYue_GuTi_FangSong.otf',
                  'fonts/HanYi_ChangLi_Song_Keben_JingXiu.ttf', 'fonts/FangZheng_Song_Keben_XiuKai_GBK.TTF']
    output_dir = 'output'

    gen_images(texts, font_paths, 40, output_dir, line_sep=True, line_sep_color='black', with_noise=True, older=True,
               bg_color='#c3aa7d')
