"""
Complete Workflow Nodes - According to workflow.json specification
All nodes use Bigtool picker and route through MCP servers
NO FALLBACKS - errors if tools not available
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, Any
from datetime import datetime
import uuid
import json
import shutil

# Import logger
from .logger import logger, set_tracker_id

# MCP Servers
from .mcp_servers.common_server import common_server
from .mcp_servers.atlas_server import atlas_server

# Bigtool Picker
from .tools.bigtool_picker import bigtool_picker


# ==================== STAGE 1: INTAKE ====================

def intake_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    INTAKE: Validate payload schema, persist raw invoice
    Mode: deterministic
    Tools: BigtoolPicker (storage), DB
    """
    logger.info("="*70)
    logger.info("📥 STAGE 1: INTAKE")
    logger.info("="*70)
    
    invoice_payload = state.get("invoice_payload", {})
    workflow_id = state.get("workflow_id", str(uuid.uuid4()))
    
    # Set tracker ID for this workflow
    set_tracker_id(workflow_id)
    
    # Bigtool: Select storage
    storage_tool = bigtool_picker.select(
        "storage",
        pool_hint=["s3", "gcs", "local_fs"]
    )
    logger.info(f"Storage: {storage_tool['name']}")
    
    # MCP COMMON: Validate schema
    logger.info("📞 MCP COMMON: validate_schema")
    
    # Add attachments to invoice_payload for validation
    attachments = state.get("attachments", [])
    validation_payload = invoice_payload.copy()
    validation_payload["attachments"] = attachments
    
    validation_result = common_server.call_tool(
        "validate_schema",
        invoice_payload=validation_payload
    )
    
    if not validation_result["valid"]:
        logger.error(f"Schema validation failed: {validation_result['errors']}")
        raise ValueError(f"Schema validation failed: {validation_result['errors']}")
    
    logger.info(f"✅ Schema valid (via {validation_result.get('server')})")
    
    # Persist raw invoice
    storage_path = "data/storage"
    os.makedirs(f"{storage_path}/invoices", exist_ok=True)
    os.makedirs(f"{storage_path}/attachments", exist_ok=True)
    
    raw_id = f"raw_{workflow_id[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    ingest_ts = datetime.now().isoformat()
    
    # Store invoice
    invoice_file = f"{storage_path}/invoices/{raw_id}.json"
    with open(invoice_file, 'w') as f:
        json.dump(invoice_payload, f, indent=2)
    
    # Store attachments
    attachments = state.get("attachments", [])
    stored_attachments = []
    for attachment_path in attachments:
        if os.path.exists(attachment_path):
            filename = os.path.basename(attachment_path)
            dest = f"{storage_path}/attachments/{raw_id}_{filename}"
            shutil.copy(attachment_path, dest)
            stored_attachments.append(dest)
    
    logs = state.get("logs", [])
    logs.append({
        "stage": "INTAKE",
        "timestamp": datetime.now().isoformat(),
        "action": "VALIDATED_AND_STORED",
        "mcp_server": "COMMON",
        "bigtool": storage_tool['name']
    })
    
    logger.info("✅ INTAKE completed")
    
    return {
        **state,
        "workflow_id": workflow_id,
        "raw_id": raw_id,
        "ingest_ts": ingest_ts,
        "validated": True,
        "storage_path": invoice_file,
        "attachments": stored_attachments,
        "current_stage": "INTAKE",
        "logs": logs
    }


# ==================== STAGE 2: UNDERSTAND ====================

