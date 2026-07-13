"""
测试数据生成脚本
运行方式：cd agent-service && python generate_test_data.py
"""
import random
import pymysql
from datetime import datetime, timedelta
from config import settings

# 连接数据库（用同步连接，简单直接）
conn = pymysql.connect(
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    database=settings.DB_NAME,
    charset="utf8mb4",
    autocommit=False,
)
cursor = conn.cursor()

# ============================================================
# 1. 员工表（新增5个员工，密码都是 123456 的 MD5）
# ============================================================
print("插入员工数据...")
employees = [
    ("张三", "zhangsan", "13900001111", "1", "110101199503152018"),
    ("李四", "lisi", "13900002222", "1", "110101199208221034"),
    ("王五", "wangwu", "13900003333", "0", "110101198811053021"),
    ("赵六", "zhaoliu", "13900004444", "1", "110101199706184056"),
    ("孙七", "sunqi", "13900005555", "1", "110101200001095072"),
]
for e in employees:
    cursor.execute(
        "INSERT INTO employee (name, username, password, phone, sex, id_number, status, create_time, update_time, create_user, update_user) "
        "VALUES (%s, %s, 'e10adc3949ba59abbe56e057f20f883e', %s, %s, %s, 1, %s, %s, 1, 1)",
        (e[0], e[1], e[2], e[3], e[4],
         datetime(2024, random.randint(1, 6), random.randint(1, 28)),
         datetime(2024, random.randint(1, 6), random.randint(1, 28)))
    )
print(f"  新增 {len(employees)} 个员工")

# ============================================================
# 2. 用户表（50个微信用户，注册时间分布在2024-2026）
# ============================================================
print("插入用户数据...")
first_names = ["张", "李", "王", "赵", "刘", "陈", "杨", "黄", "周", "吴",
               "徐", "孙", "马", "朱", "胡", "郭", "林", "何", "高", "罗"]
last_names_m = ["伟", "强", "磊", "军", "勇", "明", "辉", "鹏", "飞", "涛"]
last_names_f = ["芳", "娜", "敏", "静", "丽", "婷", "雪", "慧", "萍", "燕"]

user_ids = []
for i in range(50):
    sex = random.choice(["1", "0"])  # 1=男, 0=女
    name = random.choice(first_names) + random.choice(last_names_m if sex == "1" else last_names_f)
    phone = f"138{random.randint(10000000, 99999999)}"
    # 注册时间：2024年1月 ~ 2026年7月，越往后新用户越少
    if i < 20:
        reg_date = datetime(2024, random.randint(1, 12), random.randint(1, 28), random.randint(8, 22), random.randint(0, 59))
    elif i < 38:
        reg_date = datetime(2025, random.randint(1, 12), random.randint(1, 28), random.randint(8, 22), random.randint(0, 59))
    else:
        reg_date = datetime(2026, random.randint(1, 6), random.randint(1, 28), random.randint(8, 22), random.randint(0, 59))

    cursor.execute(
        "INSERT INTO user (openid, name, phone, sex, avatar, create_time) VALUES (%s, %s, %s, %s, %s, %s)",
        (f"ox{i:04d}{random.randint(10000, 99999)}", name, phone, sex,
         f"https://cube.elemecdn.com/{random.randint(0,9)}/{random.randint(0,9)}/{random.randint(0,9)}/avatar{i}.jpg",
         reg_date)
    )
    user_ids.append(cursor.lastrowid)
print(f"  新增 {len(user_ids)} 个用户")

# ============================================================
# 3. 地址簿（每个用户1-2个地址）
# ============================================================
print("插入地址簿数据...")
streets = ["中关村大街", "望京西路", "朝阳北路", "建国路", "三里屯路",
           "学院路", "西直门外大街", "安定门外大街", "广渠路", "东四环中路"]
districts = [("110101", "东城区"), ("110105", "朝阳区"), ("110108", "海淀区"),
             ("110106", "丰台区"), ("110102", "西城区")]
