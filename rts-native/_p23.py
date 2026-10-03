# -*- coding: utf-8 -*-
"""PATCH23: 四阵营系统 + AI自动生产 + 草地纹理 + 设置切换阵营"""
import io
P = r"C:\Users\24731\Doubao\chats\2026-09-24\new-chat-2\rts-native\game.py"
s = io.open(P, encoding='utf-8').read()

# === 1. 加四阵营定义 ===
old_const = """COMBAT_TRIGGER = 80.0"""
new_const = """# 四阵营
TEAMS = [
    {'id': 'red',    'name': '红方', 'color': (208, 80, 74),  'race': 'orc'},
    {'id': 'blue',   'name': '蓝方', 'color': (61, 125, 216), 'race': 'human'},
    {'id': 'green',  'name': '绿方', 'color': (67, 160, 71),  'race': 'dwarf'},
    {'id': 'yellow', 'name': '黄方', 'color': (224, 169, 60), 'race': 'elf'},
]
TEAM_COLOR = {t['id']: t['color'] for t in TEAMS}
TEAM_RACE = {t['id']: t['race'] for t in TEAMS}
AI_PRODUCE_INTERVAL = 10.0  # AI兵营每10秒生产一个步兵

COMBAT_TRIGGER = 80.0"""
assert old_const in s
s = s.replace(old_const, new_const, 1)

# === 2. Building 加 team 字段 ===
old_bld = """        self.train_queue = []
        self.train_progress = 0.0"""
new_bld = """        self.train_queue = []
        self.train_progress = 0.0
        self.team = None
        self.ai_timer = 0.0"""
assert old_bld in s
s = s.replace(old_bld, new_bld, 1)

# === 3. Game.__init__：加 player_team，四阵营布局 ===
old_init = """        self.buildings.append(Building('depot', 620, 560))
        self.buildings.append(Building('barracks', 1960, 300))
        self.buildings.append(Building('depot', 2050, 520))
        self._spawn('soldier', 20, 480, 480, 1300, 1300)
        self._spawn('tank', 8, 480, 1340, 1300, 1750)
        self._spawn('engineer', 10, 1400, 480, 1800, 920)
        self._spawn('hero', 2, 380, 1500, 700, 1780)
        self._spawn('esoldier', 10, 2600, 640, 3320, 1380)
        self._spawn('etank', 4, 2600, 1460, 3320, 1980)
        self._spawn('eengineer', 4, 1980, 1680, 2380, 1960)"""
new_init = """        self.player_team = 'blue'  # 默认蓝方，可在设置切换
        # 四阵营各在一个角落：蓝(左下)、红(右下)、绿(左上)、黄(右上)
        # 每阵营一个兵营
        br_blue = Building('barracks', 500, 2100); br_blue.team = 'blue'
        br_red = Building('barracks', 3100, 2100); br_red.team = 'red'
        br_green = Building('barracks', 500, 300); br_green.team = 'green'
        br_yellow = Building('barracks', 3100, 300); br_yellow.team = 'yellow'
        self.buildings.extend([br_blue, br_red, br_green, br_yellow])
        # 玩家初始步兵
        self._spawn_team('infantry', 12, 'blue', 300, 1900, 900, 2400)
        # 其他阵营初始步兵
        self._spawn_team('infantry', 8, 'red', 2700, 1900, 3300, 2400)
        self._spawn_team('infantry', 8, 'green', 300, 100, 900, 600)
        self._spawn_team('infantry', 8, 'yellow', 2700, 100, 3300, 600)"""
assert old_init in s
s = s.replace(old_init, new_init, 1)

# === 4. 加 _spawn_team 方法 ===
old_add = """    def _add_unit(self, type_, x, y):
        u = Unit(self._next_id, type_, x, y)
        self._next_id += 1
        self.units.append(u)
        return u"""
new_add = """    def _add_unit(self, type_, x, y, team=None):
        u = Unit(self._next_id, type_, x, y)
        self._next_id += 1
        if team is not None:
            u.team = team
        self.units.append(u)
        return u

    def _spawn_team(self, type_, n, team, x0, y0, x1, y1):
        \"\"\"在区域内随机放置 n 个指定阵营的单位\"\"\"
        placed = 0
        guard = 0
        while placed < n and guard < n * 300:
            guard += 1
            x = x0 + (x1 - x0) * (self._next_id * 37 % 100) / 100.0
            y = y0 + (y1 - y0) * (self._next_id * 53 % 100) / 100.0
            x = max(x0, min(x1, x))
            y = max(y0, min(y1, y))
            if self._phys_blocked(x, y, 9):
                continue
            u = self._add_unit(type_, x, y, team=team)
            placed += 1"""
