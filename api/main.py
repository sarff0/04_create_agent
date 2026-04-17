"""
定义后端的所有的接口
"""
# 1.导入FastAPI
from fastapi import FastAPI
from pydantic import BaseModel

from agent.langchain_assitant import assisrant_query,mysql_connection
# 引入StreamingResponse,用于发送事件流：EventStream
from starlette.responses import StreamingResponse
from difflib import SequenceMatcher
from sqlalchemy import text
from typing import List,Optional
import os
from dotenv import load_dotenv
load_dotenv()
client = None


# 2.创建一个application 简称app
app = FastAPI()

# 3.配置app的路由映射函数：每一个端点所对应的处理函数

class ChatRequest(BaseModel):
    query:str

class FaqItem(BaseModel):
    question:str
    answer:str

class FAQResponse(BaseModel):
    success:bool
    query:str
    # 针对于用户的一个query，需要给前端多个faq
    suggestions:list[FaqItem]

class ReservationItem(BaseModel):
    id: int
    num_people: int
    num_children: int
    arrival_time: Optional[str] = None
    seat_preference: Optional[str] = None
    main_dish_preference: Optional[str] = None
    other_comments: Optional[str] = None
    created_at: Optional[str] = None

class ReservationListResponse(BaseModel):
    success: bool
    reservations: List[ReservationItem]
    count: int
    message: str

class MenuItem(BaseModel):
    id: int
    dish_name: str
    price: float
    formatted_price: str
    description: Optional[str] = None
    category: Optional[str] = None
    spice_level: Optional[int] = None
    spice_text: Optional[str] = None
    is_vegetarian: Optional[bool] = None

class MenuListResponse(BaseModel):
    success: bool
    menu_items: List[MenuItem]
    count: int
    message: str

def get_redis_client():
    global client
    if client is None:
        from redis.asyncio import Redis
        client = Redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
    return client

async def get_faq_items_from_redis() -> list[FaqItem]:
    # 1.获取到redis的client对象
    client = get_redis_client()
    pipeline = client.pipeline()

    # 2.从redis set 中获取到faq所对应的所有keys
    faq_keys = await client.smembers("faq:all_items") 

    # 3.加载faq_keys所对应的所有faq,每个faq构造成FaqItem对象
    for faq_key in faq_keys:
        pipeline.hgetall(faq_key)

    all_faq_items = await pipeline.execute()

    return [
        FaqItem(
                question=faq_item["question"],
                answer=faq_item["answer"]
            ) for faq_item in all_faq_items
    ]

def get_similarity_score(query:str, faq_question:str) -> float:
    """
    使用简单的字符串匹配算法,计算query和faq_question的相似度得分
    """
    # 算法一：使用difflib.SequenceMatcher
    # 底层原理：递归的比较两个字符串的最长公共子序列
    matcher = SequenceMatcher(None, query, faq_question)
    score = matcher.ratio()

    # 算法二：只计算query包含的关键词/字和question包含的关键词/字，构成一个词袋，计算相似度
        # jaccard相似度用来计算两个集合之间的相似度
    a = set(list(query))
    b = set(list(faq_question))
    jaccard_score = len(a.intersection(b)) / len(a.union(b))

    return 0.6*score + 0.4*jaccard_score

# 3.1 配置/chat接口
@app.post("/chat")
async def chat_endpoint(request:ChatRequest):
    """
    处理/chat接口的请求
    request: ChatRequest对象,包含了用户的查询
    """
    query = request.query

    # return {"response": assisrant_query(query)"}
    return StreamingResponse(
        assisrant_query(query),             # 传入一个异步生成器，用于逐步发送响应
        media_type="text/event-stream"      # HTTP规范里面定义的事件流的媒体类型
    )

@app.get("/faq/suggest", response_model=FAQResponse)
async def faq_endpoint(query:str,limit:int=1):
    """
    处理/faq接口的请求
    request: ChatRequest对象,包含了用户的查询
    """
    limit = 1
    # 1.从redis中获取到所有的faq 的数据
    faq_items = await get_faq_items_from_redis()

    # 2.将这些数据中的question和用户的query做一个相似度计算，得到相似度得分
    scores_list = []
    for faq_item in faq_items:
        score = get_similarity_score(query, faq_item.question)
        scores_list.append((score, faq_item))

    # 3.将这些得分进行排序，得到最相似的前一条数据
    scores_list.sort(key=lambda x:x[0], reverse=True)
    top_k_items = scores_list[:limit]

    # 4.将这个结果返回给前端
    return FAQResponse(
        success=True,
        query=query,
        suggestions=[faq_item for score, faq_item in top_k_items]
    )

@app.get("/reservation/list", response_model=ReservationListResponse)
async def reservation_list_endpoint():
    """
    获取到预定列表
    """
    # 获取到sqlalchemy.engine.Connection,这个对象和pymysql.Connection有点区别
    with mysql_connection().connect() as conn:
        sql = """
        select id, num_people, num_children, arrival_time, seat_preference, main_dish_preference, other_comments, created_at 
        from 
            menu.reservation_order
        """
        # 直接通过conn.execute().fetchall()     获取到的是一个列表，列表的每个元素是一个元组
        # 通过conn.execute().mappings().fetchall()  获取到的是一个列表，列表的每个元素是一个字典，字典的key就是sql语句中select后面指定的字段名
        result = conn.execute(text(sql)).mappings().fetchall()

        # 把result中的每一个元素都构造成一个ReservationItem对象
        item_list = []
        for result_item in result:
            item = ReservationItem(
                id=result_item["id"],
                num_people=result_item["num_people"],
                num_children=result_item["num_children"],
                arrival_time=str(result_item["arrival_time"]),
                seat_preference=result_item["seat_preference"],
                main_dish_preference=result_item["main_dish_preference"],
                other_comments=result_item["other_comments"],
                created_at=str(result_item["created_at"])
            )
            item_list.append(item)
    return ReservationListResponse(
        success=True,
        reservations=item_list,
        count=len(item_list),
        message="获取预定列表成功"
    )

@app.get("/menu/list", response_model=MenuListResponse)
async def menu_list_endpoint():
    """
    获取菜单列表
    """
    spice_text_map = {
        0: "不辣",
        1: "微辣",
        2: "中辣",
        3: "重辣",
    }

    # 获取到sqlalchemy.engine.Connection,这个对象和pymysql.Connection有点区别
    with mysql_connection().connect() as conn:
        sql = """
        select
            id,
            dish_name,
            description,
            price,
            category,
            spice_level,
            is_vegetarian
        from 
            menu.menu_items
        where
            is_available = 1
        order by
            id
        """
        result = conn.execute(text(sql)).mappings().fetchall()

        # 把result中的每一个元素都构造成一个MenuItem对象
        item_list = []
        for result_item in result:
            price = float(result_item["price"])
            spice_level = int(result_item["spice_level"] or 0)
            item = MenuItem(
                id=result_item["id"],
                dish_name=result_item["dish_name"],
                description=result_item["description"],
                price=price,
                formatted_price=f"¥{price:.2f}",
                category=result_item["category"],
                spice_level=spice_level,
                spice_text=spice_text_map.get(spice_level, "未知"),
                is_vegetarian=bool(result_item["is_vegetarian"])
            )
            item_list.append(item)
    return MenuListResponse(
        success=True,
        menu_items=item_list,
        count=len(item_list),
        message="获取菜单列表成功"
    )
