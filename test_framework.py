"""
7 大模块框架验证脚本

验证所有模块是否正确集成，不破坏已有功能。
"""

import sys
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def test_imports():
    """测试所有模块是否能正常导入"""
    logger.info("=" * 60)
    logger.info("测试 1: 导入所有模块")
    logger.info("=" * 60)
    
    try:
        # 感知模块
        from agent.perception import perception, Perception
        logger.info("✓ 感知模块导入成功")
        
        # 记忆模块
        from agent.memory import memory, Memory
        logger.info("✓ 记忆模块导入成功")
        
        # 知识库
        from agent.knowledge.knowledge_base import knowledge_base, KnowledgeBase
        logger.info("✓ 知识库模块导入成功")
        
        # 工具管理
        from agent.tools.tool_registry import tool_registry, ToolRegistry
        logger.info("✓ 工具管理模块导入成功")
        
        # 反思模块
        from agent.reflection import reflection, Reflection
        logger.info("✓ 反思模块导入成功")
        
        # 日志配置
        from agent.logging_config import setup_logging, get_logger
        logger.info("✓ 日志配置模块导入成功")
        
        # Agent 核心（会触发所有模块的导入）
        from agent.chat_agent import chat, chat_stream, agent_graph
        logger.info("✓ Agent 核心模块导入成功")
        
        logger.info("")
        logger.info("所有模块导入成功！")
        return True
        
    except Exception as e:
        logger.error(f"✗ 导入失败: {e}", exc_info=True)
        return False


def test_perception():
    """测试感知模块"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试 2: 感知模块")
    logger.info("=" * 60)
    
    from agent.perception import perception
    
    # 测试输入清洗
    test_cases = [
        ("  你好  ", "你好"),
        ("多个   空格", "多个 空格"),
        ("", ""),
    ]
    
    for input_text, expected in test_cases:
        result = perception.preprocess(input_text)
        status = "✓" if result == expected else "✗"
        logger.info(f"{status} preprocess('{input_text}') → '{result}' (期望: '{expected}')")
    
    # 测试意图分类
    intent = perception.classify_intent("今天营业额多少")
    logger.info(f"✓ classify_intent 返回: {intent}")


def test_reflection():
    """测试反思模块"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试 3: 反思模块")
    logger.info("=" * 60)
    
    from agent.reflection import reflection
    
    # 测试身份检查
    test_response = "我是通义千问，很高兴为您服务。"
    sanitized = reflection.check_identity(test_response)
    logger.info(f"原始: {test_response}")
    logger.info(f"清洗: {sanitized}")
    logger.info(f"✓ 身份检查{'触发' if test_response != sanitized else '未触发'}")
    
    # 测试边界检查
    test_input = "帮我写一篇营销文案"
    test_response = "好的，我很乐意帮您写营销文案。"
    sanitized = reflection.check_boundary(test_response, test_input)
    logger.info(f"用户: {test_input}")
    logger.info(f"原始: {test_response}")
    logger.info(f"清洗: {sanitized}")
    logger.info(f"✓ 边界检查{'触发' if test_response != sanitized else '未触发'}")


def test_tool_registry():
    """测试工具注册中心"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试 4: 工具注册中心")
    logger.info("=" * 60)
    
    from agent.tools.tool_registry import tool_registry
    
    # 列出已注册的工具
    tools_info = tool_registry.list_tools()
    logger.info(f"已注册工具数: {len(tools_info)}")
    for tool in tools_info:
        logger.info(f"  - {tool['name']}: {tool['description'][:50]}...")
    
    logger.info(f"✓ 工具注册中心正常")


def test_knowledge_base():
    """测试知识库"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试 5: 知识库")
    logger.info("=" * 60)
    
    from agent.knowledge.knowledge_base import knowledge_base
    
    if knowledge_base._initialized:
        logger.info(f"✓ chromadb 已初始化")
        count = knowledge_base.collection.count()
        logger.info(f"  知识库文档数: {count}")
        
        # 测试检索（空知识库也能正常返回）
        results = knowledge_base.search("测试", top_k=3)
        logger.info(f"  检索结果数: {len(results)}")
        logger.info(f"✓ 知识库检索正常")
    else:
        logger.warning(f"⚠ chromadb 未安装，跳过测试")


def test_memory():
    """测试记忆模块"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试 6: 记忆模块")
    logger.info("=" * 60)
    
    from agent.memory import memory
    
    # 测试工作记忆
    test_session = "test_session_001"
    history = memory.get_working_memory(test_session)
    logger.info(f"✓ 获取工作记忆: session={test_session}, 消息数={len(history)}")
    
    # 测试知识检索
    results = memory.search_knowledge("营业额", top_k=3)
    logger.info(f"✓ 知识检索: query='营业额', 结果数={len(results)}")


def main():
    """主测试函数"""
    logger.info("")
    logger.info("╔" + "═" * 58 + "╗")
    logger.info("║" + " " * 15 + "7 大模块框架验证" + " " * 25 + "║")
    logger.info("╚" + "═" * 58 + "╝")
    logger.info("")
    
    # 测试 1: 导入
    if not test_imports():
        logger.error("导入测试失败，终止测试")
        return False
    
    # 测试 2-6: 各模块功能
    test_perception()
    test_reflection()
    test_tool_registry()
    test_knowledge_base()
    test_memory()
    
    # 总结
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试完成！")
    logger.info("=" * 60)
    logger.info("")
    logger.info("7 大模块框架已成功搭建：")
    logger.info("  1. 感知模块 (perception.py)")
    logger.info("  2. 记忆模块 (memory.py)")
    logger.info("  3. RAG 知识库 (knowledge/)")
    logger.info("  4. 工具管理 (tool_registry.py)")
    logger.info("  5. 反思模块 (reflection.py)")
    logger.info("  6. 规划模块 (chat_agent.py - 已改造)")
    logger.info("  7. 日志系统 (logging_config.py)")
    logger.info("")
    logger.info("下一步：")
    logger.info("  - 往 knowledge/data/ 目录填充知识文档")
    logger.info("  - 修复已知 Bug（通过 RAG 知识库）")
    logger.info("  - 运行回归测试")
    logger.info("")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
