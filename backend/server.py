from fastapi import FastAPI, APIRouter, HTTPException, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, date
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
import calendar
import json
from bson import json_util


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

class InvoiceItem(BaseModel):
    description: str
    quantity: float
    rate: float
    amount: float

class Customer(BaseModel):
    name: str
    mobile: Optional[str] = None
    address: Optional[str] = None

class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None
    payment_type: str  # "Cash" or "Credit"
    customer: Optional[Customer] = None
    items: List[InvoiceItem]
    subtotal: float
    discount: float = 0
    gst_rate: float = 0
    gst_amount: float = 0
    total: float
    notes: Optional[str] = None
    terms: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "Unpaid"  # "Paid", "Unpaid", "Partial"
    amount_paid: float = 0

class InvoiceCreate(BaseModel):
    payment_type: str
    customer: Optional[Customer] = None
    items: List[InvoiceItem]
    subtotal: float
    discount: float = 0
    gst_rate: float = 0
    gst_amount: float = 0
    total: float
    notes: Optional[str] = None
    terms: Optional[str] = None
    due_date: Optional[date] = None

class CompanyProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    bank_details: Optional[str] = None
    footer_text: Optional[str] = "Thank you for your business!"
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class CompanyProfileCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    bank_details: Optional[str] = None
    footer_text: Optional[str] = "Thank you for your business!"

# Helper function to generate invoice number
async def generate_invoice_number():
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Count invoices for current month
    start_of_month = datetime(current_year, current_month, 1)
    end_of_month = datetime(current_year, current_month, calendar.monthrange(current_year, current_month)[1], 23, 59, 59)
    
    count = await db.invoices.count_documents({
        "created_at": {"$gte": start_of_month, "$lte": end_of_month}
    })
    
    next_number = count + 1
    return f"INV/{current_year}/{current_month:02d}/{next_number:03d}"

