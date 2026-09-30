# -*- coding: utf-8 -*-
"""
可移植 Sprite 动画模块 —— 供主游戏直接复用
================================================
用法（主游戏接入时复制本文件即可）：

    import sprite
    # 加载某族某动作的 5 帧（自动把浅绿背景设为透明）
    frames = sprite.load_frames('rts-assets', 'human', 'walk', 5, scale=(112, 112))
    # 播放器：注册动作 → 播放 → 每帧 update → 取当前帧
    a = sprite.Animator()
    a.add_clip('walk',   sprite.load_frames(ASSET_DIR, race, 'walk',   5, SIZE))
    a.add_clip('attack', sprite.load_frames(ASSET_DIR, race, 'attack', 5, SIZE))
    a.add_clip('die',    sprite.load_frames(ASSET_DIR, race, 'die',    5, SIZE))
    a.play('walk')          # 切换动作（自动从头播放）
    a.flip = True           # 镜像翻转（朝左）
    ...
    a.update(dt)            # 帧推进
    surf.blit(a.image(), rect)

约束：
- 素材命名：<race>_<action>1..N.png，1:1 方形，浅草地绿背景
- 加载时自动按颜色距离做容差抠图 + 边缘羽化（角色无绿边矩形，可互相叠放）
"""
import os
import pygame


def _chroma_key(img, bg, lo=26.0, hi=64.0):
    """把与背景色 bg 颜色距离 <= lo 的像素设为全透明，>= hi 的设为全不透明，
    中间区间线性 alpha 羽化（消除绿边与抗锯齿硬切）。
    返回一张新的 32 位带 alpha Surface。"""
    w, h = img.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA, 32)
    out.blit(img, (0, 0))                 # 拷贝像素，初始 alpha=255
    br, bg_, bb = bg[0], bg[1], bg[2]
    for x in range(w):
        for y in range(h):
            r, g, b, _ = out.get_at((x, y))
            d = ((r - br) * (r - br) + (g - bg_) * (g - bg_) + (b - bb) * (b - bb)) ** 0.5
            if d <= lo:
                na = 0
            elif d >= hi:
                na = 255
            else:
                na = int(255 * (d - lo) / (hi - lo))
            out.set_at((x, y), (r, g, b, na))
    return out


_FRAME_CACHE = {}


def load_frames(asset_dir, race, action, count=5, scale=None):
    """加载 race_action1..count.png。
    - 采样角点背景色，按颜色距离做容差抠图 + 边缘羽化（角色不再带绿边矩形）
    - 先缩放到目标尺寸再抠图（小图上逐像素 alpha 处理，快且边缘平滑）
    - 结果按 (目录,族,动作,帧数,尺寸) 缓存，同族多单位不重复抠图
    返回带 alpha 的 Surface 帧列表。"""
    key = (os.path.abspath(asset_dir), race, action, count, tuple(scale) if scale else None)
    if key in _FRAME_CACHE:
        return _FRAME_CACHE[key]
    frames = []
    for i in range(1, count + 1):
        path = os.path.join(asset_dir, '%s_%s%d.png' % (race, action, i))
        img = pygame.image.load(path).convert()
        bg = img.get_at((2, 2))          # 背景角点色
        if scale:
            img = pygame.transform.smoothscale(img, scale)
        img = _chroma_key(img, bg)
        frames.append(img)
    _FRAME_CACHE[key] = frames
    return frames


class Animator:
    """动作播放器：按名字切换 clip，dt 推进帧，返回当前帧。

    字段：
        current  当前动作名
        frame_i  当前帧序号
        flip     是否水平镜像（朝左时 True）
        finished 非循环动作播完后 True（循环动作恒为 False）
    """

    def __init__(self):
        self.clips = {}
        self.current = None
        self.frame_i = 0
        self._t = 0.0
        self.flip = False
        self.finished = False

    def add_clip(self, name, frames, fps=8, loop=True):
        self.clips[name] = {'frames': frames, 'fps': fps, 'loop': loop}
        return self

    def play(self, name):
        """切换到指定动作（若已是该动作则不动）；非循环动作从头播放。"""
        if self.current != name:
            self.current = name
            self.frame_i = 0
            self._t = 0.0
            self.finished = False
        return self

    def update(self, dt):
        if self.current is None or self.finished:
            return
        clip = self.clips[self.current]
        fd = 1.0 / clip['fps']
        self._t += dt
        if clip['loop']:
            while self._t >= fd:
                self._t -= fd
                self.frame_i = (self.frame_i + 1) % len(clip['frames'])
        else:
            if self._t >= fd:
                steps = int(self._t / fd)
                self._t -= steps * fd
                self.frame_i = min(self.frame_i + steps, len(clip['frames']) - 1)
                if self.frame_i >= len(clip['frames']) - 1:
                    self.finished = True

    def image(self):
        """返回当前帧 Surface；flip=True 时返回水平镜像（每次调用新 Surface，量少可接受）。"""
        if self.current is None:
            return None
        img = self.clips[self.current]['frames'][self.frame_i]
        if self.flip:
            return pygame.transform.flip(img, True, False)
        return img
