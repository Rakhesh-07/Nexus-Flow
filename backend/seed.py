import os
import sys
import shutil
import datetime

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.database import Base, engine, SessionLocal
from database.models import User, Document, Conversation, WorkflowExecution, AuditLog
from api.security import get_password_hash
from rag.document_processor import chunk_text
from rag.chroma_service import chroma_service
from loguru import logger

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

DEPT_PREFIXES = {
    "Human Resources": "hr",
    "Finance": "finance",
    "Legal": "legal",
    "Engineering": "eng",
    "Information Technology": "it",
    "Operations": "ops",
    "Sales": "sales",
    "Marketing": "marketing"
}

ROLES_CONFIG = [
    {"role": "department_manager", "clearance": "RESTRICTED", "suffix": "manager", "desig_prefix": "Director of"},
    {"role": "team_lead", "clearance": "CONFIDENTIAL", "suffix": "lead", "desig_prefix": "Team Lead,"},
    {"role": "employee", "clearance": "INTERNAL", "suffix": "employee", "desig_prefix": "Specialist,"},
    {"role": "guest", "clearance": "PUBLIC", "suffix": "guest", "desig_prefix": "External Guest,"}
]

# Generate 32 department users + 1 Super Admin = 33 Users
SEED_USERS = [
    {
        "username": "admin@nexusflow.ai",
        "password": "Password123!",
        "role": "super_admin",
        "department": "Information Technology",
        "clearance_level": "HIGHLY_CONFIDENTIAL",
        "designation": "Chief Information Officer & Super Admin",
        "full_name": "Executive Super Admin",
        "email": "admin@nexusflow.ai",
        "contact_details": "+1 (800) 555-0100"
    }
]

for dept in DEPARTMENTS:
    prefix = DEPT_PREFIXES[dept]
    for r_conf in ROLES_CONFIG:
        u_email = f"{prefix}.{r_conf['suffix']}@nexusflow.ai"
        SEED_USERS.append({
            "username": u_email,
            "password": "Password123!",
            "role": r_conf["role"],
            "department": dept,
            "clearance_level": r_conf["clearance"],
            "designation": f"{r_conf['desig_prefix']} {dept}",
            "full_name": f"{dept} {r_conf['suffix'].capitalize()}",
            "email": u_email,
            "contact_details": f"+1 (555) 019-{len(SEED_USERS):04d}"
        })

