# -*- coding: utf-8 -*-
"""
2D 即时战略原型（原生版）
Python + pygame 实现，功能：
  1. 大地图（3600x2600），中键/右键按住拖动、WASD/方向键平移
  2. 多兵种（工兵可建造 3 种建筑，矩形表示）
  3. 点选 / 框选 / 双击全选画面内同类，右键点击下达移动命令（A* 寻路）
  4. 建筑与单位碰撞：不可穿越、放置检测、单位软碰撞与前方避让
  5. 小地图（点击/拖动跳转视角）+ 缩放滑块（0.5x-2.0x）

启动方式：
  双击「启动游戏.bat」或 dist 下的 exe。
自检：
  python game.py --selftest
冒烟：
  python game.py --smoke
"""
import heapq
import math
import os
import random
import sys
import time

import pygame
import sprite

# ================= 常量（PATCH16 版数值） =================
GRID = 24
MAP_W, MAP_H = 3600, 2600
COLS = MAP_W // GRID
ROWS = MAP_H // GRID
BUILD_TIME = 4.0
TRAIN_TIME = 3.0
DOUBLE_CLICK_MS = 0.3
ZOOM_MIN, ZOOM_MAX = 0.5, 2.0
MM_MARGIN = 16

COMBAT_TRIGGER = 80.0
BATTLE_RADIUS = 44.0
BATTLE_MARGIN = 14.0
BATTLE_LEAVE = 350.0   # 旧值90是四方向槽时代；RW直接追击需≥CHASE_LEAVE才不误踢
ATTACK_REACH_BASE = 12.0   # RW: max(9, selfR+targetR, 11)
ATTACK_COOLDOWN = 1.05
COMBAT_IMMUNE = 1.6
CHASE_LEAVE = 400.0
DAMAGE = 12                               # 每次挥剑伤害（每轮攻击动画结算一次；HP100 → 9 刀）

if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(__file__)
_ASSET_CANDIDATES = [os.path.abspath(os.path.join(_BASE_DIR, '..', 'rts-assets')),
                     os.path.abspath(os.path.join(_BASE_DIR, '..', '..', 'rts-assets'))]
ASSET_DIR = next((p for p in _ASSET_CANDIDATES if os.path.isdir(p)), _ASSET_CANDIDATES[0])
SPRITE_WORLD = 30.0
SPRITE_RACE = {'soldier': 'human', 'esoldier': 'orc'}
_SPRITE_CACHE = {}
_SPRITE_FAIL = [0]

UNIT_DEF = {
    'engineer':  {'name': '工兵', 'r': 10, 'speed': 68,  'team': 'player', 'color': (67, 160, 71)},
    'soldier':   {'name': '步兵', 'r': 9,  'speed': 70,  'team': 'player', 'color': (61, 125, 216), 'hp': 100},
    'tank':      {'name': '坦克', 'r': 15, 'speed': 48,  'team': 'player', 'color': (91, 109, 120)},
    'hero':      {'name': '英雄', 'r': 13, 'speed': 100, 'team': 'player', 'color': (224, 169, 60)},
    'esoldier':  {'name': '敌步兵', 'r': 9,  'speed': 0,  'team': 'enemy', 'color': (208, 80, 74), 'hp': 100},
    'etank':     {'name': '敌坦克', 'r': 15, 'speed': 0,  'team': 'enemy', 'color': (140, 58, 52)},
    'eengineer': {'name': '敌工兵', 'r': 10, 'speed': 0,  'team': 'enemy', 'color': (168, 85, 63)},
}
BUILD_DEF = {
    'barracks': {'name': '兵营', 'w': 92, 'h': 72, 'color': (63, 116, 201), 'edge': (39, 74, 128)},
    'turret':   {'name': '炮塔', 'w': 52, 'h': 52, 'color': (192, 74, 65), 'edge': (122, 42, 36)},
    'depot':    {'name': '仓库', 'w': 104, 'h': 82, 'color': (94, 138, 79), 'edge': (58, 87, 48)},
}
ROCKS = [
    (150, 200, 220, 90), (520, 1180, 150, 110), (920, 320, 170, 120),
    (1120, 1150, 180, 120), (1520, 520, 200, 140), (1830, 1340, 160, 100),
    (2050, 900, 190, 130), (2600, 300, 200, 130), (900, 2000, 170, 120),
    (3200, 1500, 220, 140), (2400, 2200, 180, 120), (500, 2300, 160, 100),
    (3100, 2200, 190, 130), (1480, 950, 460, 50), (1480, 1150, 460, 50),
    (2350, 1470, 300, 50), (2350, 1610, 300, 50),
]

# ================= 数据类 =================
class Unit:
    __slots__ = ('id', 'type', 'name', 'r', 'speed', 'team', 'color', 'x', 'y',
                 'angle', 'state', 'phase', 'move_target', 'path', 'path_idx',
                 'hidden', 'home', 'anim', 'facing', 'race', 'locked', 'battle',
                 'att_cd', 'combat_immune', 'hp', 'max_hp',
                 'prev_anim_frame')

    def __init__(self, uid, type_, x, y):
        d = UNIT_DEF[type_]
        self.id = uid
        self.type = type_
        self.name = d['name']
        self.r = d['r']
        self.speed = d['speed']
        self.team = d['team']
        self.color = d['color']
        self.x = x
        self.y = y
        self.angle = 0.0
        self.state = 'idle'
        self.phase = None
        self.move_target = None
        self.path = None
        self.path_idx = 0
        self.hidden = False
        self.home = None
        self.anim = None
        self.facing = 1
        self.race = None
        self.locked = None
        self.battle = None
        self.att_cd = 0.0
        self.combat_immune = 0.0
        self.hp = d.get('hp', 0)
        self.max_hp = self.hp
        self.prev_anim_frame = 0                # 上一帧动画帧号（攻击动画回绕=一轮完成=一次攻击动作）
        if type_ in SPRITE_RACE:
            self.race = SPRITE_RACE[type_]
            try:
                a = sprite.Animator()
                a.add_clip('walk', sprite.load_frames(ASSET_DIR, self.race, 'walk', 5, (64, 64)),
                           fps=6, loop=True)
                a.add_clip('attack', sprite.load_frames(ASSET_DIR, self.race, 'attack', 5, (64, 64)),
                           fps=6, loop=True)
                a.add_clip('die', sprite.load_frames(ASSET_DIR, self.race, 'die', 5, (64, 64)),
                           fps=6, loop=False)
                a.play('walk')
                self.anim = a
            except Exception:
                self.anim = None
                _SPRITE_FAIL[0] += 1

class Building:
    __slots__ = ('type', 'name', 'x', 'y', 'w', 'h', 'color', 'edge',
                 'train_queue', 'train_progress')

    def __init__(self, type_, x, y):
        d = BUILD_DEF[type_]
        self.type = type_
        self.name = d['name']
        self.x = x
        self.y = y
        self.w = d['w']
        self.h = d['h']
        self.color = d['color']
        self.edge = d['edge']
        self.train_queue = []
        self.train_progress = 0.0

class Construction:
    __slots__ = ('type', 'name', 'x', 'y', 'w', 'h', 'progress', 'workers',
                 'active_worker')

    def __init__(self, type_, x, y):
        d = BUILD_DEF[type_]
        self.type = type_
        self.name = d['name']
        self.x = x
        self.y = y
        self.w = d['w']
        self.h = d['h']
        self.progress = 0.0
        self.workers = []
        self.active_worker = None

class Battle:
    __slots__ = ('id', 'cx', 'cy', 'radius', 'units', 'join_t')

    def __init__(self, bid, cx, cy, radius):
        self.id = bid
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.units = set()
        self.join_t = {}

