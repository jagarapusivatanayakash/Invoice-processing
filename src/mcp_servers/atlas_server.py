#!/usr/bin/env python3
"""
MCP ATLAS Server
Handles abilities requiring external system interaction:
- OCR (Tesseract/Google Vision/AWS Textract)
- ERP connector (SAP/NetSuite/Oracle)
- Vendor enrichment (Clearbit/PDL/Vendor DB)
- Posting to ERP
- Notifications
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List
import pytesseract
from PIL import Image


class AtlasServer:
    """
    MCP ATLAS Server - External system interactions
    Routes to appropriate external services
    """

    def __init__(self):
        self.name = "ATLAS"
        self.version = "1.0.0"
        self.tools = self._register_tools()

        # Load data for mock ERP
        self.erp_data = self._load_erp_data()
        self.vendor_db = self._load_vendor_db()

    def _register_tools(self) -> Dict[str, Any]:
        """Register all available tools"""
        return {
            "ocr_extract": self.ocr_extract,
            "enrich_vendor": self.enrich_vendor,
            "fetch_po": self.fetch_po,
            "fetch_grn": self.fetch_grn,
            "fetch_history": self.fetch_history,
            "post_to_erp": self.post_to_erp,
            "schedule_payment": self.schedule_payment,
            "notify_vendor": self.notify_vendor,
            "notify_finance_team": self.notify_finance_team,
        }

    def _load_erp_data(self) -> Dict[str, Any]:
        """Load mock ERP data"""
        data_path = "data/generated/sample_data.json"
        if os.path.exists(data_path):
            with open(data_path, "r") as f:
                return json.load(f)
        return {}

    def _load_vendor_db(self) -> Dict[str, Any]:
        """Load vendor database"""
        data_path = "data/generated/sample_data.json"
        if os.path.exists(data_path):
            with open(data_path, "r") as f:
                data = json.load(f)
                return data.get("vendors", {})
        return {}

    # ==================== TOOL IMPLEMENTATIONS ====================

    def ocr_extract(
        self, image_path: str, provider: str = "tesseract"
    ) -> Dict[str, Any]:
        """
        Extract text from invoice using OCR
        Stage: UNDERSTAND
        Providers: tesseract, google_vision, aws_textract
        """
        if provider == "tesseract":
            return self._tesseract_ocr(image_path)
        elif provider == "google_vision":
            # Would use Google Vision API
            return {
                "error": "Google Vision not configured",
                "fallback": "Use tesseract instead",
                "server": "ATLAS",
            }
        elif provider == "aws_textract":
            # Would use AWS Textract API
            return {
                "error": "AWS Textract not configured",
                "fallback": "Use tesseract instead",
                "server": "ATLAS",
            }
        else:
            return {
                "error": f"Unknown OCR provider: {provider}",
                "available_providers": ["tesseract", "google_vision", "aws_textract"],
                "server": "ATLAS",
            }

    def _tesseract_ocr(self, image_path: str) -> Dict[str, Any]:
        """Run REAL Tesseract OCR"""
        try:
            img = Image.open(image_path)

            # Extract text
            text = pytesseract.image_to_string(img)

            # Get confidence data
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            confidences = [c for c in data["conf"] if c != -1]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            return {
                "text": text,
                "confidence": avg_confidence,
                "word_count": len(text.split()),
                "success": True,
                "provider": "tesseract",
                "server": "ATLAS",
            }
        except Exception as e:
            return {
                "text": "",
                "confidence": 0,
                "word_count": 0,
                "success": False,
                "error": str(e),
                "server": "ATLAS",
            }

    def enrich_vendor(
        self, vendor_name: str, provider: str = "vendor_db"
    ) -> Dict[str, Any]:
        """
        Enrich vendor data
        Stage: PREPARE
        Providers: clearbit, people_data_labs, vendor_db
        """
        if provider == "vendor_db":
            return self._enrich_from_vendor_db(vendor_name)
        elif provider == "clearbit":
            return {
                "error": "Clearbit not configured",
                "fallback": "Use vendor_db instead",
                "server": "ATLAS",
            }
        elif provider == "people_data_labs":
            return {
                "error": "People Data Labs not configured",
                "fallback": "Use vendor_db instead",
                "server": "ATLAS",
            }
        else:
            return self._mock_enrichment(vendor_name)

    def _enrich_from_vendor_db(self, vendor_name: str) -> Dict[str, Any]:
        """Enrich from local vendor database"""
        vendor_data = self.vendor_db.get(vendor_name)

        if vendor_data:
            return {
                "source": "vendor_db",
                "credit_score": vendor_data.get("enrichment_meta", {}).get(
                    "credit_score", 700
                ),
                "risk_score": vendor_data.get("enrichment_meta", {}).get(
                    "risk_score", 0.2
                ),
                "tax_id": vendor_data.get("tax_id"),
                "years_in_business": vendor_data.get("enrichment_meta", {}).get(
                    "years_in_business", 5
                ),
                "payment_history": vendor_data.get("enrichment_meta", {}).get(
                    "payment_history", "good"
                ),
                "vendor_category": vendor_data.get("enrichment_meta", {}).get(
                    "vendor_category", "General"
                ),
                "server": "ATLAS",
            }
        else:
            return self._mock_enrichment(vendor_name)

    def _mock_enrichment(self, vendor_name: str) -> Dict[str, Any]:
        """Mock enrichment when no data available"""
        return {
            "source": "mock",
            "credit_score": 700,
            "risk_score": 0.25,
            "tax_id": "MOCK_TAX_ID",
            "years_in_business": 5,
            "payment_history": "unknown",
            "vendor_category": "General",
            "note": "Using mock enrichment - no vendor data found",
            "server": "ATLAS",
        }

    def fetch_po(self, po_refs: List[str]) -> Dict[str, Any]:
        """
        Fetch Purchase Orders from ERP
        Stage: RETRIEVE
        """
        all_pos = self.erp_data.get("purchase_orders", [])

        matched = []
        for po in all_pos:
            if po.get("po_id") in po_refs:
                matched.append(po)

        return {
            "pos_found": len(matched),
            "pos": matched,
            "server": "ATLAS",
            "is_mock": True,  # Would be real SAP/NetSuite call
        }

    def fetch_grn(self, po_refs: List[str]) -> Dict[str, Any]:
        """
        Fetch Goods Received Notes from ERP
        Stage: RETRIEVE
        """
        all_grns = self.erp_data.get("goods_received_notes", [])

        matched = []
        for grn in all_grns:
            if grn.get("po_ref") in po_refs:
                matched.append(grn)

        return {
            "grns_found": len(matched),
            "grns": matched,
            "server": "ATLAS",
            "is_mock": True,
        }

    def fetch_history(self, vendor_name: str) -> Dict[str, Any]:
        """
        Fetch historical invoices for vendor from ERP
        Stage: RETRIEVE
        """
        all_history = self.erp_data.get("historical_invoices", [])

        matched = []
        for invoice in all_history:
            if vendor_name and vendor_name.upper() in invoice.get("vendor", "").upper():
                matched.append(invoice)

        return {
            "history_count": len(matched),
            "invoices": matched,
            "server": "ATLAS",
            "is_mock": True,
        }

    def post_to_erp(self, accounting_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Post journal entries to ERP
        Stage: POSTING
        """
        # Mock ERP posting
        erp_txn_id = f"ERP-TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return {
            "success": True,
            "erp_txn_id": erp_txn_id,
            "entries_posted": len(accounting_entries),
            "timestamp": datetime.now().isoformat(),
            "server": "ATLAS",
            "is_mock": True,  # Would be real SAP/NetSuite call
        }

    def schedule_payment(
        self, invoice_data: Dict[str, Any], vendor_name: str
    ) -> Dict[str, Any]:
        """
        Schedule payment in ERP
        Stage: POSTING
        """
        payment_id = f"PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        due_date = invoice_data.get("due_date", datetime.now().isoformat())

        return {
            "success": True,
            "payment_id": payment_id,
            "due_date": due_date,
            "amount": invoice_data.get("amount"),
            "vendor": vendor_name,
            "timestamp": datetime.now().isoformat(),
            "server": "ATLAS",
            "is_mock": True,
        }

    def notify_vendor(
        self, invoice_id: str, vendor_email: str = "billing@vendor.com"
    ) -> Dict[str, Any]:
        """
        Send notification to vendor
        Stage: NOTIFY
        """
        # Mock email notification
        # In production, would use SMTP or service like SendGrid

        return {
            "success": True,
            "recipient": "vendor",
            "email": vendor_email,
            "subject": f"Invoice {invoice_id} Processed",
            "status": "sent",
            "sent_at": datetime.now().isoformat(),
            "server": "ATLAS",
            "is_mock": True,  # Could use real SMTP
        }

    def notify_finance_team(
        self, invoice_id: str, finance_email: str = "finance@company.com"
    ) -> Dict[str, Any]:
        """
        Send notification to finance team
        Stage: NOTIFY
        """
        # Mock email notification

        return {
            "success": True,
            "recipient": "finance_team",
            "email": finance_email,
            "subject": f"Invoice {invoice_id} Approved",
            "status": "sent",
            "sent_at": datetime.now().isoformat(),
            "server": "ATLAS",
            "is_mock": True,
        }

    # ==================== MCP SERVER INTERFACE ====================

    def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """MCP tool call interface"""
        if tool_name not in self.tools:
            return {
                "error": f"Tool '{tool_name}' not found in ATLAS server",
                "available_tools": list(self.tools.keys()),
            }

        try:
            result = self.tools[tool_name](**kwargs)
            return result
        except Exception as e:
            return {"error": str(e), "tool": tool_name, "server": "ATLAS"}

    def list_tools(self) -> List[str]:
        """List all available tools"""
        return list(self.tools.keys())


# Create singleton instance
atlas_server = AtlasServer()


if __name__ == "__main__":
    # Test ATLAS server tools
    print("🌐 MCP ATLAS Server - Test")
    print(f"Available tools: {atlas_server.list_tools()}")

    # Test OCR
    test_image = "data/generated/images/invoice_001.png"
    if os.path.exists(test_image):
        result = atlas_server.call_tool(
            "ocr_extract", image_path=test_image, provider="tesseract"
        )
        print(f"\nOCR result: Confidence={result.get('confidence', 0):.1f}%")