# 3 Documents per Department = 24 Documents total across all 8 departments
SEED_DOCUMENTS = [
    # Human Resources
    {
        "filename": "HR_Company_Policy_Handbook_2025.txt",
        "department": "Human Resources",
        "classification": "INTERNAL",
        "visibility": "Organization",
        "uploader_username": "hr.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "NEXUSFLOW GLOBAL HUMAN RESOURCES POLICY HANDBOOK 2025\n"
            "Workplace Guidelines & Benefits Summary:\n"
            "- Core Collaboration Hours: 10:00 AM - 4:00 PM EST.\n"
            "- PTO Accrual: 22 paid annual days off for full-time personnel.\n"
            "- Parental Leave: 16 paid weeks for primary caregivers.\n"
            "- Home Office Stipend: $1,200 annual remote setup reimbursement."
        )
    },
    {
        "filename": "HR_Executive_Compensation_Review.txt",
        "department": "Human Resources",
        "classification": "RESTRICTED",
        "visibility": "Department",
        "uploader_username": "hr.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "RESTRICTED HR EXECUTIVE COMPENSATION REVIEW\n"
            "- Executive Bonus Pool: $4,200,000 allocated based on Q4 ARR targets.\n"
            "- Equity Refresh Grants: VP levels eligible for 25,000 ISO options vesting over 4 years.\n"
            "- Salary Band Adjustments: 5.5% merit increase cap for FY2025.\n"
            "Restricted Access Notice: HR Leadership and Super Admins only."
        )
    },
    {
        "filename": "HR_Pending_Remote_Work_Update.txt",
        "department": "Human Resources",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "hr.employee@nexusflow.ai",
        "approved": False,
        "content": (
            "DRAFT HR REMOTE WORK REVISION PROPOSAL\n"
            "Proposal to allow 30 consecutive business days of work-from-anywhere flexibility per calendar year.\n"
            "Status: Pending HR Manager (hr.manager@nexusflow.ai) approval."
        )
    },

    # Finance
    {
        "filename": "Finance_Q1_2025_Revenue_Report.txt",
        "department": "Finance",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "finance.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "NEXUSFLOW Q1 2025 FINANCIAL PERFORMANCE REPORT\n"
            "- Total Revenue: $42,500,000 USD (18% YoY Growth)\n"
            "- Recurring Subscription Revenue (ARR): $36,200,000 USD\n"
            "- Gross Margin: 82.4%\n"
            "- Capital Expenditure: $6,100,000 spent on GPU infrastructure and data center expansion."
        )
    },
    {
        "filename": "Finance_Mergers_Acquisitions_Strategy.txt",
        "department": "Finance",
        "classification": "RESTRICTED",
        "visibility": "Department",
        "uploader_username": "finance.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "STRICTLY RESTRICTED FINANCE M&A STRATEGY DOC\n"
            "Project Synergy - Target Acquisition Profile:\n"
            "- Evaluating acquisition of VectorScale Inc for $28,000,000 in cash & stock.\n"
            "- Synergies: Accelerates ChromaDB vector search performance by 4x.\n"
            "Restricted Notice: Finance Executives and C-Suite only."
        )
    },
    {
        "filename": "Finance_Pending_Q3_Budget_Adjustment.txt",
        "department": "Finance",
        "classification": "CONFIDENTIAL",
        "visibility": "Department",
        "uploader_username": "finance.employee@nexusflow.ai",
        "approved": False,
        "content": (
            "PENDING FINANCE BUDGET ADJUSTMENT\n"
            "Requesting $450,000 reallocation from marketing events to cloud compute infrastructure.\n"
            "Status: Pending Finance Manager (finance.manager@nexusflow.ai) approval."
        )
    },

    # Legal
    {
        "filename": "Legal_Standard_NDA_Template.txt",
        "department": "Legal",
        "classification": "PUBLIC",
        "visibility": "Organization",
        "uploader_username": "legal.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "NEXUSFLOW STANDARD MUTUAL NON-DISCLOSURE AGREEMENT (NDA)\n"
            "1. Definition of Confidential Information: Proprietary data, source code, workflows, customer lists.\n"
            "2. Non-Use Period: 3 years from execution date.\n"
            "3. Governing Law: State of Delaware."
        )
    },
    {
        "filename": "Legal_Litigation_Risk_Assessment.txt",
        "department": "Legal",
        "classification": "RESTRICTED",
        "visibility": "Department",
        "uploader_username": "legal.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "RESTRICTED LEGAL LITIGATION & PATENT RISK ASSESSMENT\n"
            "- Review of Patent #US-9842109 regarding AI Graph Workflow orchestration.\n"
            "- Outside Counsel Opinion: Low infringement risk (85% confidence score).\n"
            "- Settlement Reserve Fund: $1,500,000 set aside in escrow."
        )
    },
    {
        "filename": "Legal_Pending_Vendor_Agreement.txt",
        "department": "Legal",
        "classification": "CONFIDENTIAL",
        "visibility": "Department",
        "uploader_username": "legal.lead@nexusflow.ai",
        "approved": False,
        "content": (
            "PENDING LEGAL VENDOR CONTRACT REVIEW\n"
            "Draft Master Services Agreement with CloudScale Hosting Services.\n"
            "Status: Pending General Counsel (legal.manager@nexusflow.ai) sign-off."
        )
    },

    # Engineering
    {
        "filename": "Engineering_System_Architecture_Spec.txt",
        "department": "Engineering",
        "classification": "CONFIDENTIAL",
        "visibility": "Department",
        "uploader_username": "eng.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "NEXUSFLOW MULTI-AGENT SYSTEM ARCHITECTURE SPECIFICATION\n"
            "- Orchestrator Engine: LangGraph StateGraph pipeline\n"
            "- Agents: Planner -> Retriever -> Researcher -> Tool -> Reasoner -> Validator -> Responder\n"
            "- Vector Store: ChromaDB with persistent collection storage at ./chroma_db\n"
            "- RBAC Filter: Metadata filtering by tenant_id, department, clearance_level prior to similarity search."
        )
    },
    {
        "filename": "Engineering_Patents_Core_Algorithm.txt",
        "department": "Engineering",
        "classification": "HIGHLY_CONFIDENTIAL",
        "visibility": "Private",
        "uploader_username": "admin@nexusflow.ai",
        "approved": True,
        "content": (
            "HIGHLY CONFIDENTIAL PATENT ALGORITHM SPECIFICATION\n"
            "Dynamic Self-Healing Swarm Routing Protocol:\n"
            "Contains proprietary mathematical proofs for token reduction and auto-retry consensus validation.\n"
            "Access Restricted: Super Admin (admin@nexusflow.ai) exclusive access."
        )
    },
    {
        "filename": "Engineering_Pending_Microservices_RFC.txt",
        "department": "Engineering",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "eng.employee@nexusflow.ai",
        "approved": False,
        "content": (
            "RFC 104: PROPOSED KUBERNETES MIGRATION FOR VECTOR INGESTION\n"
            "Proposal to decouple PyPDF2 extraction workers into scalable Celery task queues.\n"
            "Status: Pending VP of Engineering (eng.manager@nexusflow.ai) approval."
        )
    },

    # Information Technology
    {
        "filename": "IT_Disaster_Recovery_Plan.txt",
        "department": "Information Technology",
        "classification": "RESTRICTED",
        "visibility": "Department",
        "uploader_username": "it.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "NEXUSFLOW IT DISASTER RECOVERY & BCP PLAN\n"
            "- Recovery Time Objective (RTO): < 15 minutes for primary API endpoints.\n"
            "- Recovery Point Objective (RPO): < 1 minute via automated PostgreSQL streaming replication.\n"
            "- Backup Locations: Multi-region AWS S3 buckets encrypted with AES-256."
        )
    },
    {
        "filename": "IT_Zero_Trust_Network_Guidelines.txt",
        "department": "Information Technology",
        "classification": "INTERNAL",
        "visibility": "Organization",
        "uploader_username": "it.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "IT ZERO-TRUST NETWORK & MFA MANDATE\n"
            "All employee devices accessing NexusFlow APIs must pass Okta SSO multi-factor authentication\n"
            "and run compliant endpoint protection software."
        )
    },
    {
        "filename": "IT_Pending_Hardware_Refresh_Req.txt",
        "department": "Information Technology",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "it.employee@nexusflow.ai",
        "approved": False,
        "content": (
            "PENDING IT HARDWARE REFRESH REQUEST\n"
            "Request for 50 Apple M3 Max Developer Laptops for Engineering and IT departments.\n"
            "Status: Pending IT Manager (it.manager@nexusflow.ai) approval."
        )
    },

    # Operations
    {
        "filename": "Operations_Supply_Chain_Logistics_SOP.txt",
        "department": "Operations",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "ops.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "OPERATIONS SUPPLY CHAIN STANDARD OPERATING PROCEDURE (SOP)\n"
            "- Lead Time Target: 48 hours for global server hardware delivery.\n"
            "- Primary Freight Carriers: DHL Express & FedEx Supply Chain.\n"
            "- Quality Control Audit Frequency: Monthly inventory checks."
        )
    },
    {
        "filename": "Operations_Vendor_Procurement_Contracts.txt",
        "department": "Operations",
        "classification": "CONFIDENTIAL",
        "visibility": "Department",
        "uploader_username": "ops.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "CONFIDENTIAL OPERATIONS PROCUREMENT AGREEMENTS\n"
            "- Bulk GPU Hardware Supplier Contract: $14,000,000 commitments through 2026.\n"
            "- Discount Terms: 12.5% tier rebate on orders exceeding 100 units."
        )
    },
    {
        "filename": "Operations_Pending_Warehouse_Automation.txt",
        "department": "Operations",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "ops.employee@nexusflow.ai",
        "approved": False,
        "content": (
            "PENDING OPERATIONS WAREHOUSE AUTOMATION PROPOSAL\n"
            "Proposal to integrate automated robotics sorting in EU distribution hubs.\n"
            "Status: Pending Operations Director (ops.manager@nexusflow.ai) approval."
        )
    },

    # Sales
    {
        "filename": "Sales_Enterprise_Pricing_Tier_2025.txt",
        "department": "Sales",
        "classification": "CONFIDENTIAL",
        "visibility": "Department",
        "uploader_username": "sales.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "NEXUSFLOW ENTERPRISE SALES PRICING MATRIX 2025\n"
            "- Tier 1 Enterprise (Up to 500 users): $120,000 / year\n"
            "- Tier 2 Fortune 500 (Unlimited users + Dedicated GPU cluster): $450,000 / year\n"
            "- Maximum Account Executive Discount Authorization: 15% without VP approval."
        )
    },
    {
        "filename": "Sales_Global_Client_Directory.txt",
        "department": "Sales",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "sales.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "SALES GLOBAL CLIENT DIRECTORY\n"
            "- Key Enterprise Accounts: Microsoft, Oracle, SAP, ServiceNow, Deloitte, Accenture.\n"
            "- Renewal Pipeline Q3: 94% retention projection."
        )
    },
    {
        "filename": "Sales_Pending_Commission_Structure.txt",
        "department": "Sales",
        "classification": "CONFIDENTIAL",
        "visibility": "Department",
        "uploader_username": "sales.employee@nexusflow.ai",
        "approved": False,
        "content": (
            "PENDING SALES COMMISSION STRUCTURE REVISION\n"
            "Proposal to increase AE commission rate to 10% on multi-year contract renewals.\n"
            "Status: Pending Sales Manager (sales.manager@nexusflow.ai) approval."
        )
    },

    # Marketing
    {
        "filename": "Marketing_Brand_Identity_Styleguide.txt",
        "department": "Marketing",
        "classification": "PUBLIC",
        "visibility": "Organization",
        "uploader_username": "marketing.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "NEXUSFLOW BRAND IDENTITY & LOGO STYLEGUIDE\n"
            "- Primary Brand Color: Cyberpunk Electric Blue (#0066FF)\n"
            "- Secondary Accent: Emerald Green (#00FF66)\n"
            "- Typography: Inter (UI text) & JetBrains Mono (Code & Metrics)"
        )
    },
    {
        "filename": "Marketing_Q3_Product_Launch_Campaign.txt",
        "department": "Marketing",
        "classification": "CONFIDENTIAL",
        "visibility": "Department",
        "uploader_username": "marketing.manager@nexusflow.ai",
        "approved": True,
        "content": (
            "CONFIDENTIAL Q3 PRODUCT LAUNCH MARKETING STRATEGY\n"
            "- Campaign Theme: 'Enterprise AI Swarms with Zero Data Leakage'\n"
            "- Budget: $1,800,000 across LinkedIn ads, keynotes, and Gartner summits."
        )
    },
    {
        "filename": "Marketing_Pending_Ad_Spend_Budget.txt",
        "department": "Marketing",
        "classification": "INTERNAL",
        "visibility": "Department",
        "uploader_username": "marketing.lead@nexusflow.ai",
        "approved": False,
        "content": (
            "PENDING MARKETING AD SPEND ALLOCATION\n"
            "Request for $250,000 for Developer Relations sponsorships at AI conferences.\n"
            "Status: Pending Marketing Director (marketing.manager@nexusflow.ai) approval."
        )
    }
]


