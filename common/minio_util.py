import io
import logging
import mimetypes
import os
import traceback
from datetime import timedelta
from uuid import uuid4

import pymupdf
import pymupdf4llm
from docx import Document
from minio import Minio, S3Error
from sanic import Request

from common.exception import MyException
from constants.code_enum import SysCodeEnum as SysCode

logger = logging.getLogger(__name__)


class MinioUtils:
    """
    上传文件工具类
    """

    def __init__(self):
        self.client = self._build_client()
        # self.executor = ThreadPoolExecutor(max_workers=5)  # 多线程上传控制最大并发数

    @staticmethod
    def _build_client():
        """初始化MinIO客户端"""
        minio_endpoint = os.getenv("MINIO_ENDPOINT")
        access_key = os.getenv("MINIO_ACCESS_KEY")
        secret_key = os.getenv("MiNIO_SECRET_KEY")
        if not all([minio_endpoint, access_key, secret_key]):
            raise MyException(SysCode.c_9999, "MinIO环境变量未正确配置")
        return Minio(endpoint=minio_endpoint, access_key=access_key, secret_key=secret_key, secure=False)

    def ensure_bucket(self, bucket_name: str) -> None:
        """确保bucket存在，不存在则创建"""
        try:
            found = self.client.bucket_exists(bucket_name)
            if not found:
                self.client.make_bucket(bucket_name)
                logger.info(f"Bucket '{bucket_name}' created.")
            else:
                logger.info(f"Bucket '{bucket_name}' already exists.")
        except S3Error as err:
            logger.error(f"Error checking or creating bucket {bucket_name}: {err}")
            raise MyException(SysCode.c_9999)

    def upload_file_from_request(self, request: Request, bucket_name: str = "filedata") -> dict:
        """
        从请求中读取文件数据并上传到MinIO服务器，返回预签名URL。

        参数:
        - request: Sanic请求对象
        - bucket_name: 存储桶名称
        返回:
        - 包含object_key的字典
        """
        try:
            file_data = request.files.get("file")
            if not file_data:
                raise MyException(SysCode.c_9999, "未找到文件数据")

            file_stream = io.BytesIO(file_data.body)
            file_length = len(file_data.body)
            object_name = file_data.name

            self.ensure_bucket(bucket_name)
            self.client.put_object(bucket_name, object_name, file_stream, file_length, content_type=file_data.type)
            logger.info(f"File successfully uploaded as {object_name}.")

            return {"object_key": object_name}
        except Exception as err:
            logger.error(f"Error uploading file from request: {err}")
            traceback.print_exception(err)
            raise MyException(SysCode.c_9999)

    def upload_to_minio_form_stream(
        self, file_stream: io.BytesIO, bucket_name: str = "filedata", file_name: str | None = None
    ) -> str | None:
        """
        将给定的字节流上传到MinIO，并返回上传文件的键（key）。

        :param file_stream: 文件的字节流 (BytesIO)
        :param bucket_name: MinIO存储桶名称
        :param file_name: 上传文件的名称（可选）
        :return: 上传文件的键（key）或None如果上传失败
        """
        try:
            self.ensure_bucket(bucket_name)

            if not file_name:
                file_extension = mimetypes.guess_extension(mimetypes.guess_type(file_stream.getvalue())[0]) or ""
                file_name = f"{uuid4()}{file_extension}"

            file_stream.seek(0)
            file_length = len(file_stream.getvalue())
            content_type, _ = mimetypes.guess_type(file_name) or ("application/octet-stream", None)

            self.client.put_object(bucket_name, file_name, file_stream, file_length, content_type=content_type)
            logger.info(f"File uploaded successfully with key: {file_name}")
            return file_name
        except Exception as e:
            logger.error(f"An error occurred while uploading to MinIO: {e}")
            return None

    def get_file_url_by_key(self, bucket_name: str = "filedata", object_key: str | None = None) -> str:
        """
        通过object_key获取文件url
        """
        try:
            if not object_key:
                raise MyException(SysCode.c_9999, "object_key不能为空")
            return self.client.presigned_get_object(bucket_name, object_key, expires=timedelta(days=7))
        except Exception as err:
            logger.error(f"Error getting file URL by key: {err}")
            traceback.print_exception(err)
            raise MyException(SysCode.c_9999)

    def upload_file_and_parse_from_request(self, request: Request, bucket_name: str = "filedata") -> dict:
        """
        上传文件并解析文件内容，返回文件内容key。

        参数:
        - request: Sanic请求对象
        - bucket_name: 存储桶名称
        返回:
        - 文件内容key
        """

        try:
            file_data = request.files.get("file")
            if not file_data:
                raise MyException(SysCode.c_9999, "未找到文件数据")

            content = io.BytesIO(file_data.body)
            object_name = file_data.name
            mime_type = file_data.type
            file_suffix = ".txt"
            # 可选：添加文件大小限制（例如 50MB）
            if len(file_data.body) > 50 * 1024 * 1024:
                raise MyException(SysCode.c_9999, "文件大小超出限制")

            source_file_key = self.upload_file_from_request(request, bucket_name)

            # 校验 MIME 类型是否支持（增强安全性）
            allowed_mimes = {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
                "application/msword",  # .doc
                "text/plain",  # .txt
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
                "application/vnd.ms-excel",  # .xls
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
                "application/vnd.ms-powerpoint",  # .ppt
                "application/pdf",  # .pdf
            }

            if mime_type not in allowed_mimes:
                raise ValueError("不支持的文件格式")

            # 根据文件类型选择不同的方式读取内容
            if mime_type in (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword",
            ):
                doc = Document(content)
                full_text = "\n".join([para.text for para in doc.paragraphs])
            elif mime_type == "text/plain":
                content.seek(0)
                full_text = content.read().decode("utf-8")

            elif mime_type in (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
            ):
                content.seek(0)
                full_text = self.read_pdf_text_from_bytes(content.getvalue())
            elif mime_type in (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.ms-powerpoint",
            ):
                content.seek(0)
                full_text = self.read_pdf_text_from_bytes(content.getvalue())
            elif mime_type == "application/pdf":
                # todo 如果pdf文件中包含图片，则需要使用OCR处理图片 私有化部署mineru支持
                content.seek(0)
                full_text = self.read_pdf_text_from_bytes(content.getvalue())
            else:
                raise ValueError("不支持的文件格式")

            # 创建一个txt文件并上传
            parse_file_key = self.upload_to_minio_form_stream(
                io.BytesIO(full_text.encode("utf-8")), bucket_name, object_name + file_suffix
            )
            return {"source_file_key": source_file_key["object_key"], "parse_file_key": parse_file_key}

        except Exception as err:
            logger.error(f"Error uploading file and parsing from request: {err}")
            traceback.print_exception(type(err), err, err.__traceback__)
            raise MyException(SysCode.c_9999) from err

    @staticmethod
    def read_pdf_text_from_bytes(file_bytes):
        """
        从字节数据中读取文件返回markdown文本 缺点不支持图片解析 如果开启需要走公网服务
        :param file_bytes: bytes, PDF 文件的二进制内容
        :return: str, 提取的文本内容
        """
        try:
            doc = pymupdf.open(stream=file_bytes)
            md_text = pymupdf4llm.to_markdown(doc=doc, ignore_images=True)
            return md_text
        except Exception as e:
            logger.error(f"读取文本时出错: {e}")
            raise MyException(SysCode.c_9999, "PDF 解析失败") from e
