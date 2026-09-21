"""
苍穹外卖 - 商家智能经营顾问 Agent

核心模块：
- state.py:       AgentState 定义
- constants.py:   跨模块共享常量（单一真值）
- llm.py:         LLM 工厂 + 模型路由
- graph.py:       LangGraph 图编排（取图只用 get_agent_graph()）
- workers/:       图节点（一节点一文件）
- prompts.py:     System Prompt 集中管理
- service.py:     对外服务接口（chat / chat_stream）
- perception.py:  感知层（意图识别 + 情境注入）
- reflection.py:  反思层（输出安全校验）
- messages.py:    消息清洗工具函数
"""

from agent.service import chat, chat_stream

__all__ = ["chat", "chat_stream"]