def understand_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    UNDERSTAND: Run OCR, extract text, parse line items
    Mode: deterministic
    Tools: BigtoolPicker (OCR), NLPParser
    """
    print("\n" + "="*70)
    print("🧠 STAGE 2: UNDERSTAND")
    logger.info("="*70)
    
    invoice_payload = state.get("invoice_payload", {})
    attachments = state.get("attachments", [])
    
    # Check if we already have complete manual data
    required_fields = ["vendor_name", "amount", "line_items"]
    logger.info(f"📋 Checking invoice payload: {list(invoice_payload.keys())}")
    has_complete_data = all(field in invoice_payload
                            for field in required_fields)
    logger.info(f"📋 Has complete data: {has_complete_data}")
    
    if has_complete_data:
        logger.info("✅ Complete manual data provided - SKIPPING OCR")
        
        # Use the manually provided data as parsed_invoice
        parsed_invoice = invoice_payload.copy()
        
        # Extract detected POs from manual line items
        detected_pos = []
        for item in parsed_invoice.get("line_items", []):
            if item.get("po_ref"):
                detected_pos.append(item["po_ref"])
        detected_pos = list(set(detected_pos))
        
        logs = state.get("logs", [])
        logs.append({
            "stage": "UNDERSTAND",
            "timestamp": datetime.now().isoformat(),
            "action": "SKIP_OCR_USE_MANUAL_DATA",
            "reason": "Complete manual data provided",
            "detected_pos": detected_pos
        })
        
        return {
            **state,
            "parsed_invoice": parsed_invoice,
            "ocr_result": {"skipped": True, "reason": "Manual data provided"},
            "ocr_confidence": 1.0,  # Manual data is 100% confident
            "detected_pos": detected_pos,
            "current_stage": "UNDERSTAND",
            "logs": logs
        }
    
    # If no complete manual data, proceed with OCR
    logger.info("📋 Incomplete manual data - PROCEEDING with OCR")
    
    # Bigtool: Select OCR provider
    ocr_tool = bigtool_picker.select(
        "ocr",
        pool_hint=["google_vision", "tesseract", "aws_textract"]
    )
    logger.info(f"OCR Provider: {ocr_tool['name']}")
    
    if not attachments:
        raise ValueError("No attachments found for OCR - NO FALLBACK")
    
    # MCP ATLAS: OCR extraction
    primary_attachment = attachments[0]
    logger.info(f"📞 MCP ATLAS: ocr_extract")
    ocr_result = atlas_server.call_tool(
        "ocr_extract",
        image_path=primary_attachment,
        provider=ocr_tool['name']
    )
    
    if not ocr_result.get('success'):
        raise ValueError(f"OCR failed: {ocr_result.get('error')} - NO FALLBACK")
    
    logger.info(f"✅ OCR: {ocr_result['confidence']:.1f}% confidence (via {ocr_result.get('server')})")
    
    # MCP COMMON: Parse invoice text
    logger.info(f"📞 MCP COMMON: parse_invoice_text")
    parsed_data = common_server.call_tool(
        "parse_invoice_text",
        ocr_text=ocr_result['text']
    )
    
    # Merge with original payload
    invoice_payload = state.get("invoice_payload", {})
    parsed_invoice = {
        **invoice_payload,
        **{k: v for k, v in parsed_data.items() if v is not None and k != 'server'}
    }
    
    # Extract detected POs
    detected_pos = []
    for item in parsed_invoice.get("line_items", []):
        if "po_ref" in item:
            detected_pos.append(item["po_ref"])
    detected_pos = list(set(detected_pos))
    
    logs = state.get("logs", [])
    logs.append({
        "stage": "UNDERSTAND",
        "timestamp": datetime.now().isoformat(),
        "action": "OCR_AND_PARSE",
        "mcp_servers": ["ATLAS (OCR)", "COMMON (Parse)"],
        "bigtool": ocr_tool['name']
    })
    
    return {
        **state,
        "parsed_invoice": parsed_invoice,
        "ocr_result": ocr_result,
        "ocr_confidence": ocr_result['confidence'],
        "detected_pos": detected_pos,
        "current_stage": "UNDERSTAND",
        "logs": logs
    }


# ==================== STAGE 3: PREPARE ====================

def prepare_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    PREPARE: Normalize vendor, enrich profile, compute flags
    Mode: deterministic
    Tools: BigtoolPicker (enrichment), COMMON_utils
    """
    print("\n" + "="*70)
    print("🛠  STAGE 3: PREPARE")
    logger.info("="*70)
    
    parsed_invoice = state.get("parsed_invoice", {})
    vendor_name = parsed_invoice.get("vendor_name", "")
    
    # MCP COMMON: Normalize vendor
    logger.info(f"📞 MCP COMMON: normalize_vendor")
    norm_result = common_server.call_tool(
        "normalize_vendor",
        vendor_name=vendor_name
    )
    normalized_name = norm_result["normalized"]
    logger.info(f"✅ Normalized: {normalized_name}")
    
    # Bigtool: Select enrichment provider
    enrich_tool = bigtool_picker.select(
        "enrichment",
        pool_hint=["clearbit", "people_data_labs", "vendor_db"]
    )
    logger.info(f"Enrichment: {enrich_tool['name']}")
    
    # MCP ATLAS: Enrich vendor
    logger.info(f"📞 MCP ATLAS: enrich_vendor")
    enrichment_data = atlas_server.call_tool(
        "enrich_vendor",
        vendor_name=vendor_name,
        provider=enrich_tool['name']
    )
    
    # Build vendor profile
    vendor_profile = {
        "normalized_name": normalized_name,
        "tax_id": parsed_invoice.get("vendor_tax_id") or enrichment_data.get("tax_id"),
        "enrichment_meta": enrichment_data
    }
    
    # MCP COMMON: Compute flags
    logger.info(f"📞 MCP COMMON: compute_flags")
    flags = common_server.call_tool(
        "compute_flags",
        invoice=parsed_invoice,
        vendor_profile=vendor_profile
    )
    
    logs = state.get("logs", [])
    logs.append({
        "stage": "PREPARE",
        "timestamp": datetime.now().isoformat(),
        "action": "NORMALIZE_AND_ENRICH",
        "mcp_servers": ["COMMON (Normalize, Flags)", "ATLAS (Enrich)"],
        "bigtool": enrich_tool['name']
    })
    
    return {
        **state,
        "vendor_profile": vendor_profile,
        "normalized_vendor_name": normalized_name,
        "normalized_invoice": parsed_invoice,
        "flags": flags,
        "current_stage": "PREPARE",
        "logs": logs
    }


