import uvicorn
from fastapi import FastAPI, HTTPException
from app.logging_config import logger
from app.settings import load_environment
from app.models import QueryRequest
from app.openai_utils import parse_query_to_sql
from app.sql_validation import validate_sql_query
from app.db import execute_sql_query
from app.formatting import format_for_echarts
from app.milvus_utils import connect_milvus, get_or_create_collection, insert_data, search_similar_question

# 加载环境变量
ENV = load_environment()
app = FastAPI()


# 处理查询请求的路由
@app.post("/query")
def handle_query(request: QueryRequest):
    try:
        user_input = request.user_input

        # 连接到 Milvus 并获取集合
        connect_milvus()
        collection = get_or_create_collection()

        # 搜索相似问题
        search_results = search_similar_question(collection, user_input)
        if search_results and search_results[0][0].score > 0.8:
            # 如果找到高相似度的问题，直接使用对应的 SQL 查询
            sql_query = search_results[0][0].entity.get("sql_query")
            logger.info(f"使用相似问题的 SQL 查询: {sql_query}")
        else:
            # 否则，调用 OpenAI API 解析新问题
            sql_query = parse_query_to_sql(user_input)
            validate_sql_query(sql_query)
            # 将新问题和 SQL 查询添加到知识库中
            insert_data(collection, [user_input], [sql_query])

        data = execute_sql_query(sql_query)
        echarts_data = format_for_echarts(data)
        return {"echarts_data": echarts_data}
    except Exception as e:
        logger.error(f"处理查询 '{request.user_input}' 时出错: {e}")
        # 开发环境返回详细错误信息
        if ENV == 'development':
            raise HTTPException(status_code=500, detail=str(e))
        else:
            raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试。")


# 运行 FastAPI 服务器
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=13000)
