"""
    同步数据至Milvus数据库中
"""
import os
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from pathlib import Path
from pymilvus import DataType
load_dotenv()
root_path = Path(__file__).parent.parent

def insert_data():

    # 1.连接到MySQL数据库,获取到menu_items当中的所有数据
    import pymysql
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
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            # 定义json的键，将数据封装成json
            str_results = []
            for item in results:
                new_result = ""
                for key, value in item.items():
                    new_result += f"{key_name_mapping[key]}: {value}\n"
                str_results.append(new_result)

    # 2.连接到Milvus数据库，获取到client对象
    from pymilvus import MilvusClient
    client = MilvusClient(url=os.getenv("MILVUS_URL"),token=os.getenv("MILVUS_TOKEN"))

    # 3.创建collection
    # 3.1创建schema
    schema = MilvusClient.create_schema(
        auto_id=True,
    ).add_field(field_name="id", datatype=DataType.INT64, is_primary=True
    ).add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024
    ).add_field(field_name="text", datatype=DataType.VARCHAR, max_length=1500)

    # 3.2创建索引
    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="HNSW",
        metric_type="L2",
    )

    # 3.3创建collection
    res = client.create_collection(
        collection_name="menu_items",
        schema=schema,
        index_params=index_params
    )

    # 4.使用embedding模型对menu_items数据进行向量化
    from langchain_huggingface import HuggingFaceEmbeddings
    embeddings = HuggingFaceEmbeddings(model=str(root_path / "models" / "bge-m3"))

    vector_list = embeddings.embed_documents(str_results)

    # 5.将向量化后的数据插入到Milvus数据库中
    insert_data = []
    for vector, text in zip(vector_list, str_results):
        insert_data.append({
            "vector": vector,
            "text": text
        })

    insert_res = client.insert(data=insert_data, collection_name="menu_items")
    print(f"插入Milvus数据库的结果: {insert_res}")

insert_data()