address_ids = []
for uid in user_ids:
    num_addresses = random.choices([1, 2], weights=[40, 60])[0]
    for j in range(num_addresses):
        d = random.choice(districts)
        cursor.execute(
            "INSERT INTO address_book (user_id, consignee, sex, phone, province_code, province_name, "
            "city_code, city_name, district_code, district_name, detail, label, is_default) "
            "VALUES (%s, %s, %s, %s, '110000', '北京市', '110100', '北京市', %s, %s, %s, %s, %s)",
            (uid,
             f"收货人{uid}",
             random.choice(["1", "0"]),
             f"138{random.randint(10000000, 99999999)}",
             d[0], d[1],
             f"{random.choice(streets)}{random.randint(1, 200)}号{random.randint(1, 30)}层",
             random.choice(["家", "公司", "学校", ""]),
             1 if j == 0 else 0)
        )
        address_ids.append(cursor.lastrowid)
print(f"  新增 {len(address_ids)} 个地址")

# ============================================================
# 4. 套餐表 + 套餐菜品关系
# ============================================================
print("插入套餐数据...")
setmeals = [
    ("单人烤鱼套餐", 13, 128.00, "草鱼2斤+米饭+王老吉"),
    ("双人牛蛙套餐", 13, 238.00, "金汤酸菜牛蛙+蒜蓉娃娃菜+米饭x2+北冰洋x2"),
    ("商务四人套餐", 15, 388.00, "清蒸鲈鱼+梅菜扣肉+清炒西兰花+鸡蛋汤x4+米饭x4"),
    ("超值单人餐", 13, 48.00, "蜀味水煮草鱼+米饭+鸡蛋汤"),
    ("家庭聚餐套餐", 15, 328.00, "剁椒鱼头+东坡肘子+清炒小油菜+平菇豆腐汤+米饭x3"),
    ("轻食双人餐", 13, 98.00, "蒜蓉娃娃菜+炝炒圆白菜+米饭x2+王老吉x2"),
]
setmeal_ids = []
for s in setmeals:
    cursor.execute(
        "INSERT INTO setmeal (category_id, name, price, status, description, image, create_time, update_time, create_user, update_user) "
        "VALUES (%s, %s, %s, 1, %s, 'https://sky-itcast.oss-cn-beijing.aliyuncs.com/setmeal.png', %s, %s, 1, 1)",
        (s[1], s[0], s[2], s[3],
         datetime(2024, random.randint(1, 6), 1),
         datetime(2024, random.randint(1, 6), 1))
    )
    setmeal_ids.append(cursor.lastrowid)

# 套餐菜品关系
setmeal_dishes_map = {
    0: [(65, "草鱼2斤", 68.00, 1), (49, "米饭", 2.00, 1), (46, "王老吉", 6.00, 1)],
    1: [(62, "金汤酸菜牛蛙", 88.00, 1), (55, "蒜蓉娃娃菜", 18.00, 1), (49, "米饭", 2.00, 2), (47, "北冰洋", 4.00, 2)],
    2: [(58, "清蒸鲈鱼", 98.00, 1), (60, "梅菜扣肉", 58.00, 1), (56, "清炒西兰花", 18.00, 1), (68, "鸡蛋汤", 4.00, 4), (49, "米饭", 2.00, 4)],
    3: [(53, "蜀味水煮草鱼", 38.00, 1), (49, "米饭", 2.00, 1), (68, "鸡蛋汤", 4.00, 1)],
    4: [(61, "剁椒鱼头", 66.00, 1), (59, "东坡肘子", 138.00, 1), (54, "清炒小油菜", 18.00, 1), (69, "平菇豆腐汤", 6.00, 1), (49, "米饭", 2.00, 3)],
    5: [(55, "蒜蓉娃娃菜", 18.00, 1), (57, "炝炒圆白菜", 18.00, 1), (49, "米饭", 2.00, 2), (46, "王老吉", 6.00, 2)],
}
for sid_idx, dishes in setmeal_dishes_map.items():
    for d in dishes:
        cursor.execute(
            "INSERT INTO setmeal_dish (setmeal_id, dish_id, name, price, copies) VALUES (%s, %s, %s, %s, %s)",
            (setmeal_ids[sid_idx], d[0], d[1], d[2], d[3])
        )
