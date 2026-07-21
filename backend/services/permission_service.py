import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from database.models import User, Document, AuditLog
from loguru import logger

# Enterprise Departments
DEPARTMENTS = [
    "Human Resources",
    "Finance",
    "Legal",
    "Engineering",
    "Information Technology",
    "Operations",
    "Sales",
    "Marketing"
]

# Classification Hierarchy
CLASSIFICATIONS = [
    "PUBLIC",
    "INTERNAL",
    "CONFIDENTIAL",
    "RESTRICTED",
    "HIGHLY_CONFIDENTIAL"
]

CLASSIFICATION_RANK = {
    "PUBLIC": 1,
    "INTERNAL": 2,
    "CONFIDENTIAL": 3,
    "RESTRICTED": 4,
    "HIGHLY_CONFIDENTIAL": 5
}

# Role Hierarchy
ROLES = [
    "super_admin",
    "department_manager",
    "team_lead",
    "employee",
    "guest"
]

# Role Clearance Level Matrix
ROLE_CLEARANCE_MATRIX = {
    "guest": ["PUBLIC"],
    "employee": ["PUBLIC", "INTERNAL"],
    "team_lead": ["PUBLIC", "INTERNAL", "CONFIDENTIAL"],
    "department_manager": ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"],
    "super_admin": ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "HIGHLY_CONFIDENTIAL"]
}


