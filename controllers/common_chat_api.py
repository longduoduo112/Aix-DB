"""
通用问答
"""
import logging
import os
import traceback

from sanic import Blueprint, request

from common.exception import MyException
from common.res_decorator import async_json_resp
from constants.code_enum import SysCodeEnum
from services.selenium_service import get_bing_first_href, get_first_search_result_link

bp = Blueprint("common-chat", url_prefix="/common"***REMOVED***


@bp.post("/get_search_url"***REMOVED***
@async_json_resp
async def get_bing_search_url(req: request.Request***REMOVED***:
    """
    通用问答 获取搜索引擎第一个结果url
    """
    try:
        query_str = req.args.get("query_str"***REMOVED***
        if os.getenv("ENV"***REMOVED*** == "test":
            result = await get_bing_first_href(query_str***REMOVED***
        else:
            # 本地调试使用chromedriver
            result = await get_first_search_result_link(query_str***REMOVED***

        return result
    except Exception as e:
        traceback.print_exception(e***REMOVED***
        logging.error(f"Error processing LLM output: {e***REMOVED***"***REMOVED***
        raise MyException(SysCodeEnum.c_9999***REMOVED***