print(f"  新增 {len(setmeals)} 个套餐")

# ============================================================
# 5. 订单 + 订单明细（核心！800+订单，覆盖2024-2026）
# ============================================================
print("生成订单数据（这是最大的一块，约800单）...")

# 菜品池（排除已停售的）
dish_pool = [
    (46, "王老吉", 6.00), (47, "北冰洋", 4.00), (48, "雪花啤酒", 4.00),
    (49, "米饭", 2.00), (50, "馒头", 1.00),
    (51, "老坛酸菜鱼", 56.00), (52, "经典酸菜鮰鱼", 66.00), (53, "蜀味水煮草鱼", 38.00),
    (54, "清炒小油菜", 18.00), (55, "蒜蓉娃娃菜", 18.00), (56, "清炒西兰花", 18.00), (57, "炝炒圆白菜", 18.00),
    (58, "清蒸鲈鱼", 98.00), (59, "东坡肘子", 138.00), (60, "梅菜扣肉", 58.00), (61, "剁椒鱼头", 66.00),
    (62, "金汤酸菜牛蛙", 88.00), (63, "香锅牛蛙", 88.00), (64, "馋嘴牛蛙", 88.00),
    (65, "草鱼2斤", 68.00), (66, "江团鱼2斤", 119.00), (67, "鮰鱼2斤", 72.00),
    (68, "鸡蛋汤", 4.00), (69, "平菇豆腐汤", 6.00),
]

# 高人气菜品（被点的概率更高）
popular_dishes = [49, 51, 53, 55, 62, 65, 68, 46]  # 米饭、酸菜鱼、牛蛙等

order_count = 0
statuses = [5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 3, 4]  # 80%已完成, 20%取消/其他

# 生成订单日期分布：2024全年 + 2025全年 + 2026上半年
dates = []
# 2024年：约250单
for _ in range(250):
    d = datetime(2024, random.randint(1, 12), random.randint(1, 28),
                 random.choices([11, 12, 17, 18, 19], weights=[15, 15, 30, 25, 15])[0],
                 random.randint(0, 59), random.randint(0, 59))
    dates.append(d)
# 2025年：约350单（生意变好了）
for _ in range(350):
    d = datetime(2025, random.randint(1, 12), random.randint(1, 28),
                 random.choices([11, 12, 17, 18, 19], weights=[15, 15, 30, 25, 15])[0],
                 random.randint(0, 59), random.randint(0, 59))
    dates.append(d)
# 2026年：约200单（到7月）
for _ in range(200):
    d = datetime(2026, random.randint(1, 7), random.randint(1, 28),
                 random.choices([11, 12, 17, 18, 19], weights=[15, 15, 30, 25, 15])[0],
                 random.randint(0, 59), random.randint(0, 59))
    dates.append(d)

random.shuffle(dates)

