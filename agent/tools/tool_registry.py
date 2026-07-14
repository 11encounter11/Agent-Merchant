"""
工具管理模块（Tool Registry）

职责：统一管理所有 Tool 的注册、调用、错误处理、日志。

对照文章的 7 大模块：
- 文章方案：工具注册中心 + 熔断降级 + 限流
- 我们方案：简化版，只做注册、日志、错误处理
- 未来可以扩展：熔断、限流、权限控制

为什么需要这个模块？
1. 统一记录每次 Tool 调用（名称、参数、结果、耗时）
2. 统一错误处理：Tool 异常时返回友好提示，而不是堆栈
3. 方便调试：看日志就知道 LLM 调了哪些 Tool、传了什么参数
4. 为后续熔断降级留接口

类比 Java：
就像 Spring 的 AOP（面向切面编程），在方法调用前后统一加日志和异常处理。
"""

import time
import logging
from typing import List, Dict, Any
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    工具注册中心：统一管理所有 Tool 的注册、调用、日志。
    
    类比 Java：
    就像一个 ToolService，封装了所有工具的调用逻辑：
    - register() → 注册工具（类似 @Bean 注册到 Spring 容器）
    - execute() → 调用工具（类似 Service 调用 DAO）
    - list_tools() → 列出所有工具（类似查看容器里有哪些 Bean）
    """
    
    def __init__(self, tools: List[BaseTool] = None):
        """
        初始化工具注册中心。
        
        参数：
            tools: 工具列表（LangChain 的 Tool 对象）
        """
        self.tools: Dict[str, BaseTool] = {}
        self.call_count: Dict[str, int] = {}  # 记录每个工具的调用次数
        
        if tools:
            for tool in tools:
                self.register(tool)
    
    def register(self, tool: BaseTool):
        """
        注册一个工具。
        
        参数：
            tool: LangChain Tool 对象
        
        类比 Java：
        applicationContext.registerBean(tool.name, tool)
        """
        self.tools[tool.name] = tool
        self.call_count[tool.name] = 0
        logger.info(f"[ToolRegistry] 注册工具: {tool.name}")
    
    async def execute(self, tool_name: str, params: Dict[str, Any]) -> str:
        """
        统一执行入口：带日志、错误处理、耗时统计。
        
        参数：
            tool_name: 工具名称
            params: 工具参数（字典）
        
        返回：
            工具执行结果（字符串）
        
        做了什么：
        1. 记录调用开始
        2. 执行工具（ainvoke 是异步调用）
        3. 记录调用结果和耗时
        4. 异常时返回友好错误信息
        
        类比 Java：
        @Around("execution(* com.example.tools.*.*(..))")
        public Object around(ProceedingJoinPoint pjp) {
            long start = System.currentTimeMillis();
            try {
                Object result = pjp.proceed();
                log.info("Tool {} 耗时 {}ms", pjp.getSignature().getName(), 
                         System.currentTimeMillis() - start);
                return result;
            } catch (Exception e) {
                log.error("Tool 执行失败", e);
                return "工具执行失败: " + e.getMessage();
            }
        }
        """
        if tool_name not in self.tools:
            logger.error(f"[ToolRegistry] 工具不存在: {tool_name}")
            return f"工具 {tool_name} 不存在"
        
        # 调用次数 +1
        self.call_count[tool_name] += 1
        call_id = self.call_count[tool_name]
        
        # 记录调用开始
        start_time = time.time()
        logger.info(f"[ToolRegistry] 调用工具 #{call_id}: {tool_name}, 参数: {params}")
        
        try:
            # 执行工具（ainvoke 是异步调用）
            tool = self.tools[tool_name]
            result = await tool.ainvoke(params)
            
            # 记录调用结果
            latency = time.time() - start_time
            logger.info(f"[ToolRegistry] 工具完成 #{call_id}: {tool_name}, 耗时 {latency:.2f}s, 结果: {result[:100]}...")
            
            return result
        
        except Exception as e:
            # 异常时返回友好错误信息
            latency = time.time() - start_time
            logger.error(f"[ToolRegistry] 工具失败 #{call_id}: {tool_name}, 耗时 {latency:.2f}s, 错误: {e}", exc_info=True)
            return f"工具 {tool_name} 执行失败：{str(e)}"
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        列出所有已注册工具的信息。
        
        返回：
            工具信息列表
        
        类比 Java：
        applicationContext.getBeanDefinitionNames()
        """
        result = []
        for name, tool in self.tools.items():
            result.append({
                "name": name,
                "description": tool.description,
                "call_count": self.call_count[name]
            })
        return result
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取工具调用统计。
        
        返回：
            调用次数字典：{tool_name: count}
        """
        return self.call_count.copy()


# 全局实例（在 chat_agent.py 中初始化）
tool_registry = ToolRegistry()