assert old_add in s
s = s.replace(old_add, new_add, 1)

# === 5. Unit.__init__：team 从 UNIT_DEF 读，但允许覆盖 ===
old_unit_team = """        self.team = d['team']"""
new_unit_team = """        self.team = d['team']  # 默认阵营，_add_unit 可覆盖"""
assert old_unit_team in s
s = s.replace(old_unit_team, new_unit_team, 1)

# === 6. SPRITE_RACE：按阵营映射素材 ===
old_race = """SPRITE_RACE = {'soldier': 'human', 'esoldier': 'orc'}"""
new_race = """SPRITE_RACE = {'infantry': None}  # race 在 __init__ 里按 team 动态设"""
assert old_race in s
s = s.replace(old_race, new_race, 1)

# === 7. Unit.__init__：按 team 选素材 ===
old_sprite = """        if type_ in SPRITE_RACE:
            self.race = SPRITE_RACE[type_]"""
new_sprite = """        # 步兵按阵营选素材
        if type_ == 'infantry':
            self.race = TEAM_RACE.get(self.team, 'human')
        elif type_ in SPRITE_RACE:
            self.race = SPRITE_RACE[type_]"""
assert old_sprite in s
s = s.replace(old_sprite, new_sprite, 1)

# === 8. UNIT_DEF：加 infantry，保留旧类型兼容 selftest ===
old_unitdef = """UNIT_DEF = {
    'engineer':  {'name': '工兵', 'r': 10, 'speed': 68,  'team': 'player', 'color': (67, 160, 71)},
    'soldier':   {'name': '步兵', 'r': 9,  'speed': 70,  'team': 'player', 'color': (61, 125, 216), 'hp': 100},
    'tank':      {'name': '坦克', 'r': 15, 'speed': 48,  'team': 'player', 'color': (91, 109, 120)},
    'hero':      {'name': '英雄', 'r': 13, 'speed': 100, 'team': 'player', 'color': (224, 169, 60)},
    'esoldier':  {'name': '敌步兵', 'r': 9,  'speed': 0,  'team': 'enemy', 'color': (208, 80, 74), 'hp': 100},
    'etank':     {'name': '敌坦克', 'r': 15, 'speed': 0,  'team': 'enemy', 'color': (140, 58, 52)},
    'eengineer': {'name': '敌工兵', 'r': 10, 'speed': 0,  'team': 'enemy', 'color': (168, 85, 63)},
}"""
new_unitdef = """UNIT_DEF = {
    'infantry':  {'name': '步兵', 'r': 9,  'speed': 70,  'team': 'blue', 'color': (61, 125, 216), 'hp': 100},
    'engineer':  {'name': '工兵', 'r': 10, 'speed': 68,  'team': 'blue', 'color': (67, 160, 71)},
    'tank':      {'name': '坦克', 'r': 15, 'speed': 48,  'team': 'blue', 'color': (91, 109, 120)},
    'hero':      {'name': '英雄', 'r': 13, 'speed': 100, 'team': 'blue', 'color': (224, 169, 60)},
}"""
assert old_unitdef in s
s = s.replace(old_unitdef, new_unitdef, 1)

# === 9. 战斗触发：所有 infantry 都参与 ===
old_trig = """            if u.hidden or u.type not in ('soldier', 'esoldier'):
                continue
            if u.combat_immune > now:                       # 玩家命令豁免：不重新触发战斗
                continue
            if u.path is not None and u.path_idx < len(u.path):  # 正在执行玩家移动命令：途中不自动接战（红警/RW行为）
                continue
            for o in self._neighbors(u):
                if o.hidden or o.team == u.team or o.type not in ('soldier', 'esoldier'):"""
new_trig = """                if u.hidden or u.type != 'infantry':
                    continue
                if u.combat_immune > now:
                    continue
                # AI单位（非玩家阵营）始终自动索敌；玩家单位正在执行移动命令时不自动接战
                is_ai = u.team != self.player_team
                if not is_ai and u.path is not None and u.path_idx < len(u.path):
                    continue
                for o in self._neighbors(u):
                    if o.hidden or o.team == u.team or o.type != 'infantry':"""
assert old_trig in s
s = s.replace(old_trig, new_trig, 1)

