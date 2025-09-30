import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import List, Any

import jwt
import requests
from sqlalchemy.orm import Session

from common.exception import MyException
from common.mysql_util import MysqlUtil
from constants.code_enum import SysCodeEnum, DiFyAppEnum, DataTypeEnum
from constants.dify_rest_api import DiFyRestApi
from model.db_connection_pool import get_db_pool
from model.db_models import TUserQaRecord, TUser
from model.serializers import model_to_dict

logger = logging.getLogger(__name__)

mysql_client = MysqlUtil()
pool = get_db_pool()


async def authenticate_user(username, password):
    """验证用户凭据并返回用户信息或 None"""
    with pool.get_session() as session:
        session: Session = session
        user_dict = model_to_dict(
            session.query(TUser).filter(TUser.userName == username).filter(TUser.password == password).first()
        )
        if user_dict:
            return user_dict
        return False
    # sql = f"""select * from t_user where userName='{username}' and password='{password}'"""
    # report_dict = MysqlUtil().query_mysql_dict(sql)
    # if len(report_dict) > 0:
    #     return report_dict[0]
    # else:
    #     return False


async def generate_jwt_token(user_id, username):
    """生成 JWT token"""
    payload = {
        "id": str(user_id),
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }  # Token 过期时间
    token = jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")
    return token