def seed_database():
    logger.info("Resetting SQLite & ChromaDB databases for Enterprise RBAC seeding...")

    # Drop existing tables and recreate cleanly
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Clean uploads directory
    uploads_dir = "./uploads"
    if os.path.exists(uploads_dir):
        shutil.rmtree(uploads_dir)
    os.makedirs(uploads_dir, exist_ok=True)

    db = SessionLocal()

    try:
        # Seed Users
        user_map = {}
        for user_data in SEED_USERS:
            u = User(
                username=user_data["username"],
                hashed_password=get_password_hash(user_data["password"]),
                role=user_data["role"],
                department=user_data["department"],
                clearance_level=user_data["clearance_level"],
                designation=user_data["designation"],
                full_name=user_data.get("full_name"),
                email=user_data.get("email"),
                contact_details=user_data.get("contact_details"),
                is_active=True
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            user_map[u.username] = u
            logger.info(f"Seeded Account: {u.username} | Role: {u.role} | Dept: {u.department} | Clearance: {u.clearance_level}")

        # Seed Documents
        for doc_data in SEED_DOCUMENTS:
            uploader = user_map.get(doc_data["uploader_username"])
            file_path = os.path.join(uploads_dir, f"{uploader.id}_{int(datetime.datetime.utcnow().timestamp())}_{doc_data['filename']}")
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(doc_data["content"])

            is_approved = doc_data["approved"]
            approved_by = uploader.id if is_approved else None
            approved_at = datetime.datetime.utcnow() if is_approved else None

            doc = Document(
                filename=doc_data["filename"],
                file_path=file_path,
                content_type="text/plain",
                department=doc_data["department"],
                team=uploader.team,
                user_id=uploader.id,
                owner_id=uploader.id,
                uploaded_by=uploader.id,
                classification=doc_data["classification"],
                visibility=doc_data["visibility"],
                approved=is_approved,
                approved_by=approved_by,
                approved_at=approved_at
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            if is_approved:
                chunks = chunk_text(doc_data["content"])
                metadatas = []
                ids = []
                for idx, chunk in enumerate(chunks):
                    metadatas.append({
                        "document_id": doc.id,
                        "tenant_id": uploader.id,
                        "user_id": uploader.id,
                        "owner_id": uploader.id,
                        "department": doc_data["department"],
                        "team": uploader.team or "",
                        "filename": doc_data["filename"],
                        "classification": doc_data["classification"],
                        "visibility": doc_data["visibility"],
                        "approved": True
                    })
                    ids.append(f"doc_{doc.id}_chunk_{idx}")
                chroma_service.add_chunks(texts=chunks, metadatas=metadatas, ids=ids)
                logger.info(f"Indexed Vector Chunks: {doc.filename} [{doc.department} | {doc.classification}] ({len(chunks)} chunks)")
            else:
                logger.info(f"Seeded Pending File: {doc.filename} [{doc.department}] (Awaiting Approval)")

            # Log Audit Event
            audit = AuditLog(
                timestamp=datetime.datetime.utcnow(),
                user_id=uploader.id,
                user_username=uploader.username,
                department=uploader.department,
                action="Upload",
                target_document_id=doc.id,
                target_document_title=doc.filename,
                status="SUCCESS" if is_approved else "PENDING_APPROVAL",
                ip_address="127.0.0.1",
                details={"classification": doc_data["classification"], "department": doc_data["department"]}
            )
            db.add(audit)
            db.commit()

        logger.info("NexusFlow Enterprise database seeding completed successfully! All 33 users and 24 files generated.")
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