# ==================== STAGE 4: RETRIEVE ====================

def retrieve_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    RETRIEVE: Fetch POs, GRNs, history from ERP
    Mode: deterministic
    Tools: BigtoolPicker (erp_connector), ATLAS_client
    """
    print("\n" + "="*70)
    print("📚 STAGE 4: RETRIEVE")
    logger.info("="*70)
    
    detected_pos = state.get("detected_pos", [])
    vendor_name = state.get("normalized_vendor_name", "")
    
    # Bigtool: Select ERP connector
    erp_tool = bigtool_picker.select(
        "erp_connector",
        pool_hint=["sap_sandbox", "netsuite", "mock_erp"]
    )
    logger.info(f"ERP Connector: {erp_tool['name']}")
    
    # MCP ATLAS: Fetch POs
    logger.info(f"📞 MCP ATLAS: fetch_po")
    po_result = atlas_server.call_tool("fetch_po", po_refs=detected_pos)
    matched_pos = po_result.get("pos", [])
    
    # MCP ATLAS: Fetch GRNs
    logger.info(f"📞 MCP ATLAS: fetch_grn")
    grn_result = atlas_server.call_tool("fetch_grn", po_refs=detected_pos)
    matched_grns = grn_result.get("grns", [])
    
    # MCP ATLAS: Fetch history
    logger.info(f"📞 MCP ATLAS: fetch_history")
    history_result = atlas_server.call_tool("fetch_history", vendor_name=vendor_name)
    history = history_result.get("invoices", [])
    
    logger.info(f"✅ Found {len(matched_pos)} PO(s), {len(matched_grns)} GRN(s)")
    
    logs = state.get("logs", [])
    logs.append({
        "stage": "RETRIEVE",
        "timestamp": datetime.now().isoformat(),
        "action": "FETCH_ERP_DATA",
        "mcp_server": "ATLAS",
        "bigtool": erp_tool['name']
    })
    
    return {
        **state,
        "matched_pos": matched_pos,
        "matched_grns": matched_grns,
        "history": history,
        "current_stage": "RETRIEVE",
        "logs": logs
    }


# ==================== STAGE 5: MATCH_TWO_WAY ====================

def match_two_way_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    MATCH_TWO_WAY: Compute 2-way match score
    Mode: deterministic
    Tools: MatchEngine, COMMON_utils
    """
    print("\n" + "="*70)
    print("⚖️  STAGE 5: MATCH_TWO_WAY")
    logger.info("="*70)
    
    parsed_invoice = state.get("parsed_invoice", {})
    matched_pos = state.get("matched_pos", [])
    
    # Get threshold from config
    match_threshold = bigtool_picker.get_config("match_threshold", 0.90)
    
    if not matched_pos:
        raise ValueError("No POs found for matching - NO FALLBACK")
    
    # MCP COMMON: Compute match score
    logger.info(f"📞 MCP COMMON: compute_match_score")
    match_result = common_server.call_tool(
        "compute_match_score",
        invoice_data=parsed_invoice,
        po_data=matched_pos[0],
        threshold=match_threshold
    )
    
    match_score = match_result["match_score"]
    match_status = match_result["match_result"]
    
    logger.info(f"Match Score: {match_score * 100:.1f}%")
    logger.info(f"Threshold: {match_threshold * 100:.0f}%")
    logger.info(f"Result: {match_status}")
    
    logs = state.get("logs", [])
    logs.append({
        "stage": "MATCH_TWO_WAY",
        "timestamp": datetime.now().isoformat(),
        "action": "COMPUTE_MATCH_SCORE",
        "mcp_server": "COMMON",
        "match_score": match_score
    })
    
    return {
        **state,
        "match_score": match_score,
        "match_result": match_status,
        "tolerance_pct": match_result["tolerance_pct"],
        "match_evidence": match_result,
        "current_stage": "MATCH_TWO_WAY",
        "logs": logs
    }


# Export all nodes
__all__ = [
    'intake_node',
    'understand_node',
    'prepare_node',
    'retrieve_node',
    'match_two_way_node'
]
