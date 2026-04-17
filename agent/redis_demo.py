def redis_command_demo1():
    """
    redis相关的命令demo演示
    """
    from redis import Redis

    # 1.获取到client对象
    client = Redis(host="localhost", port=6379, db=0,decode_responses=True)  # decode_responses=True表示将redis中存储的bytes类型自动解码成字符串类型

    # 2.使用client对象，去执行redis一些命令
    # 2.1 字符串相关命令： 执行set命令，创建一个value类型为tring的key-value对
    client.set("name", "张三")

    # 执行get命令，获取到key对应的value
    name = client.get("name")
    print(name)  # redis中存储的都是bytes类型

    # 2.2 hash map相关命令: 创建一个value为hash map的key-value对
    client.hset(
        "faq:items:address",
        mapping={
            "question": "餐厅的地址是什么？",
            "answer": "餐厅的地址是北京市朝阳区建国路88号SOHO现代城B座5层"
        }
    )
     # 获取到某一个key对应的hash map
    faq_item = client.hgetall("faq:items:address")
    print(faq_item)

    # 2.3 set相关的命令：创建一个value为set的key-value对
    # 添加一个 key="faq:items3"，value为一个set集合，集合中包含三个元素：address、phone、menu
    client.sadd(
        "faq:items3", 
        "address","phone","menu"
    )
    # result就是key="faq:items3"对应的set集合中的所有元素
    result = client.smembers("faq:items3")
    print(result)

def redis_command_demo2():
    """
    redis的pipeline命令的demo演示
    """
    from redis import Redis

    # 1.获取到client对象
    client = Redis(host="localhost", port=6379, db=0,decode_responses=True)  # decode_responses=True表示将redis中存储的bytes类型自动解码成字符串类型

    # 2.通过client。获取到pipeline对象
    pipeline = client.pipeline()

    # 3.使用pipeline声明，需要执行的命令
    pipeline.set("name1", "李四")
    pipeline.get("name1")
    pipeline.hset(
        "faq:items:phone:test",
        mapping={
            "question": "餐厅的电话是什么？",
            "answer": "餐厅的电话是010-88888888"
        }
    )

    # 4.执行pipeline中声明的命令
    results = pipeline.execute()
    print(results)  # pipeline中声明的命令会被一次性发送到redis服务器端执行，最后会返回一个列表，列表中的每个元素对应着pipeline中声明的每个命令的执行结果

if __name__ == "__main__":
    # redis_command_demo1()
    redis_command_demo2()