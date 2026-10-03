import io
P = 'game.py'
s = io.open(P, encoding='utf-8').read()

# 阵营直接用种族名
old = """# 四阵营
TEAMS = [
    {'id': 'red',    'name': '红方', 'color': (208, 80, 74),  'race': 'orc'},
    {'id': 'blue',   'name': '蓝方', 'color': (61, 125, 216), 'race': 'human'},
    {'id': 'green',  'name': '绿方', 'color': (67, 160, 71),  'race': 'dwarf'},
    {'id': 'yellow', 'name': '黄方', 'color': (224, 169, 60), 'race': 'elf'},
]
TEAM_COLOR = {t['id']: t['color'] for t in TEAMS}
TEAM_RACE = {t['id']: t['race'] for t in TEAMS}"""
new = """# 四阵营 = 四族
TEAMS = [
    {'id': 'human', 'name': '人类', 'color': (61, 125, 216)},
    {'id': 'orc',   'name': '兽人', 'color': (208, 80, 74)},
    {'id': 'dwarf', 'name': '矮人', 'color': (67, 160, 71)},
    {'id': 'elf',   'name': '精灵', 'color': (224, 169, 60)},
]
TEAM_COLOR = {t['id']: t['color'] for t in TEAMS}
TEAM_RACE = {t['id']: t['id'] for t in TEAMS}  # 阵营id=种族id"""
assert old in s
s = s.replace(old, new, 1)

# 默认玩家阵营改 human
s = s.replace("self.player_team = 'blue'", "self.player_team = 'human'")

# 初始布局：四族各在一角
old2 = """        self.player_team = 'human'  # 默认蓝方，可在设置切换
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
new2 = """        self.player_team = 'human'  # 默认人类，可在设置切换
        # 四族各在一个角落：人类(左下)、兽人(右下)、矮人(左上)、精灵(右上)
        br_human = Building('barracks', 500, 2100); br_human.team = 'human'
        br_orc = Building('barracks', 3100, 2100); br_orc.team = 'orc'
        br_dwarf = Building('barracks', 500, 300); br_dwarf.team = 'dwarf'
        br_elf = Building('barracks', 3100, 300); br_elf.team = 'elf'
        self.buildings.extend([br_human, br_orc, br_dwarf, br_elf])
        # 各族初始步兵
        self._spawn_team('infantry', 12, 'human', 300, 1900, 900, 2400)
        self._spawn_team('infantry', 8, 'orc', 2700, 1900, 3300, 2400)
        self._spawn_team('infantry', 8, 'dwarf', 300, 100, 900, 600)
        self._spawn_team('infantry', 8, 'elf', 2700, 100, 3300, 600)"""
assert old2 in s
s = s.replace(old2, new2, 1)

# UNIT_DEF 默认 team 改 human
s = s.replace("'team': 'blue'", "'team': 'human'")

# selftest 断言改 human
s = s.replace("nu.team == 'blue'", "nu.team == 'human'")

io.open(P, 'w', encoding='utf-8').write(s)
print("OK")
