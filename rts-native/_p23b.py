import io
P = 'game.py'
s = io.open(P, encoding='utf-8').read()

# 批量替换旧类型名
s = s.replace("'soldier'", "'infantry'")
s = s.replace("'esoldier'", "'infantry'")
s = s.replace("('soldier', 'esoldier')", "'infantry'")
s = s.replace("('soldier','esoldier')", "'infantry'")
# 玩家兵营生产按钮
s = s.replace("b.train_queue.append('soldier')", "b.train_queue.append('infantry')")
# selftest 断言
s = s.replace("nu.type == 'soldier' and nu.team == 'player'", "nu.type == 'infantry' and nu.team == 'blue'")
# 战斗匹配
s = s.replace("u.type not in 'infantry' or u.battle", "u.type != 'infantry' or u.battle")
s = s.replace("u.type not in 'infantry' or u.battle == b.id", "u.type != 'infantry' or u.battle == b.id")
# 渲染
s = s.replace("u.type in 'infantry'", "u.type == 'infantry'")
# UI按钮
s = s.replace("u.type == 'soldier'", "u.type == 'infantry'")

io.open(P, 'w', encoding='utf-8').write(s)
print("OK")
