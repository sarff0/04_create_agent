"""
将FAQ数据导入到redis中,方便后续agent进行查询和使用
"""

FAQ_ITEMS = [
    {
        "id":"address",
        "question": "餐厅的地址是什么？",
        "answer": "餐厅的地址是北京市朝阳区建国路88号SOHO现代城B座5层"
    },
    {
        "id":"phone",
        "question": "餐厅的电话是什么？",       
        "answer": "餐厅的电话是010-88888888"
    },
    {
        "id":"time",
        "question": "餐厅的营业时间是什么？",
        "answer": "餐厅的营业时间是每天10:00-22:00"
    },
    {
        "id":"menu",
        "question": "餐厅的菜单有哪些？",
        "answer": "餐厅的菜单有：宫保鸡丁、鱼香肉丝、麻婆豆腐、西红柿炒鸡蛋等"
    }
]

def sync_faq_items_to_redis():
    """
    将FAQ_ITEMS中的数据同步到redis中
    """

    # 1.获取到client和pipeline对象
    from redis import Redis
    client = Redis(host="localhost", port=6379, db=0,decode_responses=True)  
    pipeline = client.pipeline()
  
    # 2.使用pipeline，将所有数据，批量写入到redis的 hash map中,以及将所有的faq item对应的key，写入到一个set集合中

        # 全量对比：当用户Query来了之后，需要把所有的faq questions都从redis里面读取出来，
        # 然后和用户的query去做一个相似度计算，取出相似度最高的top_k个问题

        # 后面如何从redis中得知，我们有哪些key？
            # 方式一：redis给我们提供一个命令：keys pattern(类似正则匹配的一个表达式)，可以通过这个命令获取到redis中有哪些faq的键
                # 缺点：当redis中存储的数据量非常大的时候，执行这个命令会非常慢，甚至会阻塞redis
                    # faq:items:address  faq:items:phone  ...
                        # all_faq_keys = client.keys("faq:items")  # 获取到redis中所有的faq的key，返回一个列表
                        # for faq_item in all_faq_keys:
                        #     pipeline.hgetall(faq_item)  # 获取到每一个faq key对应的hash map中的数据，返回一个字典
                        # all_faq_items = pipeline.execute()  # 执行pipeline中声明的所有命令，返回一个列表，列表中的每一个元素就是每一个faq key对应的hash map中的数据（字典）
            # 方式二：单独创建一个set,来存储所有的faq和key
                # 每次新增一个faq item的时候，就把这个faq item对应的key添加到这个set中，
                # 这样当我们需要获取到所有的faq item对应的key的时候，就可以直接获取到这个set中的所有元素，就可以知道redis中有哪些faq item了

    for faq_item in FAQ_ITEMS:
        
        # 1.将数据写入到hash map中
        key = f"faq:items:{faq_item['id']}"
        pipeline.hset(
            name=key,
            mapping={
                "question": faq_item["question"],
                "answer": faq_item["answer"]
            }
        )

        # 2.将它的key添加到faq:items所对应的set集合中
        pipeline.sadd("faq:all_items", key)

    # 3.执行pipeline中声明的所有命令
    result = pipeline.execute()

    all_faq_keys = client.smembers("faq:all_items")  # 获取到faq:items所对应的set集合中的所有元素，也就是所有的faq item对应的key
    print(all_faq_keys)

if __name__ == "__main__":
    sync_faq_items_to_redis()