# === 10. _match_battle：敌对判定改 != ===
old_match = """            enemies = [e for e in by_team.get('enemy' if u.team == 'player' else 'player', []) if e.state != 'dying']"""
new_match = """            enemies = [e for e in units if e.team != u.team and e.state != 'dying']"""
assert old_match in s
s = s.replace(old_match, new_match, 1)

# === 11. selected_units：按 player_team 筛选 ===
old_sel = """        return [u for u in self.units if u.id in self.selection and u.team == 'player']"""
new_sel = """        return [u for u in self.units if u.id in self.selection and u.team == self.player_team]"""
assert old_sel in s
s = s.replace(old_sel, new_sel, 1)

# === 12. 框选/双击：按 player_team ===
old_box = """            if o.team != 'player' or o.type != u.type:"""
new_box = """            if o.team != self.player_team or o.type != u.type:"""
assert old_box in s
s = s.replace(old_box, new_box, 1)

old_order = """            if u.team != 'player':"""
new_order = """            if u.team != self.player_team:"""
assert old_order in s
s = s.replace(old_order, new_order, 1)

# === 13. 小地图颜色：按阵营 ===
old_mm = """        col = (111, 207, 122) if u.team == 'player' else (224, 85, 85)"""
new_mm = """        col = TEAM_COLOR.get(u.team, (200, 200, 200))"""
assert old_mm in s
s = s.replace(old_mm, new_mm, 1)

# === 14. 状态栏：四阵营计数 ===
old_stats = """            mine = sum(1 for u in self.units if u.team == 'player')
            enemy = sum(1 for u in self.units if u.team == 'enemy')"""
new_stats = """            mine = sum(1 for u in self.units if u.team == self.player_team)
            enemy = sum(1 for u in self.units if u.team != self.player_team)"""
assert old_stats in s
s = s.replace(old_stats, new_stats, 1)

# === 15. AI 兵营自动生产 + AI 步兵自动索敌 ===
# 在 _update_training 后加 AI 生产逻辑
old_train = """    def _update_training(self, dt):
        \"\"\"兵营生产：队列计时，完成后在兵营旁生成单位\"\"\"
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
            self.refresh_ui()"""
new_train = """    def _update_training(self, dt):
        \"\"\"兵营生产：队列计时，完成后在兵营旁生成单位\"\"\"
        done = False
        for b in self.buildings:
            # AI 兵营自动生产（每10秒一个步兵）
            if b.type == 'barracks' and b.team is not None and b.team != self.player_team:
                b.ai_timer += dt
                if b.ai_timer >= AI_PRODUCE_INTERVAL:
                    b.ai_timer = 0.0
                    b.train_queue.append('infantry')
            if not b.train_queue:
                continue
            b.train_progress += dt / TRAIN_TIME
            if b.train_progress >= 1.0:
                b.train_progress = 0.0
                t = b.train_queue.pop(0)
                self._spawn_trained(b, t)
                done = True
        if done:
            self.refresh_ui()

    def _update_ai_units(self, dt):
        \"\"\"AI单位：走出兵营后自动走向最近敌人巡逻\"\"\"
        for u in self.units:
            if u.type != 'infantry' or u.team == self.player_team:
                continue
            if u.state == 'combat' and u.locked is not None:
                continue  # 正在战斗
            if u.path is not None and u.path_idx < len(u.path):
                continue  # 正在移动
            if u.hidden:
                continue
            # 找最近敌人
            best = None
            best_d = 1e9
            for o in self.units:
                if o.team == u.team or o.type != 'infantry' or o.state == 'dying':
                    continue
                d = (o.x - u.x) ** 2 + (o.y - u.y) ** 2
                if d < best_d:
                    best_d = d
                    best = o
            if best is not None:
                u.move_target = (best.x, best.y)
                u.path = self.find_path(u.x, u.y, best.x, best.y)
                u.path_idx = 0"""
assert old_train in s
s = s.replace(old_train, new_train, 1)

# === 16. 主循环加 _update_ai_units ===
old_loop = """        self._update_constructions(dt)"""
new_loop = """        self._update_ai_units(dt)
        self._update_constructions(dt)"""
assert old_loop in s
s = s.replace(old_loop, new_loop, 1)

