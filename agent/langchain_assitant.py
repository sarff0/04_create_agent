"""
用来定义agent的主要代码
"""

from langchain.tools import tool
import pymysql
import os
from dotenv import load_dotenv
from pathlib import Path
from pymysql.cursors import DictCursor
from sqlalchemy import text


root_path = Path(__file__).parent.parent
load_dotenv()
embeddings = None
milvus_client = None
engine = None
agent = None

def get_embeddings():
    global embeddings
    if embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(model=str(root_path / "models" / "bge-m3"))
    return embeddings

def get_milvus_client():
    global milvus_client
    if milvus_client is None:
        import pymilvus
        milvus_client = pymilvus.MilvusClient(uri=os.getenv("MILVUS_URL"), token=os.getenv("MILVUS_TOKEN"))
    return milvus_client

def mysql_connection():
    global engine
    if engine is None:
        from sqlalchemy import create_engine
        engine = create_engine(
            url=f"mysql+pymysql://{os.getenv('MYSQL_USERNAME')}:{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}/{os.getenv('MYSQL_DATABASE')}?charset=utf8mb4",
            pool_size=15
        )
        
    return engine

@tool
def search_main_dishes():
    """
    搜索主菜的工具函数
    """
    key_name_mapping = {
        "dish_name": "菜品名称",
        "price": "价格",
        "description": "描述",
        "category": "类别",
        "spice_level": "辣度等级",
        "flavor": "口味",   
        "main_ingredients": "主要食材",
        "cooking_method": "烹饪方法",
        "is_vegetarian": "是否素食",
        "allergens": "过敏原"
    }
    with pymysql.connect(host=os.getenv("MYSQL_HOST"),
                          user=os.getenv("MYSQL_USERNAME"), 
                          password=os.getenv("MYSQL_PASSWORD"), 
                          port=int(os.getenv("MYSQL_PORT") ),
                          cursorclass=pymysql.cursors.DictCursor) as conn:
        with conn.cursor(DictCursor) as cursor:
            sql = """
                select
                    dish_name,
                    price,
                    description,
                    category,
                    spice_level,
                    flavor,
                    main_ingredients,
                    cooking_method,
                    is_vegetarian,
                    allergens
                from
                    menu.menu_items
                where
                    is_featured = 1
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            # 定义json的键，将数据封装成json
            json_results = []
            for item in results:
                json_item = {}
                for key, value in item.items():
                    json_key = key_name_mapping[key]
                    json_item[json_key] = value
                json_results.append(json_item)
            return json_results

@tool
def user_flavor_search(user_query: str):
    """
    根据用户的口味偏好,去查找相关菜品
    """
    # 1.构建用户query的向量
    embeddings = get_embeddings()

    query_vector = embeddings.embed_query(user_query)

    # 2.连接milvus,进行向量检索
    client = get_milvus_client()

    # 3.进行向量搜索
    search_res = client.search(
        collection_name="menu_items",
        data=[query_vector],
        anns_field="vector",
        output_fields=["text"],
        limit=3
    )

    # 4.解析搜索结果
    if search_res:
        all_results = search_res[0]
        # all_results是一个列表,每个元素是一个搜索结果
        final_results = []
        for res in all_results:
            text = res.entity.get("text")
            final_results.append(text)
        return final_results
    else:
        return "没有找到相关菜品"

from pydantic import BaseModel, Field
class ReservationToolArgsInfo(BaseModel):
    num_people: int = Field(..., description="预定的人数")
    num_children: int = Field(..., description="预定的儿童人数")
    arrival_time: str = Field(..., description="到达时间,格式为YYYY-MM-DD HH")
    set_preference: str = Field(..., description="座位偏好，例如靠窗、靠近厨房等,当客户没有特别的偏好时，传入空字符串")
    main_dish_preference: str = Field(..., description="主菜偏好，例如喜欢吃辣的菜、不吃海鲜等,当客户没有特别的偏好时，传入空字符串")
    comments: str = Field(..., description="其他备注信息,当客户没有特别的偏好时，传入空字符串")

@tool(args_schema=ReservationToolArgsInfo)
def make_reservation(num_people:int,num_children:int,arrival_time:str,set_preference:str,main_dish_preference:str,comments:str):
    """
    用来进行餐厅预定的工具：
    通过MYSQL向数据库中插入预定信息
    """
    engine = mysql_connection()
    with engine.connect() as conn:
        sql = """
            insert into reservation_order (num_people, num_children, arrival_time, seat_preference, main_dish_preference, other_comments)
            values (:num_people, :num_children, :arrival_time, :set_preference, :main_dish_preference, :comments)
        """
        conn.execute(statement=text(sql), parameters={'num_people': num_people, 'num_children': num_children, 'arrival_time': arrival_time, 'set_preference': set_preference, 'main_dish_preference': main_dish_preference, 'comments': comments})
        conn.commit()
        return "预定成功"

async def assisrant_query(user_query: str):
    """
    接收来自前端的用户query,使用agent进行回复
    """
    agent = await create_agent()
    # 1.调用前，新添加一个system prompt，让agent感知当前的时间
    from datetime import datetime
    from langchain.messages import ToolMessage
    current_time = datetime.now().strftime("%Y-%m-%d")
    time_system_prompt = {"role": "system", "content": f"当前的日期是{current_time},请基于这个日期来回答用户的问题"}

    # 2.config如何去构建：在实际的生产环境下，每个用户的每一次会话，在后端系统当中，都会有一个session_id，可以拿这个session_id作为thread_id传进去
    config = {"configurable":{"thread_id": "123"}}
    # res = await agent.ainvoke({"message":[time_system_prompt,{"role":"user","content":user_query}]}, config=config)
    
    # 3.如何去调用agent：通过流式输出
    async for chunk in agent.astream({"message":[time_system_prompt,{"role":"user","content":user_query}]}, config=config,stream_mode="messages"):
        # chunk首先一个tuple：(AIMessgeChunk/ToolMessage,_)
        message_chunk = chunk[0]

        # 过滤toolmessage
        if type(message_chunk) == ToolMessage:
            continue
        # 这个message需要通过什么方式，给到谁：需要通过接口方式，给到前端，然后去展示在用户界面上
        # SSE:Server-Sent Events,是一种服务器推送技术，可以实现服务器向客户端的单向实时通信
        # SSE的数据结构：data:{"type":"token","content":"你好"}

        # 快速的将这个方法传出的token，给到后端接口，让后端接口去输出给前端
        import json
        payload = {"content": message_chunk.content, "type": "token"}
        payload_str = json.dumps(payload, ensure_ascii=False)
        yield f"data:{payload_str}\n\n"


async def create_agent():
    global agent
    if agent is None:
        from langchain.agents import create_agent
        from langchain_openai import ChatOpenAI
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langgraph.checkpoint.memory import InMemorySaver
        # from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        # import sqlite3

        checkpointer = InMemorySaver()

        client = MultiServerMCPClient(
            connections={
                "amap-maps": {
                "transport": "streamable_http",
                "url": "https://mcp.api-inference.modelscope.ai/c7e97709cdbd47/mcp"
                }
            }
        )

        llm = ChatOpenAI(model="qwen3-max")
        with open(str(root_path / "agent" / "prompts"/ "system_prompt.txt"),encoding="utf-8",mode="r") as f:
            system_prompt = f.read()

        mcp_tools = await client.get_tools()

        agent = create_agent(
            model = llm,
            system_prompt = system_prompt,
            tools = [search_main_dishes, user_flavor_search, make_reservation]+ mcp_tools,
            checkpointer = checkpointer
        )
    return agent
    
async def run_agent():
    agent = await create_agent()
    config = {"configurable":{"thread_id": "123"}}
    res = await agent.ainvoke({"message":[{"role":"user","content":"你能干嘛"}]}, config=config)
    print("RESULT",res)
    print("#"*50)
    print("AI_MESSAGE",res["messages"][-1].content)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_agent())
