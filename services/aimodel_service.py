import json
import logging
import httpx
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc

from common.exception import MyException
from constants.code_enum import SysCodeEnum
from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel
from model.serializers import model_to_dict

logger = logging.getLogger(__name__)
pool = get_db_pool()

async def query_model_list(keyword: str = None, model_type: int = None) -> List[dict]:
    with pool.get_session() as session:
        query = session.query(TAiModel)
        if keyword:
            query = query.filter(TAiModel.name.like(f"%{keyword}%"))
        
        if model_type:
            query = query.filter(TAiModel.model_type == model_type)
        
        # Order by default_model desc, then name
        models = query.order_by(desc(TAiModel.default_model), TAiModel.name).all()
        
        result = []
        for model in models:
            m_dict = model_to_dict(model)
            result.append(m_dict)
        return result

async def get_model_detail(model_id: int) -> dict:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
        
        data = model_to_dict(model)
        if data.get('config'):
            try:
                data['config_list'] = json.loads(data['config'])
            except:
                data['config_list'] = []
        else:
            data['config_list'] = []
        return data

async def add_model(data: dict) -> bool:
    with pool.get_session() as session:
        # Check if default
        model_type = data.get('model_type', 1)
        
        # Only LLM (type 1) can be default
        is_default = False
        if model_type == 1:
            count = session.query(TAiModel).filter(TAiModel.model_type == 1).count()
            is_default = (count == 0) # First LLM is default

        config_list = data.get('config_list', [])
        config_str = json.dumps(config_list)

        new_model = TAiModel(
            name=data['name'],
            base_model=data['base_model'],
            model_type=data.get('model_type', 1), # Default to 1 (LLM)
            supplier=data.get('supplier', 1),
            protocol=data.get('protocol', 1),
            api_domain=data['api_domain'],
            api_key=data['api_key'],
            config=config_str,
            default_model=is_default,
            status=1,
            create_time=int(datetime.now().timestamp())
        )
        session.add(new_model)
        session.commit()
        return True

async def update_model(model_id: int, data: dict) -> bool:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
        
        model.name = data.get('name', model.name)
        model.base_model = data.get('base_model', model.base_model)
        model.protocol = data.get('protocol', model.protocol)
        model.api_domain = data.get('api_domain', model.api_domain)
        model.api_key = data.get('api_key', model.api_key)
        
        if 'config_list' in data:
            model.config = json.dumps(data['config_list'])
            
        session.commit()
        return True

async def delete_model(model_id: int) -> bool:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
             raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
        
        if model.default_model:
             raise MyException(SysCodeEnum.PARAM_ERROR, "Cannot delete default model")
             
        session.delete(model)
        session.commit()
        return True

async def set_default_model(model_id: int) -> bool:
    with pool.get_session() as session:
        model = session.query(TAiModel).filter(TAiModel.id == model_id).first()
        if not model:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Model not found")
            
        if model.model_type != 1:
            raise MyException(SysCodeEnum.PARAM_ERROR, "Only LLM can be set as default")

        if model.default_model:
            return True
            
        # Unset previous default for LLM
        session.query(TAiModel).filter(
            TAiModel.default_model == True,
            TAiModel.model_type == 1
        ).update({TAiModel.default_model: False})
        
        model.default_model = True
        session.commit()
        return True

async def check_llm_status(data: dict) -> bool:
    # Mock implementation
    return True

async def fetch_base_models(supplier: int, api_key: str = None, api_domain: str = None) -> List[str]:
    try:
        # OpenAI
        if supplier == 1:
            if not api_key:
                return []
            domain = api_domain or "https://api.openai.com/v1"
            url = f"{domain}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                models = [m['id'] for m in data.get('data', []) if 'gpt' in m['id']]
                return sorted(models)
        
        # Ollama
        elif supplier == 3:
            domain = api_domain or "http://localhost:11434"
            # Ollama API structure: GET /api/tags
            if domain.endswith('/v1'):
                 domain = domain[:-3] # Strip /v1 if present
            
            url = f"{domain}/api/tags"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                models = [m['name'] for m in data.get('models', [])]
                return sorted(models)
        
        # vLLM
        elif supplier == 4:
             if not api_domain:
                 return []
             url = f"{api_domain}/models"
             headers = {}
             if api_key:
                 headers["Authorization"] = f"Bearer {api_key}"
             async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                models = [m['id'] for m in data.get('data', [])]
                return sorted(models)
        
        # DeepSeek
        elif supplier == 5:
             # Similar to OpenAI
             if not api_key:
                 return []
             domain = api_domain or "https://api.deepseek.com"
             url = f"{domain}/models"
             headers = {"Authorization": f"Bearer {api_key}"}
             async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                models = [m['id'] for m in data.get('data', [])]
                return sorted(models)
        
        # Fallback or other providers: Return empty list or hardcoded common ones?
        # For now return empty, frontend can allow manual entry
        return []

    except Exception as e:
        logger.error(f"Failed to fetch models for supplier {supplier}: {e}")
        # Return empty list on error
        return []
