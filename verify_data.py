import pymysql
from config import settings
conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER, password=settings.DB_PASSWORD, database=settings.DB_NAME, charset='utf8mb4')
c = conn.cursor()

print('=== 数据统计 ===')
c.execute('SELECT COUNT(*) FROM user'); print(f'用户总数: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM employee'); print(f'员工总数: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM orders'); print(f'订单总数: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM order_detail'); print(f'订单明细数: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM setmeal'); print(f'套餐数: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM address_book'); print(f'地址数: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM dish'); print(f'菜品数: {c.fetchone()[0]}')

print()
print('=== 订单年份分布 ===')
c.execute('SELECT YEAR(order_time), COUNT(*) FROM orders GROUP BY YEAR(order_time) ORDER BY 1')
for row in c.fetchall(): print(f'  {row[0]}年: {row[1]}单')

print()
print('=== 订单状态分布 ===')
c.execute('SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status')
status_map = {1:'待付款',2:'待接单',3:'已接单',4:'派送中',5:'已完成',6:'已取消',7:'退款'}
for row in c.fetchall(): print(f'  {status_map.get(row[0], row[0])}: {row[1]}单')

print()
print('=== 总营业额（已完成订单）===')
c.execute('SELECT COALESCE(SUM(amount),0) FROM orders WHERE status=5')
print(f'  {float(c.fetchone()[0]):.2f} 元')

c.execute('SELECT YEAR(order_time), COALESCE(SUM(amount),0) FROM orders WHERE status=5 GROUP BY YEAR(order_time) ORDER BY 1')
print()
print('=== 各年营业额 ===')
for row in c.fetchall(): print(f'  {row[0]}年: {float(row[1]):.2f} 元')

conn.close()
