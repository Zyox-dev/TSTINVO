import requests
import unittest
import json
from datetime import datetime, date, timedelta

class InvoiceGeneratorAPITest(unittest.TestCase):
    def setUp(self):
        # Get the backend URL from the frontend .env file
        self.base_url = "https://ac7fcd36-8271-4911-8c58-89645029ad1a.preview.emergentagent.com/api"
        self.test_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.invoice_id = None
        
    def test_01_api_status(self):
        """Test if the API is accessible"""
        print("\n🔍 Testing API accessibility...")
        response = requests.get(f"{self.base_url}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Invoice Generator API"})
        print("✅ API is accessible")
        
    def test_02_status_check(self):
        """Test status check endpoint"""
        print("\n🔍 Testing status check endpoint...")
        data = {"client_name": f"test_client_{self.test_timestamp}"}
        response = requests.post(f"{self.base_url}/status", json=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["client_name"], data["client_name"])
        print("✅ Status check endpoint working")
        
    def test_03_company_profile(self):
        """Test company profile creation and retrieval"""
        print("\n🔍 Testing company profile management...")
        
        # Create a test company profile
        company_data = {
            "name": f"Test Company {self.test_timestamp}",
            "phone": "1234567890",
            "email": "test@example.com",
            "address": "123 Test Street, Test City",
            "gstin": "TEST1234567890",
            "bank_details": "Test Bank, Acc: 123456789",
            "footer_text": "Thank you for testing!"
        }
        
        response = requests.post(f"{self.base_url}/company-profile", json=company_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], company_data["name"])
        
        # Retrieve the company profile
        response = requests.get(f"{self.base_url}/company-profile")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], company_data["name"])
        print("✅ Company profile management working")
        
    def test_04_create_cash_invoice(self):
        """Test creating a cash invoice"""
        print("\n🔍 Testing cash invoice creation...")
        
        # Create a cash invoice
        invoice_data = {
            "payment_type": "Cash",
            "items": [
                {
                    "description": "Test Item 1",
                    "quantity": 2,
                    "rate": 100,
                    "amount": 200
                },
                {
                    "description": "Test Item 2",
                    "quantity": 1,
                    "rate": 50,
                    "amount": 50
                }
            ],
            "subtotal": 250,
            "discount": 10,
            "gst_rate": 5,
            "gst_amount": 12,
            "total": 252,
            "notes": "Test notes",
            "terms": "Test terms"
        }
        
        response = requests.post(f"{self.base_url}/invoices", json=invoice_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payment_type"], "Cash")
        self.assertEqual(response.json()["status"], "Paid")
        self.assertEqual(response.json()["amount_paid"], 252)
        
        # Save the invoice ID for later tests
        self.invoice_id = response.json()["id"]
        print(f"✅ Cash invoice created with ID: {self.invoice_id}")
        
    def test_05_create_credit_invoice(self):
        """Test creating a credit invoice"""
        print("\n🔍 Testing credit invoice creation...")
        
        # Create a credit invoice with customer details
        tomorrow = (date.today() + timedelta(days=7)).isoformat()
        
        invoice_data = {
            "payment_type": "Credit",
            "customer": {
                "name": f"Test Customer {self.test_timestamp}",
                "mobile": "9876543210",
                "address": "456 Test Avenue, Test Town"
            },
            "items": [
                {
                    "description": "Credit Item 1",
                    "quantity": 3,
                    "rate": 200,
                    "amount": 600
                }
            ],
            "subtotal": 600,
            "discount": 0,
            "gst_rate": 18,
            "gst_amount": 108,
            "total": 708,
            "notes": "Credit invoice test",
            "terms": "Net 7 days",
            "due_date": tomorrow
        }
        
        response = requests.post(f"{self.base_url}/invoices", json=invoice_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payment_type"], "Credit")
        self.assertEqual(response.json()["status"], "Unpaid")
        self.assertEqual(response.json()["amount_paid"], 0)
        self.assertEqual(response.json()["customer"]["name"], invoice_data["customer"]["name"])
        print("✅ Credit invoice created successfully")
        
    def test_06_get_invoices(self):
        """Test retrieving all invoices"""
        print("\n🔍 Testing invoice retrieval...")
        
        response = requests.get(f"{self.base_url}/invoices")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        
        # Check if our test invoices are in the list
        found = False
        for invoice in response.json():
            if invoice["id"] == self.invoice_id:
                found = True
                break
                
        self.assertTrue(found, "Created invoice not found in the list")
        print("✅ Invoice retrieval working")
        
    def test_07_get_specific_invoice(self):
        """Test retrieving a specific invoice"""
        print("\n🔍 Testing specific invoice retrieval...")
        
        if not self.invoice_id:
            self.skipTest("No invoice ID available from previous tests")
            
        response = requests.get(f"{self.base_url}/invoices/{self.invoice_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.invoice_id)
        print("✅ Specific invoice retrieval working")
        
    def test_08_get_customers(self):
        """Test retrieving customers"""
        print("\n🔍 Testing customer retrieval...")
        
        response = requests.get(f"{self.base_url}/customers")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        print("✅ Customer retrieval working")
        
    def test_09_get_reports_summary(self):
        """Test retrieving reports summary"""
        print("\n🔍 Testing reports summary...")
        
        response = requests.get(f"{self.base_url}/reports/summary")
        self.assertEqual(response.status_code, 200)
        self.assertIn("today", response.json())
        self.assertIn("this_month", response.json())
        self.assertIn("total_outstanding", response.json())
        print("✅ Reports summary working")
        
    def test_10_pdf_generation(self):
        """Test PDF generation"""
        print("\n🔍 Testing PDF generation...")
        
        if not self.invoice_id:
            self.skipTest("No invoice ID available from previous tests")
            
        response = requests.get(f"{self.base_url}/invoices/{self.invoice_id}/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        print("✅ PDF generation working")

if __name__ == "__main__":
    # Run the tests in order
    unittest.main(argv=['first-arg-is-ignored'], exit=False)