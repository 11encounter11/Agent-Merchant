"""
订单操作工具

提供接单、拒单等修改数据的操作。
这些操作需要调用 Java 后端的 REST API（不能直接改数据库）。

为什么不能直接改数据库？
因为 Java 后端有完整的业务逻辑（校验订单状态、发通知、更新缓存等），
如果在 Python 侧重写一遍，容易跟 Java 端不一致。
"""

import httpx
from langchain_core.tools import tool
from config import settings


# ============================================================
# Token 管理
# ============================================================
# Java 后端需要 JWT token 才能执行操作。
# 我们需要先登录拿到 token，然后在后续请求中带上它。
#
# 登录方式：POST /admin/employee/login
#   请求体：{"username": "admin", "password": "123456"}
#   响应：{"code": 1, "data": {"token": "jwt_xxx..."}}
#
# 后续请求带 token 的方式：
#   请求头：token: jwt_xxx...
# ============================================================

_admin_token: str | None = None


async def _get_admin_token() -> str:
    """
    获取管理员 token。如果已有缓存的 token 就直接用，没有就登录获取。
    """
    global _admin_token
    if _admin_token:
        return _admin_token

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.JAVA_BACKEND_URL}/admin/employee/login",
            json={"username": "admin", "password": "123456"}
        )
        data = response.json()
        if data.get("code") == 1:
            _admin_token = data["data"]["token"]
            return _admin_token
        else:
            raise Exception(f"登录 Java 后端失败：{data.get('msg', '未知错误')}")


async def _call_java_api(method: str, path: str, **kwargs) -> dict:
    """
    调用 Java 后端 API 的通用函数。

    参数：
        method: HTTP 方法（"GET", "POST", "PUT" 等）
        path: API 路径，例如 "/admin/order/confirm"
        **kwargs: 传给 httpx 的额外参数（json, params 等）
    """
    token = await _get_admin_token()
    headers = {"token": token}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(
            method,
            f"{settings.JAVA_BACKEND_URL}{path}",
            headers=headers,
            **kwargs
        )

    result = response.json()

    # 如果 token 过期了（返回 401），重新登录再试一次
    if response.status_code == 401:
        global _admin_token
        _admin_token = None
        token = await _get_admin_token()
        headers = {"token": token}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method,
                f"{settings.JAVA_BACKEND_URL}{path}",
                headers=headers,
                **kwargs
            )
        result = response.json()

    return result


# ============================================================
# Tool 定义
# ============================================================

@tool
async def accept_order(order_id: int) -> str:
    """
    接受一个待接单的订单。

    参数：
        order_id: 订单ID（数字）

    使用场景：
        - "帮我接一下订单 123"
        - "把那个待接单的单子接了"

    注意：只有状态为"待接单"（status=2）的订单才能接单。
    """
    result = await _call_java_api(
        "PUT",
        "/admin/order/confirm",
        json={"id": order_id}
    )

    if result.get("code") == 1:
        return f"订单 {order_id} 已接单成功！"
    else:
        return f"接单失败：{result.get('msg', '未知错误')}"


@tool
async def reject_order(order_id: int, reason: str) -> str:
    """
    拒绝一个待接单的订单。

    参数：
        order_id: 订单ID（数字）
        reason: 拒单原因（必填），例如 "菜品已售罄"、"配送范围超出"

    使用场景：
        - "拒绝订单 456，原因是菜品卖完了"
        - "帮我拒一下那个单"
    """
    result = await _call_java_api(
        "PUT",
        "/admin/order/rejection",
        json={"id": order_id, "reason": reason}
    )

    if result.get("code") == 1:
        return f"订单 {order_id} 已拒单。原因：{reason}"
    else:
        return f"拒单失败：{result.get('msg', '未知错误')}"


@tool
async def stop_dish(dish_id: int) -> str:
    """
    停售一个菜品。停售后该菜品将不再展示给顾客。

    参数：
        dish_id: 菜品ID（数字）

    使用场景：
        - "把东坡肘子停售了"
        - "停售菜品 ID 59"

    注意：停售菜品前请确认，因为关联的套餐也会被一起停售。
    """
    result = await _call_java_api(
        "POST",
        f"/admin/dish/status/0",
        params={"id": dish_id}
    )

    if result.get("code") == 1:
        return f"菜品 ID {dish_id} 已停售。注意：包含该菜品的套餐也会被自动停售。"
    else:
        return f"停售失败：{result.get('msg', '未知错误')}"


@tool
async def start_dish(dish_id: int) -> str:
    """
    起售一个已停售的菜品。

    参数：
        dish_id: 菜品ID（数字）

    使用场景：
        - "把东坡肘子重新上架"
        - "起售菜品 ID 59"
    """
    result = await _call_java_api(
        "POST",
        f"/admin/dish/status/1",
        params={"id": dish_id}
    )

    if result.get("code") == 1:
        return f"菜品 ID {dish_id} 已重新起售！"
    else:
        return f"起售失败：{result.get('msg', '未知错误')}"