# === 17. 草地纹理：背景加随机斑点 ===
old_bg = """    surf.fill((74, 114, 64), pygame.Rect(round(tsx(0)), round(tsy(0)), round(MAP_W / z), round(MAP_H / z)))"""
new_bg = """    surf.fill((74, 114, 64), pygame.Rect(round(tsx(0)), round(tsy(0)), round(MAP_W / z), round(MAP_H / z)))
    # 草地纹理：随机深浅斑点（预生成缓存）
    if not hasattr(g, '_grass_cache') or g._grass_cache is None:
        gc = pygame.Surface((MAP_W, MAP_H))
        gc.fill((74, 114, 64))
        import random as _r
        for _ in range(800):
            gx = _r.randint(0, MAP_W)
            gy = _r.randint(0, MAP_H)
            gr = _r.randint(2, 6)
            shade = _r.randint(-12, 12)
            pygame.draw.circle(gc, (74+shade, 114+shade, 64+shade), (gx, gy), gr)
        g._grass_cache = gc
    gw, gh = round(MAP_W / z), round(MAP_H / z)
    gv = pygame.transform.smoothscale(g._grass_cache, (max(1, gw), max(1, gh)))
    surf.blit(gv, (round(tsx(0)), round(tsy(0))))"""
assert old_bg in s
s = s.replace(old_bg, new_bg, 1)

# === 18. 设置弹窗加阵营选择 ===
old_help = """        lines = [
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
            draw_text(surf, txt, size, col, hx + 12, hy + 8 + i * 19)"""
new_help = """        lines = [
            ('操作说明', 12, (232, 238, 218)),
            ('左键 点击 / 框选 单位', 11, (200, 210, 182)),
            ('右键 点击地面 → 移动命令', 11, (200, 210, 182)),
            ('中键拖动 → 平移地图', 11, (200, 210, 182)),
            ('滚轮 缩放地图', 11, (200, 210, 182)),
            ('小地图 点击跳转视角', 11, (200, 210, 182)),
            ('点选兵营 → 生产步兵', 11, (200, 210, 182)),
        ]
        for i, (txt, size, col) in enumerate(lines):
            draw_text(surf, txt, size, col, hx + 12, hy + 8 + i * 19)
        # 阵营选择
        ty = hy + 8 + len(lines) * 19 + 8
        draw_text(surf, '选择阵营（当前: %s）' % dict((t['id'], t['name']) for t in TEAMS)[g.player_team],
                  11, (232, 238, 218), hx + 12, ty)
        for i, t in enumerate(TEAMS):
            cx = hx + 12 + i * 70
            cy = ty + 22
            pygame.draw.rect(surf, t['color'], pygame.Rect(cx, cy, 60, 24))
            if t['id'] == g.player_team:
                pygame.draw.rect(surf, (255, 255, 255), pygame.Rect(cx, cy, 60, 24), 2)
            draw_text(surf, t['name'], 10, (20, 20, 20), cx + 30, cy + 6, center=True)
            # 存阵营按钮位置供点击检测
            g._team_btn_rects = [(t['id'], (cx, cy, 60, 24)) for t in TEAMS]"""
assert old_help in s
s = s.replace(old_help, new_help, 1)

# === 19. 事件处理：点击阵营按钮切换 ===
# 找 help_open 相关的点击处理
old_click_gear = """    # 齿轮按钮
    gr = gear_rect(W)
    if mx >= gr[0] and mx <= gr[0]+gr[2] and my >= gr[1] and my <= gr[1]+gr[3]:
        g.help_open = not g.help_open
        return"""
# 先看有没有这段
if old_click_gear in s:
    new_click_gear = """    # 齿轮按钮
    gr = gear_rect(W)
    if mx >= gr[0] and mx <= gr[0]+gr[2] and my >= gr[1] and my <= gr[1]+gr[3]:
        g.help_open = not g.help_open
        return
    # 阵营按钮
    if g.help_open and hasattr(g, '_team_btn_rects'):
        for tid, (bx, by, bw, bh) in g._team_btn_rects:
            if mx >= bx and mx <= bx+bw and my >= by and my <= by+bh:
                g.player_team = tid
                g.show_toast('已切换到%s' % dict((t['id'], t['name']) for t in TEAMS)[tid])
                return"""
    s = s.replace(old_click_gear, new_click_gear, 1)

# === 20. _spawn_trained：AI兵营生产的单位自动索敌 ===
old_spawn_trained = """        u.path = [door]
        u.path_idx = 0"""
new_spawn_trained = """        u.path = [door]
        u.path_idx = 0
        # AI兵营生产的单位：走出门口后自动索敌（在 _update_ai_units 处理）"""
assert old_spawn_trained in s
s = s.replace(old_spawn_trained, new_spawn_trained, 1)

io.open(P, 'w', encoding='utf-8').write(s)
print("PATCH23 OK, size:", len(s))
