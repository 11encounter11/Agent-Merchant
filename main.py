"""
============================================================
苍穹外卖 - 商家智能助手 Agent 服务入口
============================================================

【教学说明】这个文件是干什么的？
类比 Java 的 SkyApplication.java —— 这是整个服务的"启动入口"。
你运行这个文件，服务就起来了；别人访问你定义的 URL，就能得到响应。

【教学说明】FastAPI vs Spring Boot 类比对照表：
    Java (Spring Boot)                    Python (FastAPI)
    ─────────────────────────────────     ────────────────────────────────
    @RestController                       app = FastAPI()
    @GetMapping("/health")                @app.get("/health")
    @PostMapping("/api/chat")             @app.post("/api/chat")
    @RequestBody ChatDTO                  async def chat(request: ChatRequest)
    return Result.success(data)           return {"code": 1, "data": data}

你会发现 FastAPI 的写法更简洁，但做的事情是一样的。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings

# ============================================================
# 第一步：创建 FastAPI 应用实例
# 类比 Java：@SpringBootApplication 启动类
# ============================================================
app = FastAPI(
    title=settings.APP_NAME,        # 应用名称，会显示在自动生成的API文档里
    description="面向外卖商家的智能经营助手 API",
    version="0.1.0"                 # 版本号
)

# ============================================================
# 第二步：配置跨域（CORS）
# ============================================================
# 【教学说明】什么是跨域？
# 你的前端跑在 http://localhost:8888
# 你的 Agent 服务跑在 http://localhost:8100
# 端口不同 = "跨域"。浏览器默认会拦截跨域请求（安全策略）。
# 所以需要在这里告诉 Agent 服务："允许 8888 端口的前端来访问我"。
#
# 类比 Java：Spring Boot 里你写 @CrossOrigin 或者 WebMvcConfigurer 来做这件事。
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # 允许所有来源（开发阶段方便调试，上线后要限制）
    allow_credentials=True,         # 允许携带 Cookie
    allow_methods=["*"],            # 允许所有 HTTP 方法（GET/POST/PUT/DELETE）
    allow_headers=["*"],            # 允许所有请求头
)


# ============================================================
# 第三步：定义接口（路由）
# 类比 Java：@GetMapping、@PostMapping
# ============================================================

@app.get("/health")
async def health_check():
    """
    健康检查接口。
    类比 Java 的：
        @GetMapping("/health")
        public Result<String> health() {
            return Result.success("ok");
        }

    【教学说明】async def 是什么？
    async = 异步函数。普通函数（def）是"排队执行"，
    异步函数（async def）是"可以同时处理多个请求"。
    对于健康检查这种简单接口，加不加 async 效果一样，
    但养成习惯用 async，后面调 LLM、查数据库时都需要异步。
    """
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": "0.1.0"
    }


@app.get("/")
async def root():
    """
    根路径接口，返回简单的欢迎信息。
    你在浏览器访问 http://localhost:8100 就会看到这个。
    """
    return {
        "message": "欢迎使用苍穹外卖商家智能助手 Agent 服务！",
        "docs": "/docs",          # FastAPI 自动生成的接口文档地址
        "health": "/health"
    }


# ============================================================
# 第四步：启动入口
# 类比 Java：SpringApplication.run(SkyApplication.class, args)
# ============================================================
#
# 【教学说明】怎么启动这个服务？
# 在终端运行：uvicorn main:app --host 0.0.0.0 --port 8100 --reload
#
# 拆解一下：
# - uvicorn        → 服务器（类比 Tomcat）
# - main:app       → main.py 文件里的 app 变量（就是上面创建的 FastAPI 实例）
# - --host 0.0.0.0 → 监听所有网络接口
# - --port 8100    → 端口号
# - --reload       → 代码改了自动重启（开发阶段很方便！）
#
# 类比 Java：
#   你在 IDEA 里点 "Run SkyApplication"
#   = 在终端跑 "uvicorn main:app"
#   只是换了一套工具而已。
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True    # 开发模式：改了代码自动重启
    )
