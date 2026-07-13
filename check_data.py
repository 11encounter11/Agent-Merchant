import pymysql
from config import settings
conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER, password=settings.DB_PASSWORD, database=settings.DB_NAME, charset='utf8mb4')
c = conn.cursor()
print('=== 各状态订单数 ===')
c.execute('SELECT status, COUNT(*) FROM orders GROUP BY status')
sm = {1:'待付款',2:'待接单',3:'已接单',4:'派送中',5:'已完成',6:'已取消',7:'退款'}
for r in c.fetchall(): print(f'  {sm.get(r[0],r[0])}(status={r[0]}): {r[1]}单')

print('\n=== 最近5个订单 ===')
c.execute('SELECT id, number, amount, status FROM orders ORDER BY id DESC LIMIT 5')
for r in c.fetchall(): print(f'  ID={r[0]}, 号={r[1]}, 金额={r[2]}, 状态={r[3]}')

print('\n=== 菜品参考 ===')
c.execute('SELECT id, name, status FROM dish LIMIT 5')
for r in c.fetchall():
    st = "在售" if r[2]==1 else "停售"
    print(f'  ID={r[0]}, {r[1]}, {st}')
conn.close()
