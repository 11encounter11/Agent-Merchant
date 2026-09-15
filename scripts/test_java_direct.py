"""测试 Java 菜品接口（完整错误输出）"""
import httpx, asyncio

async def test():
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post('http://localhost:8080/admin/employee/login',
            json={"username": "admin", "password": "123456"})
        token = r.json()['data']['token']

        print('--- 停售菜品 50 ---')
        r = await client.post('http://localhost:8080/admin/dish/status/0',
            params={'id': 50}, headers={'token': token})
        print(f'Status: {r.status_code}')
        print(f'Body: {r.text}')

asyncio.run(test())