# Helper function to generate PDF
async def generate_pdf(invoice: Invoice, company: CompanyProfile):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )
    
    # Build the story
    story = []
    
    # Company Header
    story.append(Paragraph(company.name, title_style))
    if company.phone or company.email:
        contact_info = []
        if company.phone:
            contact_info.append(f"Phone: {company.phone}")
        if company.email:
            contact_info.append(f"Email: {company.email}")
        story.append(Paragraph(" | ".join(contact_info), styles['Normal']))
    
    if company.address:
        story.append(Paragraph(company.address, styles['Normal']))
    if company.gstin:
        story.append(Paragraph(f"GSTIN: {company.gstin}", styles['Normal']))
    
    story.append(Spacer(1, 20))
    
    # Invoice Header - Use simple paragraphs instead of HTML
    story.append(Paragraph("INVOICE", ParagraphStyle('InvoiceTitle', parent=styles['Heading2'], alignment=TA_CENTER)))
    story.append(Paragraph(f"Invoice No: {invoice.invoice_number}", ParagraphStyle('InvoiceInfo', parent=styles['Normal'], alignment=TA_CENTER)))
    story.append(Paragraph(f"Date: {invoice.invoice_date.strftime('%d-%m-%Y')}", ParagraphStyle('InvoiceInfo', parent=styles['Normal'], alignment=TA_CENTER)))
    
    if invoice.due_date:
        story.append(Paragraph(f"Due Date: {invoice.due_date.strftime('%d-%m-%Y')}", ParagraphStyle('InvoiceInfo', parent=styles['Normal'], alignment=TA_CENTER)))
    
    story.append(Spacer(1, 20))
    
    # Customer Details
    if invoice.customer:
        story.append(Paragraph("<b>Bill To:</b>", styles['Normal']))
        story.append(Paragraph(invoice.customer.name, styles['Normal']))
        if invoice.customer.mobile:
            story.append(Paragraph(f"Mobile: {invoice.customer.mobile}", styles['Normal']))
        if invoice.customer.address:
            story.append(Paragraph(invoice.customer.address, styles['Normal']))
        story.append(Spacer(1, 20))
    
    # Items Table
    table_data = [['Description', 'Quantity', 'Rate', 'Amount']]
    for item in invoice.items:
        table_data.append([
            item.description,
            f"{item.quantity:,.2f}",
            f"₹{item.rate:,.2f}",
            f"₹{item.amount:,.2f}"
        ])
    
    # Add totals
    table_data.append(['', '', 'Subtotal:', f"₹{invoice.subtotal:,.2f}"])
    if invoice.discount > 0:
        table_data.append(['', '', 'Discount:', f"₹{invoice.discount:,.2f}"])
    if invoice.gst_amount > 0:
        table_data.append(['', '', f'GST ({invoice.gst_rate}%):', f"₹{invoice.gst_amount:,.2f}"])
    table_data.append(['', '', 'Total:', f"₹{invoice.total:,.2f}"])
    
    table = Table(table_data, colWidths=[3*inch, 1*inch, 1*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -4), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
    ]))
    story.append(table)
    
    story.append(Spacer(1, 20))
    
    # Payment Type
    story.append(Paragraph(f"<b>Payment Type:</b> {invoice.payment_type}", styles['Normal']))
    
    # Notes
    if invoice.notes:
        story.append(Spacer(1, 20))
        story.append(Paragraph("<b>Notes:</b>", styles['Normal']))
        story.append(Paragraph(invoice.notes, styles['Normal']))
    
    # Terms
    if invoice.terms:
        story.append(Spacer(1, 20))
        story.append(Paragraph("<b>Terms & Conditions:</b>", styles['Normal']))
        story.append(Paragraph(invoice.terms, styles['Normal']))
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph(company.footer_text, styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# Custom JSON encoder to handle date objects
def custom_json_encoder(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Invoice Generator API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Invoice Routes
@api_router.post("/invoices", response_model=Invoice)
async def create_invoice(invoice_data: InvoiceCreate):
    invoice_dict = invoice_data.dict()
    invoice_dict["invoice_number"] = await generate_invoice_number()
    invoice_dict["invoice_date"] = date.today()
    invoice_dict["status"] = "Paid" if invoice_data.payment_type == "Cash" else "Unpaid"
    invoice_dict["amount_paid"] = invoice_data.total if invoice_data.payment_type == "Cash" else 0
    
    # Convert date objects to strings for MongoDB
    if invoice_dict.get("due_date"):
        invoice_dict["due_date"] = invoice_dict["due_date"].isoformat()
    invoice_dict["invoice_date"] = invoice_dict["invoice_date"].isoformat()
    
    invoice = Invoice(**invoice_dict)
    result = await db.invoices.insert_one(json.loads(json.dumps(invoice.dict(), default=custom_json_encoder)))
    
    if result.inserted_id:
        return invoice
    else:
        raise HTTPException(status_code=500, detail="Failed to create invoice")

@api_router.get("/invoices", response_model=List[Invoice])
async def get_invoices():
    invoices = await db.invoices.find().to_list(1000)
    # Convert string dates back to date objects
    for invoice in invoices:
        if invoice.get("invoice_date"):
            invoice["invoice_date"] = date.fromisoformat(invoice["invoice_date"])
        if invoice.get("due_date"):
            invoice["due_date"] = date.fromisoformat(invoice["due_date"])
    return [Invoice(**invoice) for invoice in invoices]

@api_router.get("/invoices/{invoice_id}", response_model=Invoice)
async def get_invoice(invoice_id: str):
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    # Convert string dates back to date objects
    if invoice.get("invoice_date"):
        invoice["invoice_date"] = date.fromisoformat(invoice["invoice_date"])
    if invoice.get("due_date"):
        invoice["due_date"] = date.fromisoformat(invoice["due_date"])
    return Invoice(**invoice)

@api_router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: str):
    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Convert string dates back to date objects
    if invoice.get("invoice_date"):
        invoice["invoice_date"] = date.fromisoformat(invoice["invoice_date"])
    if invoice.get("due_date") and invoice["due_date"]:
        invoice["due_date"] = date.fromisoformat(invoice["due_date"])
    
    # Get company profile
    company_doc = await db.company_profile.find_one()
    if not company_doc:
        # Create default company profile
        default_company = CompanyProfile(name="Your Company Name")
        await db.company_profile.insert_one(default_company.dict())
        company = default_company
    else:
        company = CompanyProfile(**company_doc)
    
    invoice_obj = Invoice(**invoice)
    pdf_buffer = await generate_pdf(invoice_obj, company)
    
    return Response(
        content=pdf_buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{invoice_obj.invoice_number}.pdf"}
    )

# Company Profile Routes
@api_router.post("/company-profile", response_model=CompanyProfile)
async def create_or_update_company_profile(company_data: CompanyProfileCreate):
    # Check if profile exists
    existing = await db.company_profile.find_one()
    
    if existing:
        # Update existing
        await db.company_profile.update_one(
            {"id": existing["id"]},
            {"$set": {**company_data.dict(), "updated_at": datetime.utcnow()}}
        )
        updated_profile = await db.company_profile.find_one({"id": existing["id"]})
        return CompanyProfile(**updated_profile)
    else:
        # Create new
        profile = CompanyProfile(**company_data.dict())
        result = await db.company_profile.insert_one(profile.dict())
        if result.inserted_id:
            return profile
        else:
            raise HTTPException(status_code=500, detail="Failed to create company profile")

@api_router.get("/company-profile", response_model=CompanyProfile)
async def get_company_profile():
    profile = await db.company_profile.find_one()
    if not profile:
        # Return default profile
        default_profile = CompanyProfile(name="Your Company Name")
        return default_profile
    return CompanyProfile(**profile)

# Customer Routes
@api_router.get("/customers")
async def get_customers():
    # Get unique customers from invoices
    pipeline = [
        {"$match": {"customer": {"$ne": None}}},
        {"$group": {
            "_id": "$customer.name",
            "name": {"$first": "$customer.name"},
            "mobile": {"$first": "$customer.mobile"},
            "address": {"$first": "$customer.address"},
            "total_credit": {"$sum": {"$cond": [{"$eq": ["$payment_type", "Credit"]}, "$total", 0]}},
            "amount_paid": {"$sum": "$amount_paid"},
            "invoice_count": {"$sum": 1}
        }},
        {"$project": {
            "name": 1,
            "mobile": 1,
            "address": 1,
            "total_credit": 1,
            "amount_paid": 1,
            "outstanding": {"$subtract": ["$total_credit", "$amount_paid"]},
            "invoice_count": 1
        }}
    ]
    
    customers = await db.invoices.aggregate(pipeline).to_list(1000)
    return customers

# Reports Routes
@api_router.get("/reports/summary")
async def get_reports_summary():
    today = datetime.now().date()
    start_of_month = datetime(today.year, today.month, 1)
    
    # Convert date to string for MongoDB query
    today_str = today.isoformat()
    
    # Today's sales
    today_sales = await db.invoices.aggregate([
        {"$match": {"invoice_date": {"$eq": today_str}}},
        {"$group": {
            "_id": None,
            "total_sales": {"$sum": "$total"},
            "cash_sales": {"$sum": {"$cond": [{"$eq": ["$payment_type", "Cash"]}, "$total", 0]}},
            "credit_sales": {"$sum": {"$cond": [{"$eq": ["$payment_type", "Credit"]}, "$total", 0]}},
            "invoice_count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    # This month's sales
    month_sales = await db.invoices.aggregate([
        {"$match": {"created_at": {"$gte": start_of_month}}},
        {"$group": {
            "_id": None,
            "total_sales": {"$sum": "$total"},
            "cash_sales": {"$sum": {"$cond": [{"$eq": ["$payment_type", "Cash"]}, "$total", 0]}},
            "credit_sales": {"$sum": {"$cond": [{"$eq": ["$payment_type", "Credit"]}, "$total", 0]}},
            "invoice_count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    # Total outstanding
    outstanding = await db.invoices.aggregate([
        {"$match": {"payment_type": "Credit"}},
        {"$group": {
            "_id": None,
            "total_outstanding": {"$sum": {"$subtract": ["$total", "$amount_paid"]}}
        }}
    ]).to_list(1)
    
    return {
        "today": today_sales[0] if today_sales else {"total_sales": 0, "cash_sales": 0, "credit_sales": 0, "invoice_count": 0},
        "this_month": month_sales[0] if month_sales else {"total_sales": 0, "cash_sales": 0, "credit_sales": 0, "invoice_count": 0},
        "total_outstanding": outstanding[0]["total_outstanding"] if outstanding else 0
    }

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()