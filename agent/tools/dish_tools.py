"""
菜品查询工具

提供菜品列表、菜品详情等查询能力。
直接查 MySQL 数据库。
"""

from langchain_core.tools import tool
from db.database import execute_query


@tool
async def query_dish_list(category_name: str = "") -> str:
    """
    查询菜品列表。

    参数：
        category_name: 分类名称（可选）。为空时返回所有起售中的菜品。
                       例如 "蜀味烤鱼"、"酒水饮料"、"新鲜时蔬"

    使用场景：
        - "现在有哪些菜品？"
        - "蜀味烤鱼分类下有什么菜？"
        - "目前在售的菜品有多少？"
    """
    if category_name:
        sql = """
            SELECT d.id, d.name, d.price, d.status, c.name as category_name
            FROM dish d
            JOIN category c ON d.category_id = c.id
            WHERE c.name = %s AND d.status = 1
            ORDER BY d.id
        """
        rows = await execute_query(sql, (category_name,))
    else:
        sql = """
            SELECT d.id, d.name, d.price, d.status, c.name as category_name
            FROM dish d
            JOIN category c ON d.category_id = c.id
            WHERE d.status = 1
            ORDER BY c.sort, d.id
        """
        rows = await execute_query(sql)

    if not rows:
        return f"没有找到{'分类 ' + category_name + ' 下的' if category_name else ''}在售菜品。"

    lines = [f"共 {len(rows)} 个在售菜品：\n"]
    current_cat = ""
    for r in rows:
        if r["category_name"] != current_cat:
            current_cat = r["category_name"]
            lines.append(f"\n【{current_cat}】")
        lines.append(f"  - {r['name']}：{float(r['price']):.0f} 元")

    return "\n".join(lines)


@tool
async def query_dish_by_name(dish_name: str) -> str:
    """
    根据菜品名称查询菜品详情。

    参数：
        dish_name: 菜品名称（支持模糊匹配）

    使用场景：
        - "东坡肘子多少钱？"
        - "查一下酸菜鱼的详情"
        - "有没有牛蛙相关的菜？"
    """
    sql = """
        SELECT d.id, d.name, d.price, d.status, d.description, c.name as category_name
        FROM dish d
        JOIN category c ON d.category_id = c.id
        WHERE d.name LIKE %s
        ORDER BY d.id
    """
    rows = await execute_query(sql, (f"%{dish_name}%",))

    if not rows:
        return f"没有找到包含 {dish_name} 的菜品。"

    lines = [f"找到 {len(rows)} 个相关菜品：\n"]
    for r in rows:
        status_text = "在售" if r["status"] == 1 else "已停售"
        desc = r["description"] or "无"
        lines.append(
            f"  - {r['name']}（{r['category_name']}）\n"
            f"    价格：{float(r['price']):.0f} 元 | 状态：{status_text}\n"
            f"    描述：{desc}"
        )

    return "\n".join(lines)