async def decode_jwt_token(token):
    """解析 JWT token 并返回 payload"""
    try:
        # 使用与生成 token 时相同的密钥和算法来解码 token
        payload = jwt.decode(token, key=os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        # 检查 token 是否过期
        if "exp" in payload and datetime.utcfromtimestamp(payload["exp"]) < datetime.utcnow():
            raise jwt.ExpiredSignatureError("Token has expired")
        return payload
    except jwt.ExpiredSignatureError as e:
        # 处理过期的 token
        return None, 401, str(e)
    except jwt.InvalidTokenError as e:
        # 处理无效的 token
        return None, 400, str(e)
    except Exception as e:
        # 处理其他可能的错误
        return None, 500, str(e)


async def get_user_info(request) -> dict:
    """获取登录用户信息"""
    token = request.headers.get("Authorization")

    # 检查 Authorization 头是否存在
    if not token:
        logging.error("Authorization header is missing")
        raise MyException(SysCodeEnum.c_401)

    # 检查 Authorization 头格式是否正确
    if not token.startswith("Bearer "):
        logging.error("Invalid Authorization header format")
        raise MyException(SysCodeEnum.c_400)

    # 提取 token
    token = token.split(" ")[1].strip()

    # 检查 token 是否为空
    if not token:
        logging.error("Token is empty or whitespace")
        raise MyException(SysCodeEnum.c_400)

    try:
        # 解码 JWT token
        user_info = await decode_jwt_token(token)
    except Exception as e:
        logging.error(f"Failed to decode JWT token: {e}")
        raise MyException(SysCodeEnum.c_401)

    return user_info


async def add_question_record(
    uuid_str, user_token, conversation_id, message_id, task_id, chat_id, question, t02_answer, t04_answer, qa_type
):
    """
    @:param uuid_str: 唯一ID
    @param user_token: 用户token
    @param conversation_id: dify会话ID
    @param message_id: 消息ID
    @param task_id: 任务ID
    @param chat_id: 聊天ID
    @param question: 问题
    @param t02_answer: 回答
    @param t04_answer: 回答
    @param qa_type: 问答类型
    记录用户问答记录，如果记录已存在，则更新之；否则，创建新记录。
    """
    try:
        # 解析token信息
        user_dict = await decode_jwt_token(user_token)
        user_id = user_dict["id"]

        # 文件问答时保存 minio/key
        file_key = ""
        if qa_type == DiFyAppEnum.FILEDATA_QA.value[0]:
            file_key = question.split("|")[0]
            question = question.split("|")[1]

        sql = f"select * from t_user_qa_record where user_id={user_id} and chat_id='{chat_id}' and message_id='{message_id}'"
        log_dict = mysql_client.query_mysql_dict(sql)

        # 根据 message_id 判断是否是同一个问题
        if len(log_dict) > 0:
            sql = f"""update t_user_qa_record set to4_answer='{json.dumps(t04_answer, ensure_ascii=False)}' 
                    where user_id={user_id} and chat_id='{chat_id}' and message_id='{message_id}'"""
            mysql_client.update(sql)
        else:
            insert_params = [
                uuid_str,
                user_id,
                conversation_id,
                message_id,
                task_id,
                chat_id,
                question,
                json.dumps(t02_answer, ensure_ascii=False),
                qa_type,
                file_key,
            ]
            sql = (
                f" insert into t_user_qa_record(uuid,user_id,conversation_id, message_id, task_id,chat_id,question,to2_answer,qa_type,file_key) "
                f"values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            )
            mysql_client.insert(sql=sql, params=insert_params)

    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"保存用户问答日志失败: {e}")


async def add_user_record(
    uuid_str: str,
    chat_id: int,
    question: str,
    to2_answer: List[str],
    to4_answer: dict[str, Any],
    qa_type: str,
    user_token: str,
    file_list: dict[str, Any] = None,
):
    """
    新增用户问答记录
    """
    try:
        # 1. 解析用户信息
        user_info = await decode_jwt_token(user_token)
        user_id = user_info.get("id")
        if not user_id:
            raise ValueError("Invalid user token: missing user_id")

        # 2. 组装 answer 数据 - 修复部分：确保所有元素转换为字符串
        t02_content = "".join(str(item) for item in (to2_answer or []))
        t02_message_json = {
            "data": {"messageType": "continue", "content": t02_content},
            "dataType": DataTypeEnum.ANSWER.value[0],
        }
        t02_answer_str = json.dumps(t02_message_json, ensure_ascii=False)

        # 3. 插入数据库
        insert_sql = """
            INSERT INTO t_user_qa_record
            (uuid, user_id, chat_id, question, to2_answer,to4_answer, qa_type,file_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        insert_params = [
            uuid_str,
            user_id,
            chat_id,
            question,
            t02_answer_str,
            json.dumps(to4_answer, ensure_ascii=False),
            qa_type,
            json.dumps(file_list, ensure_ascii=False) if file_list and len(file_list) > 0 else "",
        ]

        # 如果 mysql_client.insert 是异步方法
        mysql_client.insert(sql=insert_sql, params=insert_params)

    except Exception as e:
        # 建议替换成项目的日志系统
        logger.error(f"Failed to insert user QA record: {e}", exc_info=True)
        raise


async def delete_user_record(user_id, record_ids):
    """
    删除用户问答记录
    :param user_id: 用户ID
    :param record_ids: 要删除的记录ID列表
    :return: None
    """
    # 确保 record_ids 是一个非空列表
    if not isinstance(record_ids, list) or not record_ids:
        raise ValueError("record_ids 必须是非空列表")

    # 创建 IN 子句和对应的参数列表
    in_clause = ", ".join(["%s"] * len(record_ids))
    sql = f"""
        DELETE FROM t_user_qa_record
        WHERE user_id = %s AND chat_id IN ({in_clause})
    """

    # 将 user_id 添加到参数列表的开头
    params = [user_id] + record_ids

    # 执行更新操作
    mysql_client.update_params(sql=sql, params=params)


async def query_user_record(user_id, page, limit, search_text, chat_id):
    """
    根据用户id查询用户问答记录
    如果chat_id不为空，则查询该chat_id的所有记录；否则根据chat_id去重，取id最小的那条
    :param page
    :param limit
    :param user_id
    :param search_text
    :param chat_id
    :return:
    """
    conditions = []
    if chat_id:
        conditions.append(f"chat_id = '{chat_id}'")
    if search_text:
        search_text = search_text.strip()  # 去除search_text首尾空格
        conditions.append(f"question LIKE '%{search_text}%'")
    elif user_id:
        conditions.append(f"user_id = {user_id}")

    # 计算偏移量
    offset = (page - 1) * limit

    # 如果chat_id不为空，则不需要去重，直接查询
    if chat_id:
        count_sql = "SELECT COUNT(1) as count FROM t_user_qa_record"
        if conditions:
            count_sql += " WHERE " + " AND ".join(conditions)
        total_count_result = mysql_client.query_mysql_dict(count_sql)
        total_count = total_count_result[0]["count"] if total_count_result else 0
        total_pages = (total_count + limit - 1) // limit

        records_sql = f"SELECT * FROM t_user_qa_record"
        if conditions:
            records_sql += " WHERE " + " AND ".join(conditions)
        records_sql += f" ORDER BY id ASC LIMIT {limit} OFFSET {offset}"
        records = mysql_client.query_mysql_dict(records_sql)
    else:
        # 如果chat_id为空，则需要去重，根据chat_id取id最小的记录
        base_condition = ""
        if conditions:
            base_condition = " WHERE " + " AND ".join(conditions)

        count_sql = f"""
            SELECT COUNT(1) as count FROM (
                SELECT chat_id, MIN(id) as min_id 
                FROM t_user_qa_record 
                {base_condition}
                GROUP BY chat_id
            ) as distinct_chats
        """
        total_count_result = mysql_client.query_mysql_dict(count_sql)
        total_count = total_count_result[0]["count"] if total_count_result else 0
        total_pages = (total_count + limit - 1) // limit

        # 查询去重后的记录，根据chat_id分组并取id最小的记录
        records_sql = f"""
            SELECT t.* FROM t_user_qa_record t
            INNER JOIN (
                SELECT chat_id, MIN(id) as min_id 
                FROM t_user_qa_record 
                {base_condition}
                GROUP BY chat_id
            ) tm ON t.chat_id = tm.chat_id AND t.id = tm.min_id
            ORDER BY t.id DESC 
            LIMIT {limit} OFFSET {offset}
        """
        records = mysql_client.query_mysql_dict(records_sql)

    return {"records": records, "current_page": page, "total_pages": total_pages, "total_count": total_count}


def query_user_qa_record(chat_id):
    """
    根据chat_id查询对话记录
    :param chat_id:
    :return:
    """
    with pool.get_session() as session:
        session: Session = session
        records = (
            session.query(TUserQaRecord)
            .filter(TUserQaRecord.chat_id == chat_id)
            .order_by(TUserQaRecord.id.desc())
            .all()
        )
        return model_to_dict(records)
    # sql = f"select * from t_user_qa_record where chat_id='{chat_id}' order by id desc limit 1"
    # return mysql_client.query_mysql_dict(sql)


async def send_dify_feedback(chat_id, rating):
    """
    发送反馈给指定的消息ID。

    :param chat_id: 消息的唯一标识符。
    :param rating: 反馈评级（例如："like" 或 "dislike"）。
    :return: 返回服务器响应。
    """
    # 查询对话记录
    qa_record = query_user_qa_record(chat_id)
    url = DiFyRestApi.replace_path_params(DiFyRestApi.DIFY_REST_FEEDBACK, {"message_id": qa_record[0]["message_id"]})
    api_key = os.getenv("DIFY_DATABASE_QA_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"rating": rating, "user": "abc-123"}

    response = requests.post(url, headers=headers, json=payload)

    # 检查请求是否成功
    if response.status_code == 200:
        logger.info("Feedback successfully sent.")
    else:
        logger.error(f"Failed to send feedback. Status code: {response.status_code},Response body: {response.text}")
        raise
