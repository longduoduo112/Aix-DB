import logging
from sanic import Blueprint, request
from sanic_ext import openapi

from services.permission_service import PermissionService
from model.db_connection_pool import get_db_pool
from common.res_decorator import async_json_resp
from common.exception import MyException
from constants.code_enum import SysCodeEnum
from common.param_parser import parse_params
from model.schemas import (
    get_schema,
    PermissionListResponse,
    SavePermissionRequest,
    SavePermissionResponse,
    DeletePermissionResponse,
)

logger = logging.getLogger(__name__)

bp = Blueprint("ds_permission", url_prefix="/ds_permission")


@bp.post("/list")
@openapi.summary("获取权限规则列表")
@openapi.description("获取所有权限规则")
@openapi.tag("权限管理")
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(PermissionListResponse),
        }
    },
    description="获取成功",
)
@async_json_resp
async def get_permission_list(req: request.Request):
    """获取权限规则列表"""
    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            result = PermissionService.get_list(session)
            return result
    except Exception as e:
        logger.error(f"获取权限列表失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"获取权限列表失败: {str(e)}")


@bp.post("/save")
@openapi.summary("保存权限规则")
@openapi.description("创建或更新权限规则")
@openapi.tag("权限管理")
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(SavePermissionRequest),
        }
    },
    description="规则信息",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(SavePermissionResponse),
        }
    },
    description="保存成功",
)
@async_json_resp
@parse_params
async def save_permission(req: request.Request, body: SavePermissionRequest):
    """保存权限规则"""
    try:
        data = body.model_dump()

        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            success = PermissionService.save_permission(session, data)
            if not success:
                raise MyException(SysCodeEnum.SYSTEM_ERROR, "保存失败")
            return {"message": "保存成功"}
    except MyException:
        raise
    except Exception as e:
        logger.error(f"保存权限规则失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"保存权限规则失败: {str(e)}")


@bp.post("/delete/<rule_id:int>")
@openapi.summary("删除权限规则")
@openapi.description("删除指定的权限规则")
@openapi.tag("权限管理")
@openapi.parameter(
    name="rule_id",
    location="path",
    schema={"type": "integer"},
    description="规则ID",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(DeletePermissionResponse),
        }
    },
    description="删除成功",
)
@async_json_resp
async def delete_permission(req: request.Request, rule_id: int):
    """删除权限规则"""
    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            success = PermissionService.delete_permission(session, rule_id)
            if not success:
                raise MyException(SysCodeEnum.DATA_NOT_FOUND, "规则不存在")
            return {"message": "删除成功"}
    except MyException:
        raise
    except Exception as e:
        logger.error(f"删除权限规则失败: {e}", exc_info=True)
        raise MyException(SysCodeEnum.SYSTEM_ERROR, f"删除权限规则失败: {str(e)}")
