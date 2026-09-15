"""直接测试 Java API 调用"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.tools.order_action_tools import _get_admin_token, _call_java_api

async def test():
    # 1. 获取 token
    token = await _get_admin_token()
    print(f'Token obtained: {token[:30]}...')

    # 2. 测试停售菜品 ID 50
    print('\n--- 测试停售菜品 ID 50 ---')
    result = await _call_java_api('POST', '/admin/dish/status/0', params={'id': 50})
    print(f'Result: {result}')

    # 3. 测试起售菜品 ID 50
    print('\n--- 测试起售菜品 ID 50 ---')
    result = await _call_java_api('POST', '/admin/dish/status/1', params={'id': 50})
    print(f'Result: {result}')

asyncio.run(test())
