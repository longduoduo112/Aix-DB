"""
提示词构建器
根据模板系统构建各种提示词（SQL生成、图表配置、权限过滤等）
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from agent.text2sql.template.template_loader import TemplateLoader

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    提示词构建器，集成所有模板模块
    """
    
    def __init__(self):
        self.template_loader = TemplateLoader()
        self.base_template = None
        self._init_base_template()
    
    def _init_base_template(self):
        """初始化基础模板"""
        try:
            self.base_template = self.template_loader.load_base_template()
        except Exception as e:
            logger.error(f"Failed to load base template: {e}")
            raise
    
    def build_sql_prompt(
        self,
        db_type: str,
        schema: str,
        question: str,
        engine: str,
        lang: str = "简体中文",
        terminologies: str = "",
        data_training: str = "",
        custom_prompt: str = "",
        enable_query_limit: bool = True,
        error_msg: str = "",
        current_time: Optional[str] = None,
        change_title: bool = False,
    ) -> Tuple[str, str]:
        """
        构建 SQL 生成提示词（系统提示词 + 用户提示词）
        
        Args:
            db_type: 数据库类型（如 'postgresql', 'mysql' 等）
            schema: 数据库表结构（M-Schema 格式）
            question: 用户问题
            engine: 数据库引擎及版本信息
            lang: 语言（默认：简体中文）
            terminologies: 术语上下文（格式化后的字符串）
            data_training: 训练示例上下文（格式化后的字符串）
            custom_prompt: 自定义提示词
            enable_query_limit: 是否启用查询限制
            error_msg: 错误消息（上次执行失败的错误信息）
            current_time: 当前时间（格式：YYYY-MM-DD HH:MM:SS）
            change_title: 是否需要生成对话标题
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            # 加载数据库特定的 SQL 模板
            sql_template_dict = self.template_loader.load_sql_template(db_type)
            # SQL 模板文件结构为 template: {quot_rule: ..., limit_rule: ...}
            sql_template = sql_template_dict.get('template', sql_template_dict)
            sql_base_template = self.base_template['template']['sql']
            
            # 获取 process_check
            process_check = sql_template.get('process_check') if sql_template.get('process_check') else sql_base_template['process_check']
            
            # 获取 query_limit 规则
            query_limit = sql_base_template['query_limit'] if enable_query_limit else sql_base_template['no_query_limit']
            
            # 组合基础 SQL 规则
            base_sql_rules = (
                sql_template['quot_rule'] + 
                query_limit + 
                sql_template['limit_rule'] + 
                sql_template['other_rule']
            )
            
            # 获取示例
            sql_examples = sql_template['basic_example']
            example_engine = sql_template['example_engine']
            example_answer_1 = sql_template['example_answer_1_with_limit'] if enable_query_limit else sql_template['example_answer_1']
            example_answer_2 = sql_template['example_answer_2_with_limit'] if enable_query_limit else sql_template['example_answer_2']
            example_answer_3 = sql_template['example_answer_3_with_limit'] if enable_query_limit else sql_template['example_answer_3']
            
            # 构建系统提示词
            system_prompt = sql_base_template['system'].format(
                engine=engine,
                schema=schema,
                question=question,
                lang=lang,
                terminologies=terminologies,
                data_training=data_training,
                custom_prompt=custom_prompt,
                process_check=process_check,
                base_sql_rules=base_sql_rules,
                basic_sql_examples=sql_examples,
                example_engine=example_engine,
                example_answer_1=example_answer_1,
                example_answer_2=example_answer_2,
                example_answer_3=example_answer_3,
            )
            
            # 构建用户提示词
            if current_time is None:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            user_prompt = sql_base_template['user'].format(
                engine=engine,
                schema=schema,
                question=question,
                rule="",  # rule 字段在当前项目中没有使用
                current_time=current_time,
                error_msg=error_msg,
                change_title=change_title,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build SQL prompt: {e}", exc_info=True)
            raise
    
    def build_chart_prompt(
        self,
        sql: str,
        question: str,
        lang: str = "简体中文",
        chart_type: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        构建图表配置生成提示词
        
        Args:
            sql: SQL 语句
            question: 用户问题
            lang: 语言（默认：简体中文）
            chart_type: 推荐的图表类型（可选）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            chart_template = self.base_template['template']['chart']
            
            # 构建系统提示词
            system_prompt = chart_template['system'].format(
                lang=lang,
            )
            
            # 构建用户提示词
            user_prompt = chart_template['user'].format(
                question=question,
                sql=sql,
                chart_type=chart_type or "",
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build chart prompt: {e}", exc_info=True)
            raise
    
    def build_datasource_prompt(
        self,
        question: str,
        datasource_list: List[Dict[str, Any]],
        lang: str = "简体中文",
    ) -> Tuple[str, str]:
        """
        构建数据源选择提示词
        
        Args:
            question: 用户问题
            datasource_list: 数据源列表 [{"id": 1, "name": "...", "description": "..."}, ...]
            lang: 语言（默认：简体中文）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            import json
            datasource_template = self.base_template['template']['datasource']
            
            # 将数据源列表转换为 JSON 字符串
            datasource_json = json.dumps(datasource_list, ensure_ascii=False)
            
            # 构建系统提示词
            system_prompt = datasource_template['system'].format(lang=lang)
            
            # 构建用户提示词
            user_prompt = datasource_template['user'].format(
                question=question,
                data=datasource_json,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build datasource prompt: {e}", exc_info=True)
            raise
    
    def build_permission_prompt(
        self,
        sql: str,
        filters: List[Dict[str, str]],
        engine: str,
        lang: str = "简体中文",
    ) -> Tuple[str, str]:
        """
        构建权限过滤提示词
        
        Args:
            sql: 原始 SQL 语句
            filters: 权限过滤条件列表 [{"table": "表名", "filter": "过滤条件"}, ...]
            engine: 数据库引擎类型
            lang: 语言（默认：简体中文）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            import json
            permissions_template = self.base_template['template']['permissions']
            
            # 将过滤条件列表转换为 JSON 字符串
            filters_json = json.dumps(filters, ensure_ascii=False)
            
            # 构建系统提示词
            system_prompt = permissions_template['system'].format(
                lang=lang,
                engine=engine,
            )
            
            # 构建用户提示词
            user_prompt = permissions_template['user'].format(
                sql=sql,
                filter=filters_json,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build permission prompt: {e}", exc_info=True)
            raise
    
    def build_guess_question_prompt(
        self,
        schema: str,
        question: str = "",
        old_questions: List[str] = None,
        lang: str = "简体中文",
        articles_number: int = 4,
    ) -> Tuple[str, str]:
        """
        构建推荐问题生成提示词
        
        Args:
            schema: 数据库表结构
            question: 当前问题（可选）
            old_questions: 历史问题列表
            lang: 语言（默认：简体中文）
            articles_number: 推荐问题数量（默认：4）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            import json
            guess_template = self.base_template['template']['guess']
            
            # 将历史问题列表转换为 JSON 字符串
            old_questions_json = json.dumps(old_questions or [], ensure_ascii=False)
            
            # 构建系统提示词
            system_prompt = guess_template['system'].format(
                lang=lang,
                articles_number=articles_number,
            )
            
            # 构建用户提示词
            user_prompt = guess_template['user'].format(
                question=question,
                schema=schema,
                old_questions=old_questions_json,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build guess question prompt: {e}", exc_info=True)
            raise
    
    def build_dynamic_sql_prompt(
        self,
        sql: str,
        sub_query: List[Dict[str, str]],
        engine: str,
        lang: str = "简体中文",
    ) -> Tuple[str, str]:
        """
        构建动态 SQL 生成提示词（用于动态数据源场景）
        
        Args:
            sql: 原始 SQL 语句
            sub_query: 子查询映射表 [{"table": "表名", "query": "子查询语句"}, ...]
            engine: 数据库引擎类型
            lang: 语言（默认：简体中文）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            import json
            dynamic_template = self.base_template['template']['dynamic_sql']
            
            # 将子查询映射表转换为 JSON 字符串
            sub_query_json = json.dumps(sub_query, ensure_ascii=False)
            
            # 构建系统提示词
            system_prompt = dynamic_template['system'].format(
                lang=lang,
                engine=engine,
            )
            
            # 构建用户提示词
            user_prompt = dynamic_template['user'].format(
                sql=sql,
                sub_query=sub_query_json,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build dynamic SQL prompt: {e}", exc_info=True)
            raise
    
    def build_summarizer_prompt(
        self,
        data_result: str,
        user_query: str,
        current_time: Optional[str] = None,
    ) -> str:
        """
        构建数据总结提示词
        
        Args:
            data_result: 数据结果（JSON格式字符串）
            user_query: 用户问题
            current_time: 当前时间（格式：YYYY-MM-DD HH:MM:SS），如果为None则自动生成
        
        Returns:
            完整的提示词字符串
        """
        try:
            if current_time is None:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            summarizer_template = self.base_template['template']['summarizer']
            
            # 构建系统提示词
            system_prompt = summarizer_template['system']
            
            # 构建用户提示词
            user_prompt = summarizer_template['user'].format(
                data_result=data_result,
                user_query=user_query,
                current_time=current_time,
            )
            
            # 返回完整的提示词（系统提示词 + 用户提示词）
            return f"{system_prompt}\n\n{user_prompt}"
            
        except Exception as e:
            logger.error(f"Failed to build summarizer prompt: {e}", exc_info=True)
            raise