class PermissionService:
    @staticmethod
    def get_allowed_classifications(user: User) -> List[str]:
        """
        Returns list of classifications user is authorized to access based on role & clearance level.
        """
        if not user or not user.is_active:
            return ["PUBLIC"]
            
        role = user.role.lower() if user.role else "guest"
        if role == "super_admin":
            return CLASSIFICATIONS
            
        matrix_allowed = ROLE_CLEARANCE_MATRIX.get(role, ["PUBLIC"])
        user_clearance = user.clearance_level.upper() if user.clearance_level else "INTERNAL"
        max_rank = CLASSIFICATION_RANK.get(user_clearance, 2)
        
        # Filter matrix by max rank of user's explicitly assigned clearance_level
        allowed = [c for c in matrix_allowed if CLASSIFICATION_RANK.get(c, 5) <= max_rank]
        return allowed if allowed else ["PUBLIC"]

    @staticmethod
    def can_upload_document(user: User) -> bool:
        """
        Guests and inactive users cannot upload documents.
        """
        if not user or not user.is_active:
            return False
        return user.role.lower() != "guest"

    @staticmethod
    def can_view_document(user: User, doc: Document) -> bool:
        """
        Determines if user has read permission for a document.
        """
        if not user or not user.is_active or not doc:
            return False

        role = user.role.lower() if user.role else "guest"

        # Super Admin has complete access
        if role == "super_admin":
            return True

        # Owner / Uploader can always view their document
        if doc.owner_id == user.id or doc.uploaded_by == user.id or doc.user_id == user.id:
            return True

        # Unapproved documents can only be viewed by Owner, Uploader, or Manager/Admin approving
        if not doc.approved:
            if role in ["department_manager", "team_lead"] and doc.department == user.department:
                return True
            return False

        # Classification check
        allowed_classifications = PermissionService.get_allowed_classifications(user)
        if doc.classification not in allowed_classifications:
            return False

        # Visibility rules
        vis = doc.visibility.lower() if doc.visibility else "department"
        if vis == "private":
            return doc.owner_id == user.id
            
        elif vis == "team":
            if doc.department != user.department:
                return False
            if doc.team and user.team and doc.team != user.team:
                if role not in ["department_manager", "team_lead"]:
                    return False
            return True

        elif vis == "department":
            return doc.department == user.department

        elif vis == "organization":
            return True

        elif vis == "custom users":
            allowed_users = []
            if isinstance(doc.tags, dict):
                allowed_users = doc.tags.get("allowed_users", [])
            return user.id in allowed_users or user.username in allowed_users

        return False

    @staticmethod
    def can_delete_document(user: User, doc: Document) -> bool:
        """
        Determines if user has delete permission for a document.
        """
        if not user or not user.is_active or not doc:
            return False

        role = user.role.lower() if user.role else "guest"
        if role == "super_admin":
            return True
            
        if role == "department_manager" and doc.department == user.department:
            return True

        if doc.owner_id == user.id or doc.uploaded_by == user.id or doc.user_id == user.id:
            return True

        return False

    @staticmethod
    def can_approve_document(user: User, doc: Document) -> bool:
        """
        Determines if user can approve a pending document.
        """
        if not user or not user.is_active or not doc:
            return False

        role = user.role.lower() if user.role else "guest"
        if role == "super_admin":
            return True

        if role == "department_manager" and doc.department == user.department:
            return True

        if role == "team_lead" and doc.department == user.department:
            if not doc.team or not user.team or doc.team == user.team:
                return True

        return False

    @staticmethod
    def can_manage_department(user: User, department: str) -> bool:
        """
        Super admin or Department Manager of target department.
        """
        if not user or not user.is_active:
            return False
            
        role = user.role.lower() if user.role else "guest"
        if role == "super_admin":
            return True
            
        if role == "department_manager" and user.department == department:
            return True
            
        return False

    @staticmethod
    def can_manage_users(user: User, target_user: Optional[User] = None) -> bool:
        """
        Super admin can manage all users. Department Manager can manage employees in their department.
        """
        if not user or not user.is_active:
            return False

        role = user.role.lower() if user.role else "guest"
        if role == "super_admin":
            return True

        if role == "department_manager":
            if target_user:
                return target_user.department == user.department and target_user.role.lower() != "super_admin"
            return True

        return False

    @staticmethod
    def build_chroma_filter(user: User) -> Dict[str, Any]:
        """
        Builds strict metadata filter for ChromaDB similarity searches.
        Only chunks matching authorized tenant, department, approval, and classification rules are returned.
        """
        if not user or not user.is_active:
            return {"$and": [{"approved": True}, {"classification": "PUBLIC"}, {"visibility": "Organization"}]}

        role = user.role.lower() if user.role else "guest"
        allowed_classifications = PermissionService.get_allowed_classifications(user)

        # Base approval rule
        filter_conditions = [{"approved": True}]

        # Super Admin sees all approved chunks
        if role == "super_admin":
            return {"approved": True}

        # Guest only sees approved PUBLIC organization documents
        if role == "guest":
            return {
                "$and": [
                    {"approved": True},
                    {"classification": "PUBLIC"},
                    {"visibility": "Organization"}
                ]
            }

        # Filter by department or organization visibility
        dept_condition = {
            "$or": [
                {"department": user.department},
                {"visibility": "Organization"},
                {"owner_id": user.id}
            ]
        }
        filter_conditions.append(dept_condition)

        # Filter by classifications
        if len(allowed_classifications) == 1:
            filter_conditions.append({"classification": allowed_classifications[0]})
        elif len(allowed_classifications) > 1:
            filter_conditions.append({
                "$or": [{"classification": c} for c in allowed_classifications]
            })

        return {"$and": filter_conditions}

    @staticmethod
    def log_audit_event(
        db: Session,
        user: Optional[User],
        action: str,
        status: str,
        target_document: Optional[Document] = None,
        ip_address: Optional[str] = "127.0.0.1",
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Logs security & operational event into PostgreSQL/SQLite AuditLog table.
        """
        try:
            username = user.username if user else "anonymous"
            user_id = user.id if user else None
            dept = user.department if user else None

            doc_id = target_document.id if target_document else None
            doc_title = target_document.filename if target_document else None

            log_entry = AuditLog(
                timestamp=datetime.datetime.utcnow(),
                user_id=user_id,
                user_username=username,
                department=dept,
                action=action,
                target_document_id=doc_id,
                target_document_title=doc_title,
                status=status,
                ip_address=ip_address,
                details=details
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            return log_entry
        except Exception as e:
            logger.error(f"Audit log insertion failed: {e}")
            db.rollback()
            return None
