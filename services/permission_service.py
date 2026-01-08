
import json
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from model.db_models import TDsRules, TDsPermission
from model.schemas import SavePermissionRequest

logger = logging.getLogger(__name__)


class PermissionService:
    @staticmethod
    def get_list(session: Session) -> List[Dict[str, Any]]:
        stmt = select(TDsRules).where(TDsRules.enable == True).order_by(TDsRules.create_time.desc())
        rules = session.execute(stmt).scalars().all()
        
        result = []
        for rule in rules:
            # Parse permission list IDs
            perm_ids = []
            if rule.permission_list:
                try:
                    perm_ids = json.loads(rule.permission_list)
                except:
                    pass
            
            # Parse user list IDs
            user_ids = []
            if rule.user_list:
                try:
                    user_ids = json.loads(rule.user_list)
                except:
                    pass
            
            # Get permissions details
            permissions = []
            if perm_ids:
                perm_stmt = select(TDsPermission).where(TDsPermission.id.in_(perm_ids))
                perms = session.execute(perm_stmt).scalars().all()
                for p in perms:
                    # Parse internal JSON fields
                    expr_tree = {}
                    if p.expression_tree:
                        try:
                            expr_tree = json.loads(p.expression_tree)
                        except:
                            pass
                    
                    perm_config = []
                    if p.permissions:
                        try:
                            perm_config = json.loads(p.permissions)
                        except:
                            pass
                            
                    permissions.append({
                        "id": p.id,
                        "name": p.name,
                        "type": p.type,
                        "ds_id": p.ds_id,
                        "table_id": p.table_id,
                        "expression_tree": expr_tree,
                        "permissions": perm_config,
                        "enable": p.enable
                    })
            
            result.append({
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "permissions": permissions,
                "users": user_ids,
                "create_time": rule.create_time.isoformat() if rule.create_time else None
            })
            
        return result

    @staticmethod
    def save_permission(session: Session, data: Dict[str, Any]) -> bool:
        rule_id = data.get("id")
        name = data.get("name")
        permissions_data = data.get("permissions", [])
        user_ids = data.get("users", [])
        
        # 1. Process permissions (Save/Update)
        perm_ids = []
        for p_data in permissions_data:
            p_id = p_data.get("id")
            # If ID is a timestamp-like large integer (from frontend new creation), treat as new
            # or if it doesn't exist in DB. 
            # Ideally, if it's a new item from frontend, ID might be temporary. 
            # But let's check if we should update or create.
            
            # Prepare permission model data
            expr_tree = p_data.get("expression_tree")
            if isinstance(expr_tree, dict):
                expr_tree = json.dumps(expr_tree)
            
            perm_config = p_data.get("permissions")
            if isinstance(perm_config, list):
                perm_config = json.dumps(perm_config)
            elif isinstance(perm_config, dict):
                 perm_config = json.dumps([perm_config]) # Should be list

            p_obj = TDsPermission(
                name=p_data.get("name"),
                type=p_data.get("type"),
                ds_id=p_data.get("ds_id"),
                table_id=p_data.get("table_id"),
                expression_tree=expr_tree,
                permissions=perm_config,
                enable=True
            )
            
            if p_id and isinstance(p_id, int) and p_id < 2000000000000: 
                # Assuming real DB IDs are smaller than timestamp-based IDs
                # Or check if it exists
                stmt = select(TDsPermission).where(TDsPermission.id == p_id)
                existing = session.execute(stmt).scalar_one_or_none()
                if existing:
                    existing.name = p_obj.name
                    existing.type = p_obj.type
                    existing.ds_id = p_obj.ds_id
                    existing.table_id = p_obj.table_id
                    existing.expression_tree = p_obj.expression_tree
                    existing.permissions = p_obj.permissions
                    session.flush()
                    perm_ids.append(existing.id)
                else:
                    session.add(p_obj)
                    session.flush()
                    perm_ids.append(p_obj.id)
            else:
                session.add(p_obj)
                session.flush()
                perm_ids.append(p_obj.id)
        
        # 2. Save Rule
        rule_obj = TDsRules(
            name=name,
            permission_list=json.dumps(perm_ids),
            user_list=json.dumps(user_ids),
            enable=True
        )
        
        if rule_id:
            stmt = select(TDsRules).where(TDsRules.id == rule_id)
            existing_rule = session.execute(stmt).scalar_one_or_none()
            if existing_rule:
                existing_rule.name = name
                existing_rule.permission_list = json.dumps(perm_ids)
                existing_rule.user_list = json.dumps(user_ids)
            else:
                return False
        else:
            session.add(rule_obj)
            
        return True

    @staticmethod
    def delete_permission(session: Session, rule_id: int) -> bool:
        stmt = select(TDsRules).where(TDsRules.id == rule_id)
        rule = session.execute(stmt).scalar_one_or_none()
        if rule:
            # Optionally delete associated permissions if they are not shared
            # For simplicity, we just delete the rule now. 
            # In a real system, we might check if permissions are used by other rules.
            session.delete(rule)
            return True
        return False
