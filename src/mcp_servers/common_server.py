#!/usr/bin/env python3
"""
MCP COMMON Server
Handles abilities requiring no external data:
- Schema validation
- Normalization
- Parsing
- Matching algorithms
- Accounting logic
"""
import re
from datetime import datetime
from typing import Dict, Any, List


class CommonServer:
    """
    MCP COMMON Server - Internal operations only
    No external system dependencies
    """

    def __init__(self):
        self.name = "COMMON"
        self.version = "1.0.0"
        self.tools = self._register_tools()

    def _register_tools(self) -> Dict[str, Any]:
        """Register all available tools"""
        return {
            "validate_schema": self.validate_schema,
            "normalize_vendor": self.normalize_vendor,
            "parse_invoice_text": self.parse_invoice_text,
            "compute_match_score": self.compute_match_score,
            "compute_flags": self.compute_flags,
            "build_accounting_entries": self.build_accounting_entries,
            "apply_approval_policy": self.apply_approval_policy,
            "output_final_payload": self.output_final_payload,
        }

    # ==================== TOOL IMPLEMENTATIONS ====================

    def validate_schema(self, invoice_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate invoice schema
        Stage: INTAKE

        For flexible processing, we only require invoice_id to be present.
        Other fields (vendor_name, amount, line_items) can be extracted later
        via OCR in the UNDERSTAND stage if attachments are provided.
        """
        errors = []

        # Only invoice_id is truly required for tracking
        if "invoice_id" not in invoice_payload:
            errors.append("Missing required field: invoice_id")

        # Validate amount if provided
        if "amount" in invoice_payload:
            try:
                float(invoice_payload["amount"])
            except (ValueError, TypeError):
                errors.append("Invalid amount: must be a number")

        # Validate line_items if provided
        if "line_items" in invoice_payload:
            if not isinstance(invoice_payload["line_items"], list):
                errors.append("Invalid line_items: must be a list")
            elif len(invoice_payload["line_items"]) == 0:
                errors.append("Invalid line_items: must contain at least one item")

        # Validate that we have either manual data OR attachments for OCR
        manual_fields = ["vendor_name", "amount", "line_items"]
        has_manual_data = any(field in invoice_payload for field in manual_fields)
        has_attachments = (
            "attachments" in invoice_payload and len(invoice_payload["attachments"]) > 0
        )

        if not has_manual_data and not has_attachments:
            errors.append(
                "Either manual invoice data or attachments " "must be provided"
            )

        return {"valid": len(errors) == 0, "errors": errors, "server": "COMMON"}

    def normalize_vendor(self, vendor_name: str) -> Dict[str, Any]:
        """
        Normalize vendor name to standard format
        Stage: PREPARE
        """
        # Convert to uppercase
        normalized = vendor_name.upper().strip()

        # Remove extra spaces
        normalized = " ".join(normalized.split())

        # Standardize legal entity suffixes
        replacements = {
            " LIMITED": " LTD",
            " INCORPORATED": " INC",
            " CORPORATION": " CORP",
            " COMPANY": " CO",
        }

        for old, new in replacements.items():
            if normalized.endswith(old):
                normalized = normalized[: -len(old)] + new

        return {"original": vendor_name, "normalized": normalized, "server": "COMMON"}

    def parse_invoice_text(self, ocr_text: str) -> Dict[str, Any]:
        """
        Parse invoice data from OCR text
        Stage: UNDERSTAND
        """
        # Extract invoice ID
        invoice_pattern = r"Invoice\s*#\s*:\s*([A-Z0-9\-]+)"
        invoice_match = re.search(invoice_pattern, ocr_text, re.IGNORECASE)
        invoice_id = invoice_match.group(1) if invoice_match else None

        # Extract dates
        date_pattern = r"(\d{4}-\d{2}-\d{2})"
        dates = re.findall(date_pattern, ocr_text)

        # Extract vendor
        vendor_pattern = r"INVOICE\s+([A-Za-z\s]+(?:Ltd|Inc|LLC|Corp|Corporation))"
        vendor_match = re.search(vendor_pattern, ocr_text)
        vendor_name = vendor_match.group(1).strip() if vendor_match else None

        # Extract tax ID
        tax_pattern = r"Tax ID:\s*([A-Z0-9]+)"
        tax_match = re.search(tax_pattern, ocr_text)
        tax_id = tax_match.group(1) if tax_match else None

        # Extract currency
        currency_pattern = r"Currency:\s*([A-Z]{3})"
        currency_match = re.search(currency_pattern, ocr_text)
        currency = currency_match.group(1) if currency_match else "USD"

        # Extract total amount
        total_pattern = r"TOTAL:\s*\$\s*([\d,]+\.?\d{0,2})"
        total_match = re.search(total_pattern, ocr_text)
        total_amount = (
            float(total_match.group(1).replace(",", "")) if total_match else None
        )

        # Extract line items
        line_items = self._extract_line_items(ocr_text)

        return {
            "invoice_id": invoice_id,
            "vendor_name": vendor_name,
            "vendor_tax_id": tax_id,
            "invoice_date": dates[0] if len(dates) > 0 else None,
            "due_date": dates[1] if len(dates) > 1 else None,
            "currency": currency,
            "amount": total_amount,
            "line_items": line_items,
            "server": "COMMON",
        }

    def _extract_line_items(self, text: str) -> List[Dict[str, Any]]:
        """Extract line items from OCR text"""
        line_items = []

        # Pattern: Description + PO Ref + Qty + Unit Price + Total
        item_pattern = r"([A-Za-z0-9\s]+?)\s+(PO-[\d-]+)\s+(\d+)\s+\$\s*([\d,]+\.?\d{0,2})\s+\$\s*([\d,]+\.?\d{0,2})"

        matches = re.finditer(item_pattern, text)

        for match in matches:
            desc, po_ref, qty, unit_price, total = match.groups()
            line_items.append(
                {
                    "desc": desc.strip(),
                    "po_ref": po_ref,
                    "qty": int(qty),
                    "unit_price": float(unit_price.replace(",", "")),
                    "total": float(total.replace(",", "")),
                }
            )

        return line_items

    def compute_match_score(
        self,
        invoice_data: Dict[str, Any],
        po_data: Dict[str, Any],
        threshold: float = 0.90,
    ) -> Dict[str, Any]:
        """
        Compute 2-way match score
        Stage: MATCH_TWO_WAY
        """
        score_components = []

        # 1. Vendor match (30% weight)
        invoice_vendor = invoice_data.get("vendor_name", "").upper().strip()
        po_vendor = po_data.get("vendor", "").upper().strip()
        vendor_match = 1.0 if invoice_vendor == po_vendor else 0.0
        score_components.append(("vendor_match", vendor_match, 0.30))

        # 2. Amount match (40% weight)
        invoice_total = float(invoice_data.get("amount", 0))
        po_total = float(po_data.get("total_amount", 0))
        amount_diff = abs(invoice_total - po_total)
        amount_diff_pct = (amount_diff / po_total) * 100 if po_total > 0 else 100

        if amount_diff_pct <= 5:
            amount_match = 1.0
        elif amount_diff_pct <= 10:
            amount_match = 0.7
        elif amount_diff_pct <= 15:
            amount_match = 0.4
        else:
            amount_match = 0.1

        score_components.append(("amount_match", amount_match, 0.40))

        # 3. Line items match (30% weight)
        invoice_items = set()
        for item in invoice_data.get("line_items", []):
            desc = item.get("desc", "").lower().strip()
            if desc:
                invoice_items.add(desc)

        po_items = set()
        for item in po_data.get("items", []):
            desc = item.get("desc", "").lower().strip()
            if desc:
                po_items.add(desc)

        matches = 0
        total_items = max(len(invoice_items), len(po_items))

        if total_items > 0:
            for inv_item in invoice_items:
                for po_item in po_items:
                    if inv_item in po_item or po_item in inv_item:
                        matches += 1
                        break
            items_match = matches / total_items
        else:
            items_match = 0.0

        score_components.append(("line_items_match", items_match, 0.30))

        # Compute weighted total score
        total_score = sum([comp[1] * comp[2] for comp in score_components])

        return {
            "match_score": round(total_score, 4),
            "match_result": "MATCHED" if total_score >= threshold else "FAILED",
            "tolerance_pct": round(amount_diff_pct, 2),
            "threshold": threshold,
            "components": {
                "vendor_match": vendor_match,
                "amount_match": amount_match,
                "items_match": items_match,
            },
            "amount_difference": amount_diff,
            "server": "COMMON",
        }

    def compute_flags(
        self, invoice: Dict[str, Any], vendor_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute validation flags
        Stage: PREPARE
        """
        warnings = []
        errors = []

        # Check for missing information
        if not vendor_profile.get("tax_id"):
            warnings.append("Missing vendor tax ID")

        if not invoice.get("invoice_date"):
            warnings.append("Missing invoice date")

        if not invoice.get("due_date"):
            warnings.append("Missing due date")

        # Check risk score
        risk_score = vendor_profile.get("enrichment_meta", {}).get("risk_score", 0)
        if risk_score > 0.5:
            warnings.append(f"High risk vendor (risk score: {risk_score})")

        # Check credit score
        credit_score = vendor_profile.get("enrichment_meta", {}).get("credit_score", 0)
        if credit_score < 600:
            warnings.append(f"Low credit score ({credit_score})")

        return {
            "warnings": warnings,
            "errors": errors,
            "risk_score": risk_score,
            "credit_score": credit_score,
            "server": "COMMON",
        }

    def build_accounting_entries(
        self, invoice_data: Dict[str, Any], vendor_name: str
    ) -> Dict[str, Any]:
        """
        Build accounting entries
        Stage: RECONCILE
        """
        invoice_amount = float(invoice_data.get("amount", 0))

        accounting_entries = [
            {
                "account": "Accounts Payable",
                "type": "credit",
                "amount": invoice_amount,
                "vendor": vendor_name,
                "description": f"Invoice {invoice_data.get('invoice_id')}",
            },
            {
                "account": "Expense",
                "type": "debit",
                "amount": invoice_amount,
                "category": "IT Equipment",
                "description": f"Invoice {invoice_data.get('invoice_id')}",
            },
        ]

        return {
            "entries": accounting_entries,
            "total_debit": invoice_amount,
            "total_credit": invoice_amount,
            "balanced": True,
            "server": "COMMON",
        }

    def apply_approval_policy(
        self, invoice_amount: float, auto_approve_limit: float = 20000.00
    ) -> Dict[str, Any]:
        """
        Apply approval policy
        Stage: APPROVE
        """
        if invoice_amount <= auto_approve_limit:
            approval_status = "AUTO_APPROVED"
            approver_id = "system"
        else:
            approval_status = "ESCALATED"
            approver_id = "finance_manager"

        return {
            "approval_status": approval_status,
            "approver_id": approver_id,
            "amount": invoice_amount,
            "limit": auto_approve_limit,
            "server": "COMMON",
        }

    def output_final_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create final output payload
        Stage: COMPLETE
        """
        final_payload = {
            "workflow_id": state.get("workflow_id"),
            "invoice_id": state.get("parsed_invoice", {}).get("invoice_id"),
            "status": "COMPLETED",
            "processed_at": datetime.now().isoformat(),
            "summary": {
                "vendor": state.get("normalized_vendor_name"),
                "amount": state.get("parsed_invoice", {}).get("amount"),
                "match_score": state.get("match_score"),
                "approval_status": state.get("approval_status"),
                "erp_txn_id": state.get("erp_txn_id"),
                "payment_id": state.get("scheduled_payment_id"),
            },
            "details": {
                "invoice": state.get("parsed_invoice"),
                "vendor_profile": state.get("vendor_profile"),
                "accounting_entries": state.get("accounting_entries"),
                "reconciliation_report": state.get("reconciliation_report"),
            },
            "server": "COMMON",
        }

        return final_payload

    # ==================== MCP SERVER INTERFACE ====================

    def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """MCP tool call interface"""
        if tool_name not in self.tools:
            return {
                "error": f"Tool '{tool_name}' not found in COMMON server",
                "available_tools": list(self.tools.keys()),
            }

        try:
            result = self.tools[tool_name](**kwargs)
            return result
        except Exception as e:
            return {"error": str(e), "tool": tool_name, "server": "COMMON"}

    def list_tools(self) -> List[str]:
        """List all available tools"""
        return list(self.tools.keys())


# Create singleton instance
common_server = CommonServer()


if __name__ == "__main__":
    # Test COMMON server tools
    print("🔧 MCP COMMON Server - Test")
    print(f"Available tools: {common_server.list_tools()}")

    # Test validate_schema
    test_invoice = {
        "invoice_id": "INV-001",
        "vendor_name": "Test Corp",
        "amount": 1000.0,
        "currency": "USD",
        "line_items": [{"desc": "Item 1"}],
    }

    result = common_server.call_tool("validate_schema", invoice_payload=test_invoice)
    print(f"\nValidation result: {result}")