# ================= 主游戏类 =================
class Game:
    def __init__(self):
        self.units = []
        self.buildings = []
        self.constructions = []
        self.selection = set()
        self.camera = [0.0, 0.0]
        self.view = [1280, 720]
        self.zoom = 1.0
        self.place_mode = None
        self.hover_w = [0.0, 0.0]
        self.order_point = None
        self.toast_text = None
        self.toast_t = 0.0
        self.keys = set()
        self.mouse_pos = (0, 0)
        self.mouse_on = False
        self.left_down = None
        self.right_down = None
        self.mid_down = None
        self.marquee = None
        self.last_click = None
        self.mm_drag = False
        self.slider_drag = False
        self.sel_building = None
        self.show_health = True
        self._dead_pending = []
        self.help_open = False
        self.infantry_mode = None
        self.battles = {}
        self._next_battle = 1
        self._combat_t = 0.0
        self.ui_buttons = []
        self.stats_text = ''
        self._stats_timer = 0.0
        self._next_id = 1
        self._frame = 0
        self.blocked = bytearray(COLS * ROWS)
        self.mm_size = (200, max(200, round(60 * MAP_H / MAP_W)))
        self.mm_cache = None
        self.buildings.append(Building('depot', 620, 560))
        self.buildings.append(Building('barracks', 1960, 300))
        self.buildings.append(Building('depot', 2050, 520))
        self._spawn('soldier', 20, 480, 480, 1300, 1300)
        self._spawn('tank', 8, 480, 1340, 1300, 1750)
        self._spawn('engineer', 10, 1400, 480, 1800, 920)
        self._spawn('hero', 2, 380, 1500, 700, 1780)
        self._spawn('esoldier', 10, 2600, 640, 3320, 1380)
        self._spawn('etank', 4, 2600, 1460, 3320, 1980)
        self._spawn('eengineer', 4, 1980, 1680, 2380, 1960)
        self.rebuild_blocked()
        self.camera = [0, 240]
        self.clamp_camera()

    def _add_unit(self, type_, x, y):
        u = Unit(self._next_id, type_, x, y)
        self._next_id += 1
        self.units.append(u)
        return u

    def _spawn(self, type_, n, x0, y0, x1, y1):
        """在区域内随机放置 n 个单位，避开建筑与岩石"""
        placed = 0
        guard = 0
        while placed < n and guard < n * 300:
            guard += 1
            x = random.uniform(x0, x1)
            y = random.uniform(y0, y1)
            ok = True
            for b in self.buildings:
                if abs(x - b.x) * 2 < b.w + 40 and abs(y - b.y) * 2 < b.h + 40:
                    ok = False
                    break
            if ok:
                for (rx, ry, rw, rh) in ROCKS:
                    if abs(x - rx) * 2 < rw + 30 and abs(y - ry) * 2 < rh + 30:
                        ok = False
                        break
            if not ok:
                continue
            self._add_unit(type_, x, y)
            placed += 1

    def get_unit(self, uid):
        for u in self.units:
            if u.id == uid:
                return u
        return None

    @staticmethod
    def clamp(v, a, b):
        if v < a:
            return a
        if v > b:
            return b
        return v

    def clamp_camera(self):
        vis_w = self.view[0] * self.zoom
        vis_h = self.view[1] * self.zoom
        self.camera[0] = self.clamp(self.camera[0], 0, max(0, MAP_W - vis_w))
        self.camera[1] = self.clamp(self.camera[1], 0, max(0, MAP_H - vis_h))

    def screen_to_world(self, sx, sy):
        return (self.camera[0] + sx * self.zoom, self.camera[1] + sy * self.zoom)

    def set_camera_center(self, wx, wy):
        self.camera[0] = wx - self.view[0] * self.zoom / 2
        self.camera[1] = wy - self.view[1] * self.zoom / 2
        self.clamp_camera()

    def mm_rect(self):
        return (self.view[0] - self.mm_size[0] - MM_MARGIN, 54,
                self.mm_size[0], self.mm_size[1])

    def slider_rect(self):
        mm = self.mm_rect()
        return (mm[0] + mm[2] + 8, mm[1], 14, mm[3])

    def minimap_to_world(self, mx, my):
        mm = self.mm_rect()
        wx = (mx - mm[0]) / mm[2] * MAP_W
        wy = (my - mm[1]) / mm[3] * MAP_H
        return (self.clamp(wx, 0, MAP_W), self.clamp(wy, 0, MAP_H))

    def set_zoom(self, z):
        cx = self.camera[0] + self.view[0] * self.zoom / 2
        cy = self.camera[1] + self.view[1] * self.zoom / 2
        self.zoom = z
        self.camera[0] = cx - self.view[0] * self.zoom / 2
        self.camera[1] = cy - self.view[1] * self.zoom / 2
        self.clamp_camera()

    def build_minimap_cache(self):
        w, h = self.mm_size
        surf = pygame.Surface((w, h))
        surf.fill((74, 114, 64))
        for (rx, ry, rw, rh) in ROCKS:
            rect = pygame.Rect(rx / MAP_W * w - rw / MAP_W * w / 2,
                               ry / MAP_H * h - rh / MAP_H * h / 2,
                               rw / MAP_W * w, rh / MAP_H * h)
            pygame.draw.rect(surf, (107, 112, 117), rect)
        for b in self.buildings:
            rect = pygame.Rect(b.x / MAP_W * w - b.w / MAP_W * w / 2,
                               b.y / MAP_H * h - b.h / MAP_H * h / 2,
                               b.w / MAP_W * w, b.h / MAP_H * h)
            pygame.draw.rect(surf, b.color, rect)
        for c in self.constructions:
            rect = pygame.Rect(c.x / MAP_W * w - c.w / MAP_W * w / 2,
                               c.y / MAP_H * h - c.h / MAP_H * h / 2,
                               c.w / MAP_W * w, c.h / MAP_H * h)
            pygame.draw.rect(surf, (230, 230, 220), rect)
        self.mm_cache = surf

    # ---------- 障碍网格 / 寻路 ----------
    def mark_rect(self, cx, cy, cw, ch, v):
        x0 = max(0, math.floor((cx - cw / 2 - GRID) / GRID))
        x1 = min(COLS - 1, math.ceil((cx + cw / 2 + GRID) / GRID))
        y0 = max(0, math.floor((cy - ch / 2 - GRID) / GRID))
        y1 = min(ROWS - 1, math.ceil((cy + ch / 2 + GRID) / GRID))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.blocked[y * COLS + x] = v

    def rebuild_blocked(self):
        for i in range(len(self.blocked)):
            self.blocked[i] = 0
        for (rx, ry, rw, rh) in ROCKS:
            self.mark_rect(rx, ry, rw, rh, 1)
        for b in self.buildings:
            self.mark_rect(b.x, b.y, b.w, b.h, 1)
        for c in self.constructions:
            self.mark_rect(c.x, c.y, c.w, c.h, 1)
        self.build_minimap_cache()

    def is_blocked(self, px, py):
        gx = math.floor(px / GRID)
        gy = math.floor(py / GRID)
        if gx < 0 or gy < 0 or gx >= COLS or gy >= ROWS:
            return True
        return self.blocked[gy * COLS + gx] == 1

    def _phys_blocked(self, px, py, r, ignore=None):
        """物理碰撞判定：单位圆（中心 px,py 半径 r）是否与岩石/建筑真实相交。
        用于单位移动（粗网格含 24px 外扩缓冲，若直接用于移动判定，
        单位被挤入缓冲格后会彻底卡死——压力测试已复现）。
        ignore：可选建筑对象，判定时跳过（供兵营内新兵出门豁免）。"""
        for (rx, ry, rw, rh) in ROCKS:
            if abs(px - rx) * 2 < rw + r * 2 and abs(py - ry) * 2 < rh + r * 2:
                return True
        for b in self.buildings:
            if ignore is not None and b is ignore:
                continue
            if abs(px - b.x) * 2 < b.w + r * 2 and abs(py - b.y) * 2 < b.h + r * 2:
                return True
        for c in self.constructions:
            if abs(px - c.x) * 2 < c.w + r * 2 and abs(py - c.y) * 2 < c.h + r * 2:
                return True
        return False

    def to_free_cell(self, px, py):
        gx = self.clamp(math.floor(px / GRID), 0, COLS - 1)
        gy = self.clamp(math.floor(py / GRID), 0, ROWS - 1)
        if not self.blocked[gy * COLS + gx]:
            return (gx, gy)
        for rad in range(1, 7):
            for dy in range(-rad, rad + 1):
                for dx in range(-rad, rad + 1):
                    if max(abs(dx), abs(dy)) != rad:
                        continue
                    x, y = gx + dx, gy + dy
                    if x < 0 or y < 0 or x >= COLS or y >= ROWS:
                        continue
                    if not self.blocked[y * COLS + x]:
                        return (x, y)
        return None

    def find_path(self, px, py, gx, gy):
        """A*（二叉堆）。返回世界坐标路径点数组；不可达返回 None。"""
        s = self.to_free_cell(px, py)
        g = self.to_free_cell(gx, gy)
        if s is None or g is None:
            return None
        key = lambda x, y: y * COLS + x
        heur = lambda x, y: abs(x - g[0]) + abs(y - g[1])
        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
        open_heap = [(heur(s[0], s[1]), 0, s[0], s[1])]
        came = {}
        cost = {key(s[0], s[1]): 0.0}
        closed = set()
        while open_heap:
            _f, cg, cx, cy = heapq.heappop(open_heap)
            ck = key(cx, cy)
            if cx == g[0] and cy == g[1]:
                path = []
                cur = (g[0], g[1])
                while True:
                    path.insert(0, (cur[0] * GRID + GRID / 2, cur[1] * GRID + GRID / 2))
                    if cur == s:
                        break
                    cur = came.get(key(cur[0], cur[1]))
                    if cur is None:
                        return None
                return path
            if ck in closed:
                continue
            closed.add(ck)
            for dx, dy in dirs:
                nx, ny = cx + dx, cy + dy
                if nx < 0 or ny < 0 or nx >= COLS or ny >= ROWS:
                    continue
                if self.blocked[ny * COLS + nx]:
                    continue
                if dx and dy:   # 对角禁止穿角
                    if self.blocked[cy * COLS + nx] or self.blocked[ny * COLS + cx]:
                        continue
                nk = key(nx, ny)
                if nk in closed:
                    continue
                ng = cg + (1.414 if dx and dy else 1.0)
                if ng < cost.get(nk, math.inf):
                    cost[nk] = ng
                    came[nk] = (cx, cy)
                    heapq.heappush(open_heap, (ng + heur(nx, ny), ng, nx, ny))
        return None

    def _perturb_path(self, path, seed, r):
        """路径横向微扰：按单位 id 给每个路径点加小偏移，
        让多单位的路径略微错开，避免所有人挤在同一条走廊上
        （挤在同一点会触发硬碰撞推回平衡 → 集体卡死）。
        偏移点用单位半径做穿墙检查：窄缺口处偏移会撞墙 → 放弃偏移、保持原路径。"""
        off = ((seed * 7) % 5 - 2) * 3
        if off == 0:
            off = ((seed * 13) % 5 - 2) * 3      # 次哈希，避免存在不微扰的单位
        if off == 0:
            return path
        new = []
        for i, (px, py) in enumerate(path):
            if i == len(path) - 1:            # 终点保持精确，支持精准移动
                new.append((px, py))
                continue
            if i + 1 < len(path):
                dx = path[i + 1][0] - px
                dy = path[i + 1][1] - py
            elif i > 0:
                dx = px - path[i - 1][0]
                dy = py - path[i - 1][1]
            else:
                new.append((px, py))
                continue
            ln = math.hypot(dx, dy)
            if ln < 0.01:
                new.append((px, py))
                continue
            qx, qy = px - dy / ln * off, py + dx / ln * off
            if not self._phys_blocked(qx, qy, r):   # 单位圆不穿墙才偏移
                new.append((qx, qy))
            else:
                new.append((px, py))
        return new

    # ---------- 选择 ----------
    def selected_units(self):
        return [u for u in self.units if u.id in self.selection and u.team == 'player']

    def hit_unit(self, wx, wy):
        best = None
        bd = math.inf
        for u in self.units:
            d = math.hypot(wx - u.x, wy - u.y)
            if d <= u.r + 3 and d < bd:
                best = u
                bd = d
        return best

    def select_same_type_in_view(self, u):
        self.selection.clear()
        x0, y0 = self.camera
        x1 = x0 + self.view[0] * self.zoom
        y1 = y0 + self.view[1] * self.zoom
        for o in self.units:
            if o.team != 'player' or o.type != u.type:
                continue
            if x0 <= o.x <= x1 and y0 <= o.y <= y1:
                self.selection.add(o.id)
        self.refresh_ui()
        self.show_toast('已选中画面内所有%s（%d 个）' % (UNIT_DEF[u.type]['name'], len(self.selection)))

    def do_marquee_select(self, m):
        ax, ay = self.screen_to_world(min(m[0], m[2]), min(m[1], m[3]))
        bx, by = self.screen_to_world(max(m[0], m[2]), max(m[1], m[3]))
        if bx - ax < 3 and by - ay < 3:
            return
        self.selection.clear()
        self.sel_building = None
        for u in self.units:
            if u.team != 'player':
                continue
            if ax <= u.x <= bx and ay <= u.y <= by:
                self.selection.add(u.id)
        self.refresh_ui()
        if self.selection:
            self.show_toast('已选中 %d 个单位' % len(self.selection))

    # ---------- 命令：移动 ----------
    @staticmethod
    def spread_points(tx, ty, n):
        """黄金角螺旋分散：多单位落点均匀分布，避免挤成一团"""
        if n <= 1:
            return [(tx, ty)]
        pts = []
        for i in range(n):
            ang = i * 2.399963            # 黄金角，逐圈错位
            rad = 24 + (i // 7) * 34      # 每 7 个增加一圈半径
            pts.append((tx + math.cos(ang) * rad, ty + math.sin(ang) * rad))
        return pts

    def cancel_construction(self, u):
        u.state = 'idle'
        u.phase = None
        u.path = None
        u.move_target = None
        for c in self.constructions:
            if u.id in c.workers:
                c.workers.remove(u.id)
            if c.active_worker == u.id:
                c.active_worker = None

    def order_move(self, lst, tx, ty):
        """多单位移动：就近分配落点，减少路径交叉，避免全体排成单线"""
        if not lst:
            return
        self.order_point = (tx, ty, self._combat_t)
        pts = self.spread_points(tx, ty, len(lst))
        ordered = sorted(lst, key=lambda u: math.hypot(u.x - tx, u.y - ty))
        unreachable = False
        for u, p in zip(ordered, pts):
            if u.state == 'building':
                self.cancel_construction(u)
            if u.state == 'combat' or u.locked is not None:   # 玩家命令打断战斗
                self._unlock(u)
                u.combat_immune = self._combat_t + COMBAT_IMMUNE   # 豁免：命令后不被立即重新拉入战斗（模拟时钟）
                if u.battle is not None:
                    b = self.battles.get(u.battle)
                    if b is not None:
                        b.units.discard(u.id)
                        b.join_t.pop(u.id, None)
                    u.battle = None
            u.move_target = (p[0], p[1])
            u.path = self.find_path(u.x, u.y, p[0], p[1])
            if u.path is not None:
                u.path = self._perturb_path(u.path, u.id, u.r)   # 路径错开，避免走廊挤死
            u.path_idx = 0
            if u.path is None:
                u.move_target = None
                unreachable = True
        if unreachable:
            self.show_toast('部分目标位置不可达，已原地待命')
        elif len(lst) > 1:
            self.show_toast('%d 个单位执行移动' % len(lst))
        else:
            self.show_toast('%s 执行移动' % UNIT_DEF[lst[0].type]['name'])

    # ---------- 命令：建造 ----------
    def start_place(self, type_):
        if not any(u.type == 'engineer' for u in self.selected_units()):
            self.show_toast('请先选中工兵单位')
            return
        self.place_mode = type_
        self.refresh_ui()

    def cancel_place(self):
        self.place_mode = None
        self.refresh_ui()

    def place_valid(self, type_, cx, cy):
        d = BUILD_DEF[type_]
        if cx - d['w'] / 2 < 4 or cx + d['w'] / 2 > MAP_W - 4 or cy - d['h'] / 2 < 4 or cy + d['h'] / 2 > MAP_H - 4:
            return False
        rect = (cx, cy, d['w'], d['h'])
        for (rx, ry, rw, rh) in ROCKS:
            if abs(rect[0] - rx) * 2 < rect[2] + rw + 8 and abs(rect[1] - ry) * 2 < rect[3] + rh + 8:
                return False
        for b in self.buildings:
            if abs(rect[0] - b.x) * 2 < rect[2] + b.w + 8 and abs(rect[1] - b.y) * 2 < rect[3] + b.h + 8:
                return False
        for c in self.constructions:
            if abs(rect[0] - c.x) * 2 < rect[2] + c.w + 8 and abs(rect[1] - c.y) * 2 < rect[3] + c.h + 8:
                return False
        for u in self.units:
            ccx = self.clamp(u.x, cx - d['w'] / 2, cx + d['w'] / 2)
            ccy = self.clamp(u.y, cy - d['h'] / 2, cy + d['h'] / 2)
            if math.hypot(u.x - ccx, u.y - ccy) < u.r + 2:
                return False
        return True

    def assign_build(self, engs, c):
        sites = [
            (c.x, c.y - c.h / 2 - 26),
            (c.x, c.y + c.h / 2 + 26),
            (c.x - c.w / 2 - 26, c.y),
            (c.x + c.w / 2 + 26, c.y),
        ]
        c.workers = [u.id for u in engs]
        for i, u in enumerate(engs):
            if u.state == 'building':
                self.cancel_construction(u)
            u.state = 'building'
            u.phase = 'moving'
            p = sites[i % 4]
            u.move_target = p
            u.path = self.find_path(u.x, u.y, p[0], p[1])
            u.path_idx = 0

    def try_place(self, cx, cy):
        if self.place_mode is None:
            return
        if not self.place_valid(self.place_mode, cx, cy):
            self.show_toast('无法放置：位置被占用或越界')
            return
        d = BUILD_DEF[self.place_mode]
        engs = [u for u in self.selected_units() if u.type == 'engineer']
        if not engs:
            self.show_toast('请先选中工兵单位')
            return
        c = Construction(self.place_mode, cx, cy)
        self.constructions.append(c)
        self.rebuild_blocked()
        self.assign_build(engs, c)
        self.show_toast('开始建造 %s（%d 名工兵）' % (d['name'], len(engs)))
        self.place_mode = None
        self.refresh_ui()

    # ---------- 更新 ----------
    def update(self, dt):
        self._frame += 1
        self._update_units(dt)
        self._update_combat(dt)
        self._update_constructions(dt)
        self._update_training(dt)
        self._update_hidden(dt)
        self._update_camera(dt)
        if self.toast_t > 0:
            self.toast_t -= dt
            if self.toast_t <= 0:
                self.toast_text = None
        self._stats_timer -= dt
        if self._stats_timer <= 0:
            self._stats_timer = 0.3
            mine = sum(1 for u in self.units if u.team == 'player')
            enemy = sum(1 for u in self.units if u.team == 'enemy')
            queued = sum(len(b.train_queue) for b in self.buildings)
            self.stats_text = '我方单位 %d · 敌方单位 %d · 建筑 %d · 施工中 %d · 训练队列 %d · 缩放 %.1fx' % (
                mine, enemy, len(self.buildings), len(self.constructions), queued, self.zoom)

    # ---------- 单位移动：路径跟随 + 对称分离力 ----------
    # 分离力：被近邻单位推挤时，双方同时向相反方向平滑让开（方向连续、随距离渐变），
    # 取代旧版"对前方单位单侧滑移"——旧法会让单位互相推挤绕圈、剧烈抖动。
    def _in_view(self, u, margin=160):
        """单位是否在相机视野（含边距）内"""
        vx0 = self.camera[0] - margin
        vy0 = self.camera[1] - margin
        vx1 = self.camera[0] + self.view[0] * self.zoom + margin
        vy1 = self.camera[1] + self.view[1] * self.zoom + margin
        return vx0 <= u.x <= vx1 and vy0 <= u.y <= vy1

    def _sep_scale(self, u):
        """RW 软碰撞：战斗单位常驻 0.85（允许 15% 重叠，softCollisionOnAll=12 思路）；
        移动中按 zoom 5%~15% 容忍；静止单位 1.0（0 容忍）。"""
        if u.state == 'combat' and u.locked is not None:
            return 0.85   # 战斗中常驻软碰撞，围攻挤位不震颤
        moving = (u.path and u.path_idx < len(u.path))
        if not moving:
            return 1.0
        z = self.clamp(self.zoom, ZOOM_MIN, ZOOM_MAX)
        f = 0.925 + 0.05 * (z - ZOOM_MIN) / (ZOOM_MAX - ZOOM_MIN)
        if not self._in_view(u):
            f = max(0.925, f * 0.95)
        return f

    # ---------- 步兵战斗：战场扩散 + 时序/距离一对一匹配 ----------
    def _get_combat_unit(self, uid):
        return self.get_unit(uid)

    def _join_battle(self, a, b, t):
        ba = self.battles.get(a.battle) if a.battle is not None else None
        bb = self.battles.get(b.battle) if b.battle is not None else None
        if ba is None and bb is None:
            bid = self._next_battle
            self._next_battle += 1
            btl = Battle(bid, (a.x + b.x) / 2, (a.y + b.y) / 2, BATTLE_RADIUS)
            btl.units.add(a.id); btl.units.add(b.id)
            btl.join_t[a.id] = t; btl.join_t[b.id] = t
            a.battle = bid; b.battle = bid
            self.battles[bid] = btl
        elif ba is not None and bb is None:
            self._battle_add(ba, b, t)
        elif ba is None and bb is not None:
            self._battle_add(bb, a, t)
        elif ba is not bb:
            for uid in list(bb.units):
                self._battle_add(ba, self.get_unit(uid), bb.join_t.get(uid, t))
            del self.battles[bb.id]

    def _battle_add(self, b, u, t):
        if u is None or u.type not in ('soldier', 'esoldier') or u.battle == b.id:
            return
        if u.battle is not None:
            ob = self.battles.get(u.battle)
            if ob is not None and ob is not b:
                ob.units.discard(u.id)
        u.battle = b.id
        b.units.add(u.id)
        if u.id not in b.join_t:
            b.join_t[u.id] = t
        d = math.hypot(u.x - b.cx, u.y - b.cy)   # 扩大战场范围
        need = d + BATTLE_MARGIN
        if need > b.radius:
            b.radius = need

    def _expand_battle(self, b):
        changed = True
        guard = 0
        while changed and guard < 200:
            changed = False
            guard += 1
            for u in self.units:
                if u.hidden or u.state == 'dying' or u.type not in ('soldier', 'esoldier') or u.battle == b.id:
                    continue
                if math.hypot(u.x - b.cx, u.y - b.cy) <= b.radius:
                    self._battle_add(b, u, self._combat_t)
                    changed = True

    def _unlock(self, u):
        """解除战斗锁定"""
        u.locked = None
        if u.state == 'combat':
            u.state = 'idle'

    def _match_battle(self, b):
        units = [self.get_unit(i) for i in list(b.units)]
        units = [u for u in units if u is not None]
        if not units:
            return
        now = self._combat_t
        by_team = {}
        for u in units:
            by_team.setdefault(u.team, []).append(u)
        free = [u for u in units if u.locked is None and u.state != 'dying']
        free.sort(key=lambda u: (b.join_t.get(u.id, now), math.hypot(u.x - b.cx, u.y - b.cy)))
        for u in free:
            if u.locked is not None:
                continue
            if u.combat_immune > now:          # 玩家命令豁免中：暂不匹配
                continue
            enemies = [e for e in by_team.get('enemy' if u.team == 'player' else 'player', []) if e.state != 'dying']   # dying 目标不再参与匹配
            if not enemies:
                continue
            # RW 逻辑：一对一优先（无人锁定的敌人），多对一时直接围攻最近敌人（不查槽位）
            idle = [e for e in enemies
                    if not any(v.locked == e.id for v in units if v is not e)]
            if idle:
                idle.sort(key=lambda e: (b.join_t.get(e.id, now), math.hypot(e.x - u.x, e.y - u.y)))
                tgt = idle[0]
            else:
                # 多对一：所有敌人都被锁定了，直接围攻最近的（RW 软碰撞允许挤）
                tgt = min(enemies, key=lambda e: math.hypot(e.x - u.x, e.y - u.y))
            u.locked = tgt.id
            u.state = 'combat'
            u.path = None
            u.move_target = None
            u.path_idx = 0
            u.att_cd = 0.0

    def _prune_battle(self, bid, b):
        for uid in list(b.units):
            u = self.get_unit(uid)
            if u is None:
                b.units.discard(uid)
                b.join_t.pop(uid, None)
                continue
            if u.state == 'dying':                              # 死亡：移出战场
                b.units.discard(uid)
                b.join_t.pop(uid, None)
                if u.battle == bid:
                    u.battle = None
                continue
            if math.hypot(u.x - b.cx, u.y - b.cy) > b.radius + BATTLE_LEAVE:   # 脱离
                b.units.discard(uid)
                b.join_t.pop(uid, None)
                if u.battle == bid:
                    u.battle = None
                self._unlock(u)
        alive = [self.get_unit(i) for i in list(b.units)]
        alive = [u for u in alive if u is not None]
        has = {}
        for u in alive:
            has[u.team] = has.get(u.team, 0) + 1
        if len(has) < 2:                                    # 只剩一方/无人 → 解散战场
            for u in alive:
                u.battle = None
                self._unlock(u)
            self.battles.pop(bid, None)
        else:
            for u in alive:                                 # 锁定对手过远/已不存在 → 解锁
                if u.locked is not None:
                    t = self.get_unit(u.locked)
                    if t is None or t.battle != bid or math.hypot(t.x - u.x, t.y - u.y) > BATTLE_LEAVE:
                        self._unlock(u)

    def _update_combat(self, dt):
        self._combat_t += dt
        self._build_buckets()
        now = self._combat_t
        for u in self.units:                                # 触发：敌对步兵相聚足够近
            if u.hidden or u.type not in ('soldier', 'esoldier'):
                continue
            if u.combat_immune > now:                       # 玩家命令豁免：不重新触发战斗
                continue
            if u.path is not None and u.path_idx < len(u.path):  # 正在执行玩家移动命令：途中不自动接战（红警/RW行为）
                continue
            for o in self._neighbors(u):
                if o.hidden or o.team == u.team or o.type not in ('soldier', 'esoldier'):
                    continue
                if o.combat_immune > now or o.state == 'dying':
                    continue
                if math.hypot(u.x - o.x, u.y - o.y) < COMBAT_TRIGGER:
                    self._join_battle(u, o, self._combat_t)
        for bid, b in list(self.battles.items()):           # 扩散 → 匹配 → 清理
            self._expand_battle(b)
            self._match_battle(b)
            self._prune_battle(bid, b)

    def _kill_unit(self, t):
        """步兵死亡：切死亡状态、解除锁定/战场，通知所有锁定它的单位"""
        t.state = 'dying'
        t.hp = 0
        t.path = None
        t.move_target = None
        self._unlock(t)                    # 释放 t 锁定的目标方向槽 + 自己的槽
        if t.battle is not None:
            b = self.battles.get(t.battle)
            if b is not None:
                b.units.discard(t.id)
                b.join_t.pop(t.id, None)
            t.battle = None
        for o in self.units:
            if o.locked == t.id:           # 所有锁 t 的攻击者解锁（空出方向槽）
                self._unlock(o)

    def _build_buckets(self):
        CELL = 96
        buckets = {}
        for u in self.units:
            k = (int(u.x // CELL), int(u.y // CELL))
            buckets.setdefault(k, []).append(u)
        self._buckets = buckets
        self._cell = CELL

    def _neighbors(self, u):
        CELL = self._cell
        gx, gy = int(u.x // CELL), int(u.y // CELL)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                lst = self._buckets.get((gx + dx, gy + dy))
                if lst:
                    for o in lst:
                        if o is not u:
                            out.append(o)
        return out

    def _update_units(self, dt):
        self._build_buckets()
        for u in self.units:
            if u.state == 'dying':                           # 死亡：播 die 动画，播完移除
                if u.anim is not None:
                    if u.anim.current != 'die':
                        u.anim.play('die')
                    u.anim.update(dt)
                    if u.anim.frame_i >= 4:                  # 最后一帧播完
                        self._dead_pending.append(u)
                else:
                    self._dead_pending.append(u)
                continue
            if u.anim is None:
                continue
            if u.state == 'combat' and u.locked is not None:   # RW 近战：A*追击，贴脸攻击
                t = self.get_unit(u.locked)
                if t is None or t.state == 'dying':           # 目标消失/死亡 → 解除战斗
                    self._unlock(u)
                    continue
                dx = t.x - u.x
                dy = t.y - u.y
                d = math.hypot(dx, dy)
                reach = max(ATTACK_REACH_BASE, u.r + t.r)    # 贴脸距离 = max(基础, 两半径和)
                if d > CHASE_LEAVE:                           # 目标过远 → 放弃战斗
                    self._unlock(u)
                    continue
                if d > reach:                                 # 未贴脸：走A*追敌人（不直线挤）
                    u.move_target = (t.x, t.y)
                    # 每0.3秒或路径走完时更新寻路目标
                    if u.path is None or u.path_idx >= len(u.path) or (self._combat_t % 0.3) < dt:
                        u.path = self.find_path(u.x, u.y, t.x, t.y)
                        u.path_idx = 0
                    # 不continue，让后面的路径移动逻辑处理（有分离力/绕墙）
                else:                                        # 已贴脸：停下转身攻击
                    u.path = None
                    u.move_target = None
                    u.path_idx = 0
                    if dx > 0.25:
                        u.facing = 1
                    elif dx < -0.25:
                        u.facing = -1
                    u.anim.flip = u.facing < 0
                    if u.anim.current != 'attack':
                        u.anim.play('attack')
                        u.prev_anim_frame = u.anim.frame_i
                    u.anim.update(dt)
                    if u.anim.frame_i < u.prev_anim_frame:   # 动画完成一轮（回绕）= 一次攻击动作
                        t.hp -= DAMAGE                       # 每次攻击动作扣一次血
                        if t.hp <= 0:
                            self._kill_unit(t)
                    u.prev_anim_frame = u.anim.frame_i
                    continue
            moving = u.path is not None and u.path_idx < len(u.path)
            if moving:                 # 移动中：走步动画
                if u.anim.current != 'walk':
                    u.anim.play('walk')
                u.anim.update(dt)
            else:                      # 静止：停在"战斗待命站姿"帧（attack5），不推进帧
                if u.anim.current != 'attack':
                    u.anim.play('attack')
                    u.anim.frame_i = 4
        for u in self.units:
            if not u.path or u.path_idx >= len(u.path):
                continue
            in_view = self._in_view(u)
            tx, ty = u.path[u.path_idx]
            dx, dy = tx - u.x, ty - u.y
            d = math.hypot(dx, dy)
            step = u.speed * (0.85 if not in_view else 1.0) * dt   # 视野外降速系数最大 85%
            is_last = (u.path_idx == len(u.path) - 1)
            if not is_last:
                # 投影通过（红警式航点导航）：单位已越过当前路径点所在平面
                # （沿路径方向在其前方）→ 直接切换下一路径点，位置不变、丝滑滑过；
                # 仅当朝下一段方向两步不穿墙时生效（防拐角内侧切角穿墙）
                nxt = u.path[u.path_idx + 1]
                segx, segy = nxt[0] - tx, nxt[1] - ty
                sln = math.hypot(segx, segy)
                if sln > 0.01 and (dx * segx + dy * segy) < 0:
                    p2x = u.x + segx / sln * step * 2
                    p2y = u.y + segy / sln * step * 2
                    if not self._phys_blocked(p2x, p2y, u.r, ignore=u.home):
                        u.path_idx += 1
                        continue
            # 终点：一步内可达即直接吸附到精确终点（不越过→避免振荡）；
            # 中间点：一步吸附（无大瞬移，配合投影通过自然滑过）
            if (is_last and d <= step) or (not is_last and (d <= 4 or d <= step * 1.1)):
                if self._phys_blocked(tx, ty, u.r, ignore=u.home):
                    self._recompute_path(u)
                    continue
                u.x, u.y = tx, ty
                u.path_idx += 1
                if u.path_idx >= len(u.path):
                    u.path = None
                    if u.state == 'building' and u.phase == 'moving':
                        u.phase = 'building'
                continue
            mx, my = dx / d, dy / d
            sep_f = self._sep_scale(u)
            if in_view:
                # 对称分离力（连续、双方同时让开）；间距基于真实碰撞半径×容忍系数
                sx = sy = 0.0
                for o in self._neighbors(u):
                    ox, oy = u.x - o.x, u.y - o.y
                    od = math.hypot(ox, oy)
                    min_d = (u.r + o.r) * sep_f + 2
                    if od < min_d and od > 0.01:
                        w = (min_d - od) / min_d
                        sx += ox / od * w
                        sy += oy / od * w
                # 钳制分离力上限：避免多单位互挤时分离力与目标方向完全抵消
                # （方向翻转 → 原地打转/死锁），单位始终保留朝目标的分量
                sep = math.hypot(sx, sy)
                if sep > 0.5:
                    sx *= 0.5 / sep
                    sy *= 0.5 / sep
                vx = mx + sx * 1.8
                vy = my + sy * 1.8
                vl = math.hypot(vx, vy)
                if vl < 0.001:
                    vx, vy = mx, my
                    vl = 1.0
                vx, vy = vx / vl, vy / vl
            else:
                # 视野外：直接沿路径方向移动（降速上限 85%），跳过分离力
                # → 计算压力减小；重叠容忍已由 sep_f（视野外 0.85）放大
                vx, vy = mx, my
            # 同向排队（视野外也保留）：前方同向移动单位即将接触时完全等待，
            # 窄口/走廊内单位严格串行通过——否则多单位同时挤缺口会被硬碰撞推冻结
            queued = False
            for o in self._neighbors(u):
                odx, ody = o.x - u.x, o.y - u.y
                od = math.hypot(odx, ody)
                if od > (u.r + o.r) * sep_f + 1 or od < 0.01:
                    continue
                if (odx * vx + ody * vy) / od <= 0.8:
                    continue
                o_moving = o.path is not None and o.path_idx < len(o.path)
                if o_moving:
                    otx, oty = o.path[o.path_idx]
                    odm = math.hypot(otx - o.x, oty - o.y)
                    if odm > 0.01 and ((otx - o.x) / odm * vx + (oty - o.y) / odm * vy) > 0.3:
                        queued = True
                        break
            if queued:
                continue
            nx, ny = u.x + vx * step, u.y + vy * step
            if self._phys_blocked(nx, ny, u.r, ignore=u.home):
                # 沿墙滑动：先试横向再试纵向，避免被墙卡死
                if not self._phys_blocked(nx, u.y, u.r, ignore=u.home):
                    u.x = nx
                elif not self._phys_blocked(u.x, ny, u.r, ignore=u.home):
                    u.y = ny
            else:
                u.x, u.y = nx, ny
            u.angle = math.atan2(vy, vx)
            if u.anim is not None:    # 朝向跟随移动方向（水平分量，死区防抖）
                if vx > 0.25:
                    u.facing = 1
                elif vx < -0.25:
                    u.facing = -1
                u.anim.flip = u.facing < 0
        # 硬碰撞：保证互不重叠（近邻桶加速，每对只处理一次）
        for a in self.units:
            for b in self._neighbors(a):
                if a.id >= b.id:
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                # RW 软碰撞：战斗单位之间推到两半径和*0.88（允许约12%重叠），不是完全不推
                ca = a.state == 'combat' and a.locked is not None
                cb = b.state == 'combat' and b.locked is not None
                if ca and cb:
                    mn = (a.r + b.r) * 0.88
                    if d < mn and d > 0.01:
                        push = (mn - d) / 2
                        nx, ny = dx / d, dy / d
                        a.x -= nx * push
                        a.y -= ny * push
                        b.x += nx * push
                        b.y += ny * push
                    continue
                ma = (a.path is not None and a.path_idx < len(a.path)) or ca
                mb = (b.path is not None and b.path_idx < len(b.path)) or cb
                f = min(self._sep_scale(a), self._sep_scale(b)) if (ma or mb) else 1.0
                mn = (a.r + b.r) * f
                if d < mn and d > 0.01:
                    push = (mn - d) / 2
                    nx, ny = dx / d, dy / d
                    a.x -= nx * push
                    a.y -= ny * push
                    b.x += nx * push
                    b.y += ny * push
        for u in self.units:
            u.x = self.clamp(u.x, u.r, MAP_W - u.r)
            u.y = self.clamp(u.y, u.r, MAP_H - u.r)
            # 硬碰撞可能把单位推进墙内：向最近方向脱离
            if self._phys_blocked(u.x, u.y, u.r, ignore=u.home):
                for (ox, oy) in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                    tx, ty = u.x + ox * 8, u.y + oy * 8
                    if not self._phys_blocked(tx, ty, u.r, ignore=u.home):
                        u.x, u.y = tx, ty
                        break
        if self._dead_pending:                                # 死亡动画播完 → 移除单位
            for u in self._dead_pending:
                if u in self.units:
                    self.units.remove(u)
            self._dead_pending = []

    def _recompute_path(self, u):
        if u.move_target is None:
            u.path = None
            return
        u.path = self.find_path(u.x, u.y, u.move_target[0], u.move_target[1])
        u.path_idx = 0

    def _update_constructions(self, dt):
        remove = []
        for c in self.constructions:
            if not c.workers:                 # 工兵全部离开 → 工地取消
                remove.append(c)
                continue
            if c.progress >= 1:
                self.buildings.append(Building(c.type, c.x, c.y))
                for uid in c.workers:
                    w = self.get_unit(uid)
                    if w:
                        w.state = 'idle'
                        w.phase = None
                remove.append(c)
                self.show_toast('建造完成：%s' % c.name)
                self.refresh_ui()
                continue
            if c.active_worker is not None:
                w = self.get_unit(c.active_worker)
                if w and w.state == 'building' and w.phase == 'building':
                    c.progress = min(1.0, c.progress + dt / BUILD_TIME)
                else:
                    c.active_worker = None   # 施工工兵被打断，等待接替
            for uid in c.workers:             # 已到工地的工兵认领施工
                w = self.get_unit(uid)
                if w is None or w.state != 'building' or w.path:
                    continue
                w.phase = 'building'
                if c.active_worker is None:
                    c.active_worker = uid
        if remove:
            for c in remove:
                if c in self.constructions:
                    self.constructions.remove(c)
            self.rebuild_blocked()

    def _update_training(self, dt):
        """兵营生产：队列计时，完成后在兵营旁生成单位"""
        done = False
        for b in self.buildings:
            if not b.train_queue:
                continue
            b.train_progress += dt / TRAIN_TIME
            if b.train_progress >= 1.0:
                b.train_progress = 0.0
                t = b.train_queue.pop(0)
                self._spawn_trained(b, t)
                self.show_toast('兵营生产完成：%s' % UNIT_DEF[t]['name'])
                done = True
        if done:
            self.refresh_ui()

    def _spawn_trained(self, b, type_):
        """兵营出兵：单位生成在建筑内部"产生位置"（不可见），自动向门口移动。
        内部点取门口内侧；门口 = 兵营门正下方最近一格中心。
        移动期间忽略自家兵营碰撞（物理豁免），走出建筑即解除隐藏。"""
        sx, sy = b.x, b.y + b.h / 2 - 10          # 内部产生位置（门内侧）
        u = self._add_unit(type_, sx, sy)
        u.hidden = True
        u.home = b
        gy = int((b.y + b.h / 2) / GRID) + 1      # 建筑底部下一格 = 门口
        door = (b.x, gy * GRID + GRID / 2)
        u.move_target = door
        # 直线出门：不寻路（起点在建筑内，A* 会把起点外推到远处自由格造成绕行）；
        # 移动物理豁免自家兵营，直接穿过门口；走出建筑碰撞范围即解除隐藏
        u.path = [door]
        u.path_idx = 0

    def _update_hidden(self, dt):
        """走出自家建筑物理碰撞范围即解除隐藏（变为可见、恢复正常碰撞判定）。
        以物理判定为准（建筑半径外扩），保证解除后不会再被自家建筑挡住。"""
        for u in self.units:
            if not u.hidden or u.home is None:
                continue
            if not self._phys_blocked(u.x, u.y, u.r):
                u.hidden = False
                u.home = None

    def _spawn_near(self, b, type_):
        """在建筑旁找一块空地生成单位（避开建筑/岩石）"""
        d = UNIT_DEF[type_]
        gap = d['r'] + 14
        sites = [
            (b.x, b.y - b.h / 2 - gap),
            (b.x, b.y + b.h / 2 + gap),
            (b.x - b.w / 2 - gap, b.y),
            (b.x + b.w / 2 + gap, b.y),
        ]
        for sx, sy in sites:
            if not self._phys_blocked(sx, sy, d['r']):
                return (sx, sy)
        for rad in (30, 50, 80):
            for i in range(8):
                ang = i * math.pi / 4
                sx = b.x + math.cos(ang) * rad
                sy = b.y + math.sin(ang) * rad
                if not self._phys_blocked(sx, sy, d['r']):
                    return (sx, sy)
        return (b.x, b.y + b.h / 2 + gap)

    def start_train(self):
        """当前选中的兵营开始生产步兵（支持排队）"""
        b = self.sel_building
        if b is None or b.type != 'barracks':
            return
        b.train_queue.append('soldier')
        self.show_toast('兵营开始生产步兵（队列 %d 个）' % len(b.train_queue))

    def hit_building(self, wx, wy):
        for b in self.buildings:
            if b.x - b.w / 2 <= wx <= b.x + b.w / 2 and b.y - b.h / 2 <= wy <= b.y + b.h / 2:
                return b
        return None

    def zoom_at(self, sx, sy, factor):
        """以屏幕点 (sx,sy) 为锚点缩放：锚点下的世界坐标保持不动"""
        wx, wy = self.screen_to_world(sx, sy)
        z = self.clamp(self.zoom * factor, ZOOM_MIN, ZOOM_MAX)
        if abs(z - self.zoom) < 0.0001:
            return
        self.zoom = z
        self.camera[0] = wx - sx * z
        self.camera[1] = wy - sy * z
        self.clamp_camera()

    def _update_camera(self, dt):
        dx = dy = 0.0
        if 'w' in self.keys or 'up' in self.keys:
            dy -= 1
        if 's' in self.keys or 'down' in self.keys:
            dy += 1
        if 'a' in self.keys or 'left' in self.keys:
            dx -= 1
        if 'd' in self.keys or 'right' in self.keys:
            dx += 1
        if dx or dy:
            l = math.hypot(dx, dy)
            self.camera[0] += dx / l * 520 * self.zoom * dt
            self.camera[1] += dy / l * 520 * self.zoom * dt
            self.clamp_camera()

    # ---------- UI ----------
    def show_toast(self, msg):
        self.toast_text = msg
        self.toast_t = 2.2

    def refresh_ui(self):
        self.ui_buttons = []
        if self.place_mode:
            return
        if self.sel_building is not None:
            if self.sel_building.type == 'barracks':
                bw, bh = 128, 38
                x0 = self.view[0] - 18 - bw
                y0 = self.view[1] - 54
                self.ui_buttons.append({'rect': (x0, y0, bw, bh), 'type': 'train_soldier'})
            return
        sel = self.selected_units()
        if not sel:
            return
        has_eng = any(u.type == 'engineer' for u in sel)
        if not has_eng:
            # 步兵三状态（本轮只做 UI）：积极寻敌 / 守卫 / 撤退
            if any(u.type == 'soldier' for u in sel):
                bw, bh = 112, 38
                gap = 8
                modes = [('inf_attack', '积极寻敌'), ('inf_guard', '守卫'), ('inf_retreat', '撤退')]
                total = len(modes) * bw + (len(modes) - 1) * gap
                x0 = self.view[0] - total - 18
                y0 = self.view[1] - 54
                for i, (t, label) in enumerate(modes):
                    self.ui_buttons.append({'rect': (x0 + i * (bw + gap), y0, bw, bh), 'type': t, 'label': label})
            return
        bw, bh = 112, 38
        gap = 8
        total = len(BUILD_DEF) * bw + (len(BUILD_DEF) - 1) * gap
        x0 = self.view[0] - total - 18
        y0 = self.view[1] - 54
        for i, t in enumerate(BUILD_DEF):
            self.ui_buttons.append({'rect': (x0 + i * (bw + gap), y0, bw, bh), 'type': t})

    def click_build_button(self, pos):
        for b in self.ui_buttons:
            x, y, w, h = b['rect']
            if x <= pos[0] <= x + w and y <= pos[1] <= y + h:
                if b['type'] in ('inf_attack', 'inf_guard', 'inf_retreat'):
                    self.infantry_mode = b['type']
                    label = {'inf_attack': '积极寻敌', 'inf_guard': '守卫', 'inf_retreat': '撤退'}[b['type']]
                    self.show_toast('功能开发中：%s（已记录选择状态）' % label)
                elif b['type'] == 'train_soldier':
                    self.start_train()
                else:
                    self.start_place(b['type'])
                return True
        return False

    # ---------- 输入辅助：命中 UI 控件 ----------
    def hit_minimap(self, pos):
        mm = self.mm_rect()
        return mm[0] <= pos[0] <= mm[0] + mm[2] and mm[1] <= pos[1] <= mm[1] + mm[3]

    def hit_slider(self, pos):
        sl = self.slider_rect()
        return sl[0] <= pos[0] <= sl[0] + sl[2] and sl[1] <= pos[1] <= sl[1] + sl[3]

    def set_zoom_from_slider_y(self, y):
        sl = self.slider_rect()
        t = 1.0 - (y - sl[1] - 6) / max(1, sl[3] - 12)
        self.set_zoom(ZOOM_MIN + t * (ZOOM_MAX - ZOOM_MIN))


# ==================== 渲染 ====================
_FONT_PATH = None
_font_cache = {}

def load_font():
    paths = [
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/msyhbd.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
    ]
    for p in paths:
        try:
            f = pygame.font.Font(p, 12)
            if f:
                return p
        except Exception:
            continue
    return None

def get_font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(_FONT_PATH, size) if _FONT_PATH else pygame.font.Font(None, size)
    return _font_cache[size]

def draw_text(surf, text, size, color, x, y, center=False):
    f = get_font(size)
    img = f.render(text, True, color)
    r = img.get_rect()
    if center:
        r.center = (int(x), int(y))
    else:
        r.topleft = (int(x), int(y))
    surf.blit(img, r)

def gear_rect(W):
    """右上角设置（齿轮）图标区域"""
    return (W - 54, 10, 28, 28)

def help_rect(g):
    """帮助面板矩形：小地图正下方"""
    mm = g.mm_rect()
    pw, ph = 252, 220
    return (mm[0] + mm[2] - pw, mm[1] + mm[3] + 16, pw, ph)

def health_row_rect(g):
    """面板内"显示血条"开关行区域（点击切换）"""
    hx, hy, hw, hh = help_rect(g)
    return (hx + 8, hy + 8 + 9 * 19, hw - 16, 18)

def _in_rect(pos, r):
    return r[0] <= pos[0] <= r[0] + r[2] and r[1] <= pos[1] <= r[1] + r[3]

def draw_gear(surf, cx, cy, r=14, col=(232, 238, 218)):
    """简易齿轮：8 齿辐条 + 中心圆孔"""
    pygame.draw.circle(surf, (34, 42, 32), (cx, cy), r + 3)
    pygame.draw.circle(surf, (90, 105, 80), (cx, cy), r + 3, 1)
    for i in range(8):
        a = i * math.pi / 4
        x1 = cx + math.cos(a) * r * 0.62
        y1 = cy + math.sin(a) * r * 0.62
        x2 = cx + math.cos(a) * r * 0.98
        y2 = cy + math.sin(a) * r * 0.98
        pygame.draw.line(surf, col, (x1, y1), (x2, y2), 4)
    pygame.draw.circle(surf, col, (cx, cy), r * 0.68)
    pygame.draw.circle(surf, (24, 30, 19), (cx, cy), r * 0.36)

def label_size(g, base):
    """文字标签随缩放调整，但限制在可读范围"""
    return max(8, min(24, round(base / g.zoom)))

def draw(surf, g):
    W, H = g.view[0], g.view[1]
    z = g.zoom
    cx, cy = g.camera[0], g.camera[1]
    tsx = lambda wx: (wx - cx) / z
    tsy = lambda wy: (wy - cy) / z

    surf.fill((21, 26, 18))                     # 地图外深色背景
    surf.fill((74, 114, 64), pygame.Rect(round(tsx(0)), round(tsy(0)), round(MAP_W / z), round(MAP_H / z)))

    # 网格线（可见范围）
    lw = max(1, round(1 / z))
    gcol = (50, 88, 40)
    x0 = math.floor(cx / GRID) * GRID
    x1 = min(MAP_W, cx + W * z + GRID)
    y0 = math.floor(cy / GRID) * GRID
    y1 = min(MAP_H, cy + H * z + GRID)
    x = x0
    while x <= x1:
        pygame.draw.line(surf, gcol, (round(tsx(x)), round(tsy(y0))), (round(tsx(x)), round(tsy(y1))), lw)
        x += GRID
    y = y0
    while y <= y1:
        pygame.draw.line(surf, gcol, (round(tsx(x0)), round(tsy(y))), (round(tsx(x1)), round(tsy(y))), lw)
        y += GRID

    # 岩石
    for (rx, ry, rw, rh) in ROCKS:
        rect = pygame.Rect(round(tsx(rx - rw / 2)), round(tsy(ry - rh / 2)),
                           round(rw / z), round(rh / z))
        pygame.draw.rect(surf, (107, 112, 117), rect)
        pygame.draw.rect(surf, (69, 73, 77), rect, max(1, round(2 / z)))
        draw_text(surf, '岩石', label_size(g, 10), (200, 205, 210), rect.centerx, rect.centery, center=True)

    # 施工中工地
    for c in g.constructions:
        rect = pygame.Rect(round(tsx(c.x - c.w / 2)), round(tsy(c.y - c.h / 2)),
                           round(c.w / z), round(c.h / z))
        pygame.draw.rect(surf, (207, 216, 200), rect, 1, border_radius=0)
        pygame.draw.rect(surf, (207, 216, 200), rect, max(1, round(2 / z)))
        bw, bh = c.w / z, 8
        bx, by = tsx(c.x - c.w / 2), tsy(c.y + c.h / 2 + 12)
        pygame.draw.rect(surf, (0, 0, 0), pygame.Rect(round(bx), round(by), round(bw), round(bh)))
        pygame.draw.rect(surf, (111, 207, 122), pygame.Rect(round(bx), round(by), round(bw * c.progress), round(bh)))
        draw_text(surf, '建造中 %d%%' % (c.progress * 100), label_size(g, 11), (232, 238, 218),
                  tsx(c.x), by + bh + 6, center=True)

    # 建筑
    for b in g.buildings:
        rect = pygame.Rect(round(tsx(b.x - b.w / 2)), round(tsy(b.y - b.h / 2)),
                           round(b.w / z), round(b.h / z))
        pygame.draw.rect(surf, b.color, rect)
        pygame.draw.rect(surf, b.edge, rect, max(1, round(2 / z)))
        draw_text(surf, b.name, label_size(g, 12), (240, 245, 235), rect.centerx, rect.centery - 6, center=True)
        if b.type == 'barracks':
            pygame.draw.rect(surf, (0, 0, 0), pygame.Rect(rect.centerx - round(9 / z), rect.bottom - round(14 / z),
                                                          round(18 / z), round(14 / z)))
        elif b.type == 'turret':
            pygame.draw.rect(surf, (51, 51, 51), pygame.Rect(rect.centerx - round(4 / z), rect.top - round(12 / z),
                                                             round(8 / z), round(12 / z)))
            pygame.draw.circle(surf, (34, 34, 34), (rect.centerx, rect.top - round(12 / z)), max(1, round(5 / z)))
        elif b.type == 'depot':
            s = max(2, round(14 / z))
            for ox in (-b.w / 2 + 8, -7, b.w / 2 - 22):
                pygame.draw.rect(surf, (255, 255, 255),
                                 pygame.Rect(round(tsx(b.x + ox)), round(tsy(b.y + b.h / 2 - 22)), s, s))
        # 训练进度条（兵营生产时显示在建筑内部顶部）
        if b.type == 'barracks' and (b.train_queue or b.train_progress > 0):
            pbw = round(b.w / z * 0.8)
            pbx = rect.centerx - pbw // 2
            pby = rect.top + round(8 / z)
            pbh = max(3, round(6 / z))
            pygame.draw.rect(surf, (0, 0, 0), pygame.Rect(pbx, pby, pbw, pbh))
            pygame.draw.rect(surf, (111, 207, 122), pygame.Rect(pbx, pby, round(pbw * b.train_progress), pbh))
            draw_text(surf, '训练中 %d%%' % (b.train_progress * 100), label_size(g, 10), (255, 207, 110),
                      rect.centerx, pby + pbh + 4, center=True)

    # 建筑选中高亮
    if g.sel_building is not None:
        b = g.sel_building
        rect = pygame.Rect(round(tsx(b.x - b.w / 2)), round(tsy(b.y - b.h / 2)),
                           round(b.w / z), round(b.h / z))
        pygame.draw.rect(surf, (169, 212, 255), rect, max(2, round(2 / z)))

    # 单位（hidden：兵营内部产生中，不绘制）——半俯视：按世界 y 排序绘制（靠下/靠前最后画）
    for u in sorted((u for u in g.units if not u.hidden), key=lambda u: u.y):
        sx, sy = tsx(u.x), tsy(u.y)
        rr = max(2, round(u.r / z))
        label_off = rr + 2
        if u.anim is not None:
            # 步兵：播放中的精灵帧，随缩放缓存；脚底（midbottom）锚定在世界坐标（半俯视）
            wpx = max(8, round(SPRITE_WORLD / z))
            key = (u.race, u.anim.frame_i, u.anim.flip, wpx)
            img = _SPRITE_CACHE.get(key)
            if img is None:
                base = u.anim.image()
                if base is not None:
                    img = pygame.transform.smoothscale(base, (wpx, wpx))
                    _SPRITE_CACHE[key] = img
            if len(_SPRITE_CACHE) > 600:      # 防缩放档位累积失控
                _SPRITE_CACHE.clear()
            if img is not None:
                surf.blit(img, img.get_rect(midbottom=(round(sx), round(sy))))
                label_off = wpx // 2 + 2
        else:
            pygame.draw.circle(surf, u.color, (round(sx), round(sy)), rr)
            pygame.draw.circle(surf, (0, 0, 0), (round(sx), round(sy)), rr, 1)
            if u.type == 'hero':
                pts = []
                R = u.r / z * 0.6
                for i in range(5):
                    a = -math.pi / 2 + i * 2 * math.pi / 5
                    a2 = a + math.pi / 5
                    pts.append((sx + math.cos(a) * R, sy + math.sin(a) * R))
                    pts.append((sx + math.cos(a2) * R * 0.45, sy + math.sin(a2) * R * 0.45))
                pygame.draw.polygon(surf, (255, 248, 225), pts)
            elif u.type in ('soldier', 'esoldier'):
                ang = u.angle
                pygame.draw.line(surf, (42, 47, 38),
                                 (sx + math.cos(ang) * u.r / z * 0.2, sy + math.sin(ang) * u.r / z * 0.2),
                                 (sx + math.cos(ang) * u.r / z * 1.5, sy + math.sin(ang) * u.r / z * 1.5),
                                 max(1, round(3 / z)))
            elif u.type in ('engineer', 'eengineer'):
                wl = u.r / z * 0.38
                pygame.draw.line(surf, (244, 247, 238), (sx - wl, sy), (sx + wl, sy), max(1, round(4 / z)))
                pygame.draw.line(surf, (244, 247, 238), (sx, sy - wl), (sx, sy + wl), max(1, round(4 / z)))
            elif u.type in ('tank', 'etank'):
                pygame.draw.rect(surf, u.color, pygame.Rect(round(sx - u.r / z), round(sy - u.r / z * 0.72),
                                                            round(u.r * 2 / z), round(u.r * 1.44 / z)))
                ang = u.angle
                pygame.draw.line(surf, (47, 47, 47),
                                 (sx + math.cos(ang) * u.r / z * 0.5, sy + math.sin(ang) * u.r / z * 0.5),
                                 (sx + math.cos(ang) * u.r / z * 2.0, sy + math.sin(ang) * u.r / z * 2.0),
                                 max(1, round(6 / z)))
                pygame.draw.circle(surf, (57, 66, 74), (round(sx), round(sy)), max(1, round(u.r * 0.5 / z)))
        if u.hp > 0 and g.show_health:                       # 血条（头顶，随缩放）
            bw = max(12, round(18 / z))
            bh = max(2, round(3 / z))
            bx = round(sx - bw / 2)
            by = round(sy - label_off * 2 - 6 - bh)
            pygame.draw.rect(surf, (0, 0, 0), pygame.Rect(bx, by, bw, bh))
            frac = max(0.0, min(1.0, u.hp / u.max_hp))
            if frac > 0.5:
                hcol = (92, 200, 92)
            elif frac > 0.25:
                hcol = (222, 196, 74)
            else:
                hcol = (216, 74, 60)
            pygame.draw.rect(surf, hcol, pygame.Rect(bx, by, max(1, round(bw * frac)), bh))
        if u.state == 'building':
            draw_text(surf, '建造中', label_size(g, 10), (255, 207, 110), sx, sy + label_off + 12, center=True)

    # 选中标记：单位脚下很小的实心高亮圆点（固定屏幕尺寸，不随缩放变大）
    for uid in g.selection:
        u = g.get_unit(uid)
        if u is None:
            continue
        sx, sy = tsx(u.x), tsy(u.y)
        pygame.draw.circle(surf, (255, 226, 96), (round(sx), round(sy) + 1), 3)

    # 框选
    if g.marquee:
        m = g.marquee
        ax, ay = g.screen_to_world(min(m[0], m[2]), min(m[1], m[3]))
        bx, by = g.screen_to_world(max(m[0], m[2]), max(m[1], m[3]))
        w = (bx - ax) / z
        h = (by - ay) / z
        sel_surf = pygame.Surface((max(1, round(w)), max(1, round(h))), pygame.SRCALPHA)
        sel_surf.fill((120, 180, 255, 46))
        surf.blit(sel_surf, (round(tsx(ax)), round(tsy(ay))))
        pygame.draw.rect(surf, (127, 178, 255), pygame.Rect(round(tsx(ax)), round(tsy(ay)), round(w), round(h)), 1)

    # 命令标记
    if g.order_point:
        age = g._combat_t - g.order_point[2]
        if age > 0.9:
            g.order_point = None
        else:
            ox, oy = tsx(g.order_point[0]), tsy(g.order_point[1])
            col = (255, 220, 120)
            pygame.draw.circle(surf, col, (round(ox), round(oy)), max(3, round(9 / z)), 1)
            pygame.draw.line(surf, col, (ox - 14, oy), (ox + 14, oy))
            pygame.draw.line(surf, col, (ox, oy - 14), (ox, oy + 14))

    # 放置预览
    if g.place_mode:
        d = BUILD_DEF[g.place_mode]
        px, py = g.hover_w[0], g.hover_w[1]
        ok = g.place_valid(g.place_mode, px, py)
        rect = pygame.Rect(round(tsx(px - d['w'] / 2)), round(tsy(py - d['h'] / 2)),
                           round(d['w'] / z), round(d['h'] / z))
        color = (111, 207, 122) if ok else (224, 85, 85)
        pv = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pv.fill((color[0], color[1], color[2], 90))
        surf.blit(pv, (rect.x, rect.y))
        pygame.draw.rect(surf, color, rect, max(1, round(2 / z)))
        draw_text(surf, d['name'] + ('（可放置）' if ok else '（不可放置）'), label_size(g, 12), color,
                  rect.centerx, rect.top - 6, center=True)

    # 地图边界
    pygame.draw.rect(surf, (94, 122, 74), pygame.Rect(round(tsx(0)), round(tsy(0)), round(MAP_W / z), round(MAP_H / z)),
                     max(1, round(2 / z)))

    # ---------- UI 面板（不随缩放） ----------
    pygame.draw.rect(surf, (24, 30, 19), pygame.Rect(0, 0, W, 44))
    pygame.draw.line(surf, (60, 70, 52), (0, 44), (W, 44))
    draw_text(surf, '2D 即时战略原型', 15, (217, 223, 200), 14, 10)
    draw_text(surf, '原生版 · 大地图 3600x2600 · 工兵建造 · 兵营生产', 11, (154, 168, 138), 170, 15)
    draw_text(surf, g.stats_text, 12, (200, 210, 182), W - 14, 14)

    bar_h = 64
    pygame.draw.rect(surf, (24, 30, 19), pygame.Rect(0, H - bar_h, W, bar_h))
    pygame.draw.line(surf, (60, 70, 52), (0, H - bar_h), (W, H - bar_h))

    if g.place_mode:
        draw_text(surf, '放置模式：%s　移动鼠标预览，左键放置，右键 / Esc 取消' % BUILD_DEF[g.place_mode]['name'],
                  13, (217, 223, 200), 14, H - bar_h + 22)
    elif g.sel_building is not None:
        b = g.sel_building
        draw_text(surf, '已选中建筑：%s（%dx%d）' % (b.name, b.w, b.h), 13, (217, 223, 200), 14, H - bar_h + 12)
        if b.type == 'barracks':
            if b.train_queue:
                draw_text(surf, '生产队列：步兵 ×%d　当前进度 %d%%' % (len(b.train_queue), b.train_progress * 100),
                          11, (154, 168, 138), 14, H - bar_h + 34)
            else:
                draw_text(surf, '点击右侧按钮生产步兵（耗时 %.0f 秒/个）' % TRAIN_TIME,
                          11, (154, 168, 138), 14, H - bar_h + 34)
            for btn in g.ui_buttons:
                rect = pygame.Rect(btn['rect'])
                pygame.draw.rect(surf, (38, 48, 31), rect)
                pygame.draw.rect(surf, (75, 93, 63), rect, 1)
                draw_text(surf, '生产步兵', 12, (217, 223, 200), rect.centerx, rect.y + 8, center=True)
                draw_text(surf, '队列 %d · %.0fs/个' % (len(b.train_queue), TRAIN_TIME), 10, (154, 168, 138),
                          rect.centerx, rect.y + 26, center=True)
        else:
            draw_text(surf, '该建筑无生产功能', 11, (154, 168, 138), 14, H - bar_h + 34)
    else:
        sel = g.selected_units()
        if sel:
            types = {}
            for u in sel:
                types[u.name] = types.get(u.name, 0) + 1
            desc = '、'.join(n + (' ×%d' % c if c > 1 else '') for n, c in types.items())
            draw_text(surf, '已选中：%s' % desc, 13, (217, 223, 200), 14, H - bar_h + 12)
            draw_text(surf, '右键点击地面下达移动命令', 11, (154, 168, 138), 14, H - bar_h + 34)
            for b in g.ui_buttons:
                rect = pygame.Rect(b['rect'])
                if b['type'] in ('inf_attack', 'inf_guard', 'inf_retreat'):
                    active = g.infantry_mode == b['type']
                    base = {'inf_attack': (54, 96, 46), 'inf_guard': (104, 98, 40),
                            'inf_retreat': (102, 48, 42)}[b['type']]
                    bg = tuple(min(255, c + 22) for c in base) if active else base
                    pygame.draw.rect(surf, bg, rect)
                    pygame.draw.rect(surf, (217, 223, 200) if active else (75, 93, 63), rect, 1)
                    draw_text(surf, b.get('label', ''), 12, (217, 223, 200),
                              rect.centerx, rect.y + 6, center=True)
                    draw_text(surf, '开发中', 10, (200, 210, 182), rect.centerx, rect.y + 22, center=True)
                else:
                    active = g.place_mode == b['type']
                    pygame.draw.rect(surf, (51, 69, 44) if active else (38, 48, 31), rect)
                    pygame.draw.rect(surf, (111, 207, 122) if active else (75, 93, 63), rect, 1)
                    draw_text(surf, BUILD_DEF[b['type']]['name'], 12, (217, 223, 200),
                              rect.centerx, rect.y + 6, center=True)
                    draw_text(surf, '%dx%d' % (BUILD_DEF[b['type']]['w'], BUILD_DEF[b['type']]['h']),
                              10, (154, 168, 138), rect.centerx, rect.y + 22, center=True)
    # 右上角设置（齿轮）：点击后弹出操作说明
    gr = gear_rect(g.view[0])
    draw_gear(surf, gr[0] + gr[2] // 2, gr[1] + gr[3] // 2)
    if g.help_open:
        hx, hy, hw, hh = help_rect(g)
        hb = pygame.Surface((hw, hh), pygame.SRCALPHA)
        hb.fill((20, 26, 16, 222))
        surf.blit(hb, (hx, hy))
        pygame.draw.rect(surf, (90, 105, 80), pygame.Rect(hx, hy, hw, hh), 1)
        lines = [
            ('操作说明', 12, (232, 238, 218)),
            ('左键 点击 / 框选 单位', 11, (200, 210, 182)),
            ('双击 单位 → 全选画面内同类', 11, (200, 210, 182)),
            ('右键 点击地面 → 移动命令', 11, (200, 210, 182)),
            ('中键拖动 → 平移地图（仅中键）', 11, (200, 210, 182)),
            ('滚轮 以鼠标位置缩放地图', 11, (200, 210, 182)),
            ('小地图 点击/拖动 → 跳转视角', 11, (200, 210, 182)),
            ('点选兵营 → 生产步兵（排队）', 11, (200, 210, 182)),
            ('滑块 缩放 0.5x-2.0x · Esc 取消', 11, (200, 210, 182)),
        ]
        for i, (txt, size, col) in enumerate(lines):
            draw_text(surf, txt, size, col, hx + 12, hy + 8 + i * 19)
        hr = health_row_rect(g)
        pygame.draw.rect(surf, (70, 86, 60), pygame.Rect(hr))
        hcol = (111, 207, 122) if g.show_health else (216, 74, 60)
        draw_text(surf, '显示血条：%s（点击切换）' % ('开' if g.show_health else '关'), 11,
                  hcol, hr[0] + 8, hr[1] + 3)

    # 小地图 + 缩放滑块
    draw_minimap(surf, g)
    draw_slider(surf, g)

    # Toast
    if g.toast_text:
        f = get_font(13)
        img = f.render(g.toast_text, True, (232, 238, 218))
        tw, th = img.get_width() + 24, 30
        tx, ty = W / 2 - tw / 2, H - bar_h - 40
        pygame.draw.rect(surf, (24, 30, 19), pygame.Rect(tx, ty, tw, th))
        pygame.draw.rect(surf, (90, 105, 80), pygame.Rect(tx, ty, tw, th), 1)
        surf.blit(img, (tx + 12, ty + 7))

def draw_minimap(surf, g):
    mm = g.mm_rect()
    w, h = mm[2], mm[3]
    if g.mm_cache:
        surf.blit(g.mm_cache, (mm[0], mm[1]))
    # 视口矩形
    vx = g.camera[0] / MAP_W * w
    vy = g.camera[1] / MAP_H * h
    vw = g.view[0] * g.zoom / MAP_W * w
    vh = g.view[1] * g.zoom / MAP_H * h
    pygame.draw.rect(surf, (255, 255, 255), pygame.Rect(round(mm[0] + vx), round(mm[1] + vy),
                                                        max(2, round(vw)), max(2, round(vh))), 1)
    # 单位点（hidden 不显示）
    for u in g.units:
        if u.hidden:
            continue
        ux = mm[0] + u.x / MAP_W * w
        uy = mm[1] + u.y / MAP_H * h
        col = (111, 207, 122) if u.team == 'player' else (224, 85, 85)
        pygame.draw.circle(surf, col, (round(ux), round(uy)), 2)
    # 边框
    pygame.draw.rect(surf, (90, 105, 80), pygame.Rect(mm[0], mm[1], w, h), 1)
    draw_text(surf, '小地图', 10, (217, 223, 200), mm[0] + 4, mm[1] - 15)

def draw_slider(surf, g):
    sl = g.slider_rect()
    pygame.draw.rect(surf, (34, 42, 32), pygame.Rect(sl[0], sl[1], sl[2], sl[3]))
    pygame.draw.rect(surf, (90, 105, 80), pygame.Rect(sl[0], sl[1], sl[2], sl[3]), 1)
    pygame.draw.line(surf, (120, 140, 110), (sl[0] + sl[2] // 2, sl[1] + 8),
                     (sl[0] + sl[2] // 2, sl[1] + sl[3] - 8), 2)
    t = (g.zoom - ZOOM_MIN) / (ZOOM_MAX - ZOOM_MIN)
    hy = sl[1] + 8 + (1 - t) * (sl[3] - 20)
    pygame.draw.rect(surf, (217, 223, 200), pygame.Rect(sl[0] + 2, round(hy), sl[2] - 4, 14))
    draw_text(surf, '%.1fx' % g.zoom, 10, (217, 223, 200), sl[0] + sl[2] // 2, sl[1] + sl[3] + 4, center=True)

# ==================== 事件循环 ====================
def main(smoke=False):
    pygame.init()
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    pygame.display.set_caption('2D 即时战略原型 - 原生版')
    clock = pygame.time.Clock()
    g = Game()
    g.view = list(screen.get_size())
    g.clamp_camera()
    g.refresh_ui()
    if _SPRITE_FAIL[0]:
        g.show_toast('未找到步兵素材目录(rts-assets)：步兵退化为几何图形')
    else:
        g.show_toast('步兵素材加载完成：框选/右键移动可看到小人行走')

    global _FONT_PATH
    _FONT_PATH = load_font()

    lmb_consumed = False
    running = True
    frames = 0
    while running:
        dt = min(0.05, clock.tick(60) / 1000.0)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                key = ev.key
                if key == pygame.K_ESCAPE:
                    if g.help_open:
                        g.help_open = False
                    elif g.place_mode:
                        g.cancel_place()
                    else:
                        g.selection.clear()
                        g.sel_building = None
                        g.refresh_ui()
                else:
                    mapping = {
                        pygame.K_w: 'w', pygame.K_a: 'a', pygame.K_s: 's', pygame.K_d: 'd',
                        pygame.K_UP: 'up', pygame.K_DOWN: 'down', pygame.K_LEFT: 'left', pygame.K_RIGHT: 'right',
                    }
                    if key in mapping:
                        g.keys.add(mapping[key])
            elif ev.type == pygame.KEYUP:
                mapping = {
                    pygame.K_w: 'w', pygame.K_a: 'a', pygame.K_s: 's', pygame.K_d: 'd',
                    pygame.K_UP: 'up', pygame.K_DOWN: 'down', pygame.K_LEFT: 'left', pygame.K_RIGHT: 'right',
                }
                if ev.key in mapping:
                    g.keys.discard(mapping[ev.key])
            elif ev.type == pygame.MOUSEMOTION:
                g.mouse_pos = ev.pos
                g.mouse_on = True
                g.hover_w = list(g.screen_to_world(*ev.pos))
                if g.mid_down is not None:
                    st, cam = g.mid_down['pos'], g.mid_down['cam']
                    if math.hypot(ev.pos[0] - st[0], ev.pos[1] - st[1]) > 6:
                        g.mid_down['moved'] = True
                        g.camera = [cam[0] - (ev.pos[0] - st[0]) * g.zoom,
                                    cam[1] - (ev.pos[1] - st[1]) * g.zoom]
                        g.clamp_camera()
                if g.left_down is not None:
                    if math.hypot(ev.pos[0] - g.left_down['pos'][0], ev.pos[1] - g.left_down['pos'][1]) > 6:
                        g.left_down['moved'] = True
                        if g.marquee:
                            g.marquee[2] = ev.pos[0]
                            g.marquee[3] = ev.pos[1]
                if g.mm_drag:
                    g.set_camera_center(*g.minimap_to_world(*ev.pos))
                if g.slider_drag:
                    g.set_zoom_from_slider_y(ev.pos[1])
            elif ev.type == pygame.MOUSEWHEEL:
                if 44 <= g.mouse_pos[1] <= g.view[1] - 64:
                    g.zoom_at(g.mouse_pos[0], g.mouse_pos[1], 1.15 ** ev.y)
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    gr = gear_rect(g.view[0])
                    if _in_rect(ev.pos, gr):
                        g.help_open = not g.help_open
                        lmb_consumed = True
                    elif g.help_open and _in_rect(ev.pos, help_rect(g)):
                        if _in_rect(ev.pos, health_row_rect(g)):
                            g.show_health = not g.show_health
                            g.show_toast('血条显示：%s' % ('开' if g.show_health else '关'))
                        else:
                            g.help_open = False
                        lmb_consumed = True
                    elif g.hit_minimap(ev.pos):
                        lmb_consumed = True
                        g.mm_drag = True
                        g.set_camera_center(*g.minimap_to_world(*ev.pos))
                    elif g.hit_slider(ev.pos):
                        lmb_consumed = True
                        g.slider_drag = True
                        g.set_zoom_from_slider_y(ev.pos[1])
                    elif g.click_build_button(ev.pos):
                        lmb_consumed = True
                    else:
                        lmb_consumed = False
                        g.left_down = {'pos': ev.pos, 'moved': False}
                        g.marquee = [ev.pos[0], ev.pos[1], ev.pos[0], ev.pos[1]]
                elif ev.button == 2:
                    g.mid_down = {'pos': ev.pos, 'cam': list(g.camera), 'moved': False}
                elif ev.button == 3:
                    g.right_down = {'pos': ev.pos, 'cam': list(g.camera), 'moved': False}
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    was_ui = lmb_consumed
                    lmb_consumed = False
                    g.mm_drag = False
                    g.slider_drag = False
                    if was_ui or g.left_down is None:
                        g.left_down = None
                        g.marquee = None
                        continue
                    moved = g.left_down['moved']
                    g.left_down = None
                    if moved:
                        g.do_marquee_select(g.marquee)
                        g.marquee = None
                    else:
                        wx, wy = g.screen_to_world(*ev.pos)
                        if g.place_mode:
                            g.try_place(wx, wy)
                        else:
                            bb = g.hit_building(wx, wy)
                            if bb is not None:
                                g.sel_building = bb
                                g.selection.clear()
                                g.refresh_ui()
                            else:
                                g.sel_building = None
                                hit = g.hit_unit(wx, wy)
                                if hit and hit.team == 'player':
                                    now = time.time()
                                    dbl = (g.last_click is not None and now - g.last_click[0] < DOUBLE_CLICK_MS
                                           and g.last_click[1] == hit.id)
                                    g.last_click = (now, hit.id)
                                    if dbl:
                                        g.select_same_type_in_view(hit)
                                    else:
                                        g.selection.clear()
                                        g.selection.add(hit.id)
                                        g.refresh_ui()
                                else:
                                    g.selection.clear()
                                    g.refresh_ui()
                        g.marquee = None
                elif ev.button == 2 and g.mid_down is not None:
                    g.mid_down = None
                elif ev.button == 3 and g.right_down is not None:
                    g.right_down = None
                    wx, wy = g.screen_to_world(*ev.pos)
                    if g.place_mode:
                        g.cancel_place()
                    else:
                        sel = g.selected_units()
                        if sel:
                            g.order_move(sel, wx, wy)
            elif ev.type == pygame.VIDEORESIZE:
                g.view = list(ev.size)
                g.clamp_camera()
                g.refresh_ui()
            elif ev.type == pygame.WINDOWLEAVE:
                g.mouse_on = False

        g.update(dt)
        draw(screen, g)
        pygame.display.flip()
        frames += 1
        if smoke and frames >= 90:
            running = False
    pygame.quit()

# ==================== 自检 ====================
def selftest():
    if os.environ.get('SDL_VIDEODRIVER') != 'dummy':
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
    pygame.init()
    pygame.display.set_mode((640, 480))   # 动画加载（convert/smoothscale）需要显示 Surface
    g = Game()

    # 1. 直线寻路 + 移动到达
    u = g._add_unit('soldier', 100, 100)
    g.order_move([u], 300, 100)
    assert u.path is not None, '直线寻路失败'
    for _ in range(600):
        g.update(0.1)
    assert math.hypot(u.x - 300, u.y - 100) < 30, '单位未到达目标'

    # 2. 绕障：建筑挡路
    g2 = Game()
    g2.units[:] = []                                  # 清空随机初始单位，保证路径干净
    g2.buildings.append(Building('barracks', 300, 100))
    g2.rebuild_blocked()
    u2 = g2._add_unit('soldier', 100, 100)
    g2.order_move([u2], 500, 100)
    assert u2.path is not None, '绕障寻路失败'
    for _ in range(3000):
        g2.update(0.1)
    assert math.hypot(u2.x - 500, u2.y - 100) < 50, '绕障后未到达目标'

    # 3. 放置合法性
    g.units[:] = []                                   # 清空随机初始单位，避免挡住放置位
    assert g.place_valid('barracks', 900, 1300), '空地应可放置'
    g3 = Game()
    g3.buildings.append(Building('depot', 300, 300))
    g3.rebuild_blocked()
    assert not g3.place_valid('depot', 300, 300), '重叠应不可放置'
    assert g3.place_valid('turret', 300, 460), '相邻空地应可放置'

    # 4. 建造流程：放置 → 施工 → 完成
    g.units[:] = []                                  # 清空随机初始单位，保证空地
    eng = g._add_unit('engineer', 200, 700)
    g.selection = {eng.id}
    g.start_place('turret')
    assert g.place_mode == 'turret', '进入放置模式失败'
    g.try_place(500, 700)
    assert g.constructions, '工地未创建'
    for _ in range(500):
        g.update(0.1)
    assert any(b.type == 'turret' for b in g.buildings), '建筑未建成'
    assert eng.state == 'idle', '工兵应恢复空闲'

    # 5. 单位软碰撞
    a = g._add_unit('soldier', 100, 100)
    b = g._add_unit('soldier', 102, 100)
    for _ in range(30):
        g.update(0.1)
    assert math.hypot(a.x - b.x, a.y - b.y) >= 16, '软碰撞未推开'

    # 6. 双击全选画面内同类
    g4 = Game()
    g4.units[:] = []
    s1 = g4._add_unit('soldier', 300, 300)
    s2 = g4._add_unit('soldier', 340, 340)
    g4._add_unit('engineer', 320, 320)
    g4.camera = [200, 200]
    g4.view = [800, 600]
    g4.select_same_type_in_view(s1)
    assert s1.id in g4.selection and s2.id in g4.selection, '同类未被全选'
    assert len(g4.selection) == 2, '选中范围应为 2 个同类单位'

    # 7. 移动命令打断施工
    eng2 = g._add_unit('engineer', 200, 100)
    g.selection = {eng2.id}
    g.start_place('barracks')
    g.try_place(400, 100)
    assert eng2.state == 'building', '工兵应进入施工状态'
    g.order_move([eng2], 200, 200)
    assert eng2.state == 'idle', '移动命令应打断施工'

    # 8. 多单位挤一堆：5 个步兵同时移动到一个点，应分散到达且互不重叠
    g5 = Game()
    g5.units[:] = []
    squad = [g5._add_unit('soldier', 100, 100 + i * 8) for i in range(5)]
    g5.order_move(squad, 1000, 500)
    for _ in range(300):
        g5.update(0.1)
    for su in squad:
        assert math.hypot(su.x - 1000, su.y - 500) < 150, '单位未到达目标区域'
    for i in range(len(squad)):
        for j in range(i + 1, len(squad)):
            d = math.hypot(squad[i].x - squad[j].x, squad[i].y - squad[j].y)
            assert d >= 16, '多单位仍重叠 (d=%.1f)' % d

    # 9. 缩放与坐标换算
    g6 = Game()
    g6.camera = [500, 400]
    g6.view = [1280, 720]
    g6.set_zoom(1.5)
    wx, wy = g6.screen_to_world(0, 0)
    assert abs(wx - g6.camera[0]) < 0.01 and abs(wy - g6.camera[1]) < 0.01, 'screen_to_world 错误'
    wx2, wy2 = g6.screen_to_world(1280, 720)
    assert abs(wx2 - (g6.camera[0] + 1280 * 1.5)) < 0.01, 'zoom 换算错误'
    assert 0.5 <= g6.zoom <= 2.0, 'zoom 越界'

    # 10. 小地图映射
    mm = g6.mm_rect()
    wx0, wy0 = g6.minimap_to_world(mm[0], mm[1])
    wx1, wy1 = g6.minimap_to_world(mm[0] + mm[2], mm[1] + mm[3])
    assert wx0 < 100 and wy0 < 100, '小地图左上映射错误'
    assert wx1 > MAP_W - 100 and wy1 > MAP_H - 100, '小地图右下映射错误'

    # 11. 相向而行：应平滑错开通过，不重叠、不绕圈
    g8 = Game()
    g8.units[:] = []
    a = g8._add_unit('soldier', 200, 300)
    b = g8._add_unit('soldier', 600, 306)
    g8.order_move([a], 600, 300)
    g8.order_move([b], 200, 306)
    min_d = 9999.0
    a_total = 0.0
    a_prev = (a.x, a.y)
    for _ in range(600):
        g8.update(0.1)
        d = math.hypot(a.x - b.x, a.y - b.y)
        min_d = min(min_d, d)
        a_total += math.hypot(a.x - a_prev[0], a.y - a_prev[1])
        a_prev = (a.x, a.y)
    assert math.hypot(a.x - 600, a.y - 300) < 40, '相向移动 A 未到达'
    assert math.hypot(b.x - 200, b.y - 306) < 40, '相向移动 B 未到达'
    assert min_d >= 12, '相向单位发生重叠（min_d=%.1f）' % min_d
    assert a_total < 1200, 'A 绕圈抖动（路程 %.0f / 直线 400）' % a_total

    # 12. 大量单位穿过狭窄峡谷：全部到达、互不重叠、路程正常（不绕圈）
    g9 = Game()
    g9.units[:] = []
    squad = []
    for i in range(15):
        squad.append(g9._add_unit('soldier', 700 + (i % 3) * 24, 500 + (i // 3) * 24))
    for i in range(5):
        squad.append(g9._add_unit('tank', 700 + (i % 2) * 34, 760 + (i // 2) * 40))
    goal = (2000, 1045)                          # 峡谷（缺口约 150px）另一侧
    g9.order_move(squad, goal[0], goal[1])
    assert all(u.path is not None for u in squad), '峡谷寻路失败（路径不存在）'
    total = 0.0
    prev = [(u.x, u.y) for u in squad]
    for _ in range(1500):
        g9.update(0.1)
        for i, u in enumerate(squad):
            total += math.hypot(u.x - prev[i][0], u.y - prev[i][1])
            prev[i] = (u.x, u.y)
    for u in squad:
        assert math.hypot(u.x - goal[0], u.y - goal[1]) < 200, '%s 未穿过峡谷' % u.name
    for i in range(len(squad)):
        for j in range(i + 1, len(squad)):
            d = math.hypot(squad[i].x - squad[j].x, squad[i].y - squad[j].y)
            assert d >= 12, '峡谷中单位重叠'
    straight = math.hypot(goal[0] - 700, goal[1] - 500)
    assert total < len(squad) * straight * 2.6, '峡谷移动路程异常（可能绕圈）'

    # 13. 滚轮缩放：鼠标锚点下的世界坐标保持不动，且 clamp 生效
    g10 = Game()
    g10.camera = [500, 400]
    g10.view = [1280, 720]
    g10.zoom = 1.0
    wx0, wy0 = g10.screen_to_world(640, 360)
    g10.zoom_at(640, 360, 1.3)
    wx1, wy1 = g10.screen_to_world(640, 360)
    assert abs(wx1 - wx0) < 0.01 and abs(wy1 - wy0) < 0.01, '滚轮缩放锚点漂移'
    assert abs(g10.zoom - 1.3) < 0.0001, '滚轮缩放系数错误'
    g10.zoom_at(640, 360, 0.001)
    assert abs(g10.zoom - ZOOM_MIN) < 0.0001, '缩小越界未限制'
    g10.zoom_at(640, 360, 999)
    assert abs(g10.zoom - ZOOM_MAX) < 0.0001, '放大越界未限制'

    # 14. 兵营生产步兵：入队 → 计时完成 → 兵营旁生成新单位（含排队叠加）
    g11 = Game()
    g11.units[:] = []
    b = Building('barracks', 1000, 1000)
    g11.buildings.append(b)
    g11.rebuild_blocked()
    before = len(g11.units)
    g11.sel_building = b
    g11.start_train()
    assert len(b.train_queue) == 1 and b.train_progress == 0.0, '生产入队失败'
    frames1 = int(TRAIN_TIME / 0.1) + 2
    gy = int((b.y + b.h / 2) / GRID) + 1
    door_y = gy * GRID + GRID / 2
    nu = None
    seen = False
    for _ in range(frames1 + 30):                # 训练 + 自动出门移动
        g11.update(0.1)
        if not seen and len(g11.units) == before + 1:
            seen = True
            nu = g11.units[-1]
            assert nu.type == 'soldier' and nu.team == 'player', '生产兵种错误'
            # 生成瞬间：在内部产生位置且不可见
            assert nu.hidden, '新兵应在内部产生位置且不可见'
            assert nu.x == b.x and nu.y < b.y + b.h / 2, '新兵未在内部产生位置'
    assert seen, '未生成新步兵'
    assert not b.train_queue and b.train_progress == 0.0, '首个步兵未按时完成'
    assert not nu.hidden, '新兵未走出兵营（隐藏未解除）'
    assert abs(nu.x - b.x) < 40 and abs(nu.y - door_y) < 40, '新兵未到达门口'
    # 排队叠加：连续点两次 → 两个步兵依次完成
    g11.start_train()
    g11.start_train()
    assert len(b.train_queue) == 2, '生产队列叠加失败'
    for _ in range(frames1 * 2 + 2):
        g11.update(0.1)
    assert not b.train_queue, '队列未全部完成'
    assert len(g11.units) == before + 3, '队列完成数量错误'

    print('SELFTEST PASS')
    return 0


# ==================== 入口 ====================
if __name__ == '__main__':
    if '--selftest' in sys.argv:
        try:
            sys.exit(selftest())
        except AssertionError as e:
            print('SELFTEST FAIL:', e)
            sys.exit(1)
    elif '--smoke' in sys.argv:
        main(smoke=True)
    else:
        main()