for order_date in dates:
    uid = random.choice(user_ids)
    # 找这个用户的地址
    cursor.execute("SELECT id FROM address_book WHERE user_id = %s", (uid,))
    user_addresses = [row[0] for row in cursor.fetchall()]
    if not user_addresses:
        continue
    aid = random.choice(user_addresses)

    status = random.choice(statuses)
    pay_method = random.choices([1, 2], weights=[70, 30])[0]  # 70%微信, 30%支付宝

    # 如果是取消订单，设置取消时间和原因
    cancel_time = None
    cancel_reason = None
    pay_status = 1  # 已支付
    checkout_time = order_date + timedelta(minutes=random.randint(1, 5))

    if status == 6:
        cancel_time = order_date + timedelta(minutes=random.randint(5, 30))
        cancel_reason = random.choice(["不想要了", "点错了", "等太久了", "临时有事"])
        pay_status = random.choice([0, 2])  # 未支付或退款
        checkout_time = None
    elif status == 1:
        pay_status = 0
        checkout_time = None

    # 决定这单点的是菜品还是套餐
    is_setmeal = random.random() < 0.25  # 25%概率点套餐

    order_details = []
    total_amount = 0

    if is_setmeal:
        # 点套餐
        sm_idx = random.randint(0, len(setmeal_ids) - 1)
        cursor.execute("SELECT name, price FROM setmeal WHERE id = %s", (setmeal_ids[sm_idx],))
        sm = cursor.fetchone()
        copies = random.choices([1, 2], weights=[80, 20])[0]
        order_details.append((None, setmeal_ids[sm_idx], None, copies, float(sm[1]) * copies, sm[0], None))
        total_amount = float(sm[1]) * copies
    else:
        # 点菜品（2-4个）
        num_items = random.choices([2, 3, 4], weights=[40, 40, 20])[0]
        # 必点米饭的概率很高
        selected = []
        if random.random() < 0.85:
            selected.append(49)  # 米饭
        # 再随机选几个
        available = [d[0] for d in dish_pool if d[0] not in selected]
        # 高人气菜品有更高概率被选中
        weights = [3 if d[0] in popular_dishes else 1 for d in dish_pool if d[0] in available]
        chosen = random.choices(available, weights=weights, k=min(num_items - len(selected), len(available)))
        selected.extend(chosen)

        for dish_id in selected:
            dish_info = next(d for d in dish_pool if d[0] == dish_id)
            copies = 1
            flavor = None
            if dish_id in [51, 52, 53, 62, 63, 64, 65, 66, 67]:
                flavor = random.choice(["不辣", "微辣", "中辣", "重辣"])
            elif dish_id in [46, 47, 48]:
                flavor = random.choice(["常温", "去冰", "少冰"])

            order_details.append((dish_id, None, flavor, copies, float(dish_info[2]) * copies, dish_info[1], None))
            total_amount += float(dish_info[2]) * copies

    # 加打包费
    pack_amount = random.choice([1, 2, 2, 3])
    total_amount += pack_amount

    # 插入订单
    order_number = str(int(order_date.timestamp() * 1000) + random.randint(0, 999))
    delivery_time = order_date + timedelta(minutes=random.randint(30, 60))

    cursor.execute(
        "INSERT INTO orders (number, status, user_id, address_book_id, order_time, checkout_time, "
        "pay_method, pay_status, amount, remark, phone, address, user_name, consignee, "
        "cancel_reason, cancel_time, estimated_delivery_time, delivery_status, delivery_time, "
        "pack_amount, tableware_number, tableware_status) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (order_number, status, uid, aid, order_date, checkout_time,
         pay_method, pay_status, round(total_amount, 2),
         random.choice(["", "", "", "少放辣", "多放醋", "不要葱姜蒜", "请尽快送达"]),
         f"138{random.randint(10000000, 99999999)}",
         f"北京市{random.choice(streets)}{random.randint(1,200)}号",
         f"用户{uid}", f"收货人{uid}",
         cancel_reason, cancel_time,
         delivery_time if status in [3, 4, 5] else None,
         1, delivery_time if status == 5 else None,
         pack_amount, random.choice([1, 2, 2, 3]), 1)
    )
    order_id = cursor.lastrowid
    order_count += 1

    # 插入订单明细
    for detail in order_details:
        cursor.execute(
            "INSERT INTO order_detail (name, image, order_id, dish_id, setmeal_id, dish_flavor, number, amount) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (detail[5],
             f"https://sky-itcast.oss-cn-beijing.aliyuncs.com/dish{detail[0] or 0}.png",
             order_id, detail[0], detail[1], detail[2], detail[3], round(detail[4], 2))
        )

print(f"  新增 {order_count} 个订单")

# ============================================================
# 提交所有更改
# ============================================================
conn.commit()
cursor.close()
conn.close()

print("\n✅ 测试数据生成完成！")
print(f"   员工: +{len(employees)}")
print(f"   用户: +{len(user_ids)}")
print(f"   地址: +{len(address_ids)}")
print(f"   套餐: +{len(setmeals)}")
print(f"   订单: +{order_count}")
