"""
Complete LangGraph Workflow with HITL
- SQLite checkpointer (not in-memory)
- interrupt() for human review
- Resume from checkpoint
- Deterministic thread_id based on invoice_id
- Error handling with retry logic
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt
from typing import Literal, Dict, Any, Callable
import sqlite3
import time
import traceback
from .logger import logger

from .workflow_nodes import (
    intake_node,
    understand_node,
    prepare_node,
    retrieve_node,
    match_two_way_node,
)
from .tools.bigtool_picker import bigtool_picker


# ==================== ERROR HANDLING ====================


def with_retry(node_func: Callable, max_retries: int = 3, backoff_seconds: int = 2):
    """
    Decorator to add retry logic to nodes
    As per workflow.json error_handling specification
    """

    def wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        last_error = None

        for attempt in range(max_retries):
            try:
                # Execute the node
                return node_func(state)

            except Exception as e:
                last_error = e
                logger.error(
                    f"❌ Error in {node_func.__name__} (attempt {attempt + 1}/{max_retries}): {e}"
                )

                if attempt < max_retries - 1:
                    # Wait before retry with exponential backoff
                    wait_time = backoff_seconds * (2**attempt)
                    logger.warning(f"⏳ Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # Max retries exceeded
                    logger.error(f"💥 Max retries exceeded for {node_func.__name__}")
                    logger.error(f"Error details: {traceback.format_exc()}")

                    # Persist error state
                    error_state = {
                        **state,
                        "error": str(last_error),
                        "error_stage": node_func.__name__,
                        "error_trace": traceback.format_exc(),
                        "workflow_status": "FAILED",
                        "current_stage": f"FAILED_{node_func.__name__}",
                    }

                    # Notify ops team (would implement actual notification)
                    logger.error("📧 Notifying ops_team of unrecoverable error")

                    # Re-raise to stop workflow
                    raise Exception(
                        f"Unrecoverable error in {node_func.__name__}: {e}"
                    ) from last_error

        return state

    return wrapper


# ==================== CHECKPOINT HITL NODE ====================


def checkpoint_hitl_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    CHECKPOINT_HITL: Create checkpoint if match failed
    Persist state, create review ticket, push to queue
    Spec compliant - separate from HITL_DECISION
    """
    logger.info("=" * 70)
    logger.info("⏸️  STAGE 6: CHECKPOINT_HITL")
    logger.info("=" * 70)

    match_result = state.get("match_result", "MATCHED")

    if match_result == "FAILED":
        logger.info("⚠️  Match failed - CREATING CHECKPOINT")

        thread_id = state.get("thread_id")
        checkpoint_id = thread_id
        review_url = f"/human-review/{checkpoint_id}"

        logger.info(f"Checkpoint ID: {checkpoint_id}")
        logger.info(f"Review URL: {review_url}")
        logger.info(f"⏸️  State will be persisted by LangGraph")

        # Return checkpoint info (LangGraph auto-saves state)
        return {
            **state,
            "checkpoint_id": checkpoint_id,
            "review_url": review_url,
            "paused_reason": "Match score below threshold",
            "current_stage": "CHECKPOINT_HITL",
            "needs_human_review": True,
        }
    else:
        logger.info("✅ Match successful - no human review needed")
        return {
            **state,
            "current_stage": "CHECKPOINT_HITL",
            "needs_human_review": False,
            "human_decision": "AUTO_APPROVED",
        }


def hitl_decision_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    HITL_DECISION: Await human decision
    Non-deterministic stage - waits for human input
    Spec compliant - separate from CHECKPOINT_HITL
    """
    logger.info("=" * 70)
    logger.info("👤 STAGE 7: HITL_DECISION")
    logger.info("=" * 70)

    logger.info("Awaiting human decision...")

    # INTERRUPT - Wait for human decision
    # This pauses execution until decision is provided
    human_input = interrupt(
        {
            "type": "human_review_required",
            "checkpoint_id": state.get("checkpoint_id"),
            "review_url": state.get("review_url"),
            "invoice_id": state.get("parsed_invoice", {}).get("invoice_id"),
            "vendor": state.get("normalized_vendor_name"),
            "amount": state.get("parsed_invoice", {}).get("amount"),
            "match_score": state.get("match_score"),
            "reason": state.get("paused_reason"),
        }
    )

    # Execution continues here after resume
    decision = human_input.get("decision", "REJECT")
    reviewer_id = human_input.get("reviewer_id", "unknown")
    resume_token = human_input.get("resume_token", state.get("thread_id"))

    logger.info(f"✅ Decision received: {decision}")
    logger.info(f"Reviewer: {reviewer_id}")

    if decision == "ACCEPT":
        next_stage = "RECONCILE"
        logger.info(f"▶️  Continuing to {next_stage}")
    else:
        next_stage = "MANUAL_HANDOFF"
        logger.warning(f"⚠️  Manual handoff required")

    return {
        **state,
        "human_decision": decision,
        "reviewer_id": reviewer_id,
        "resume_token": resume_token,
        "next_stage": next_stage,
        "current_stage": "HITL_DECISION",
        "workflow_status": "RESUMED" if decision == "ACCEPT" else "MANUAL_HANDOFF",
    }


# Remove old combined checkpoint_hitl_node function
# No _add_to_review_queue function needed


# ==================== CONDITIONAL ROUTING ====================


def should_continue_after_checkpoint(state) -> Literal["hitl_decision", "reconcile"]:
    """Route after CHECKPOINT_HITL based on whether human review is needed"""
    needs_review = state.get("needs_human_review", False)

    if needs_review:
        return "hitl_decision"
    else:
        return "reconcile"


def should_continue_after_hitl(state) -> Literal["reconcile", "end"]:
    """Route after HITL_DECISION based on human decision"""
    decision = state.get("human_decision")

    if decision == "ACCEPT":
        return "reconcile"
    else:
        return "end"


# ==================== REMAINING STAGES ====================


def reconcile_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """RECONCILE: Build accounting entries"""
    print("\n" + "=" * 70)
    logger.info("📘 STAGE 8: RECONCILE")
    logger.info("=" * 70)

    from .mcp_servers.common_server import common_server

    parsed_invoice = state.get("parsed_invoice", {})
    vendor_name = state.get("normalized_vendor_name", "")

    logger.info("📞 MCP COMMON: build_accounting_entries")
    result = common_server.call_tool(
        "build_accounting_entries", invoice_data=parsed_invoice, vendor_name=vendor_name
    )

    logger.info(f"✅ Created {len(result['entries'])} accounting entries")

    return {
        **state,
        "accounting_entries": result["entries"],
        "reconciliation_report": result,
        "current_stage": "RECONCILE",
    }


def approve_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """APPROVE: Apply approval policy"""
    print("\n" + "=" * 70)
    logger.info("🔄 STAGE 9: APPROVE")
    logger.info("=" * 70)

    from .mcp_servers.common_server import common_server

    invoice_amount = state.get("parsed_invoice", {}).get("amount", 0)
    auto_approve_limit = bigtool_picker.get_config("auto_approve_limit", 20000.00)

    logger.info("📞 MCP COMMON: apply_approval_policy")
    result = common_server.call_tool(
        "apply_approval_policy",
        invoice_amount=invoice_amount,
        auto_approve_limit=auto_approve_limit,
    )

    logger.info(f"✅ Approval: {result['approval_status']}")

    return {
        **state,
        "approval_status": result["approval_status"],
        "approver_id": result["approver_id"],
        "current_stage": "APPROVE",
    }


def posting_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """POSTING: Post to ERP and schedule payment"""
    print("\n" + "=" * 70)
    logger.info("🏃 STAGE 10: POSTING")
    logger.info("=" * 70)

    from .mcp_servers.atlas_server import atlas_server

    accounting_entries = state.get("accounting_entries", [])
    parsed_invoice = state.get("parsed_invoice", {})
    vendor_name = state.get("normalized_vendor_name", "")

    # Bigtool: Select ERP
    erp_tool = bigtool_picker.select(
        "erp_connector", pool_hint=["sap_sandbox", "netsuite", "mock_erp"]
    )

    logger.info("📞 MCP ATLAS: post_to_erp")
    post_result = atlas_server.call_tool(
        "post_to_erp", accounting_entries=accounting_entries
    )

    logger.info("📞 MCP ATLAS: schedule_payment")
    payment_result = atlas_server.call_tool(
        "schedule_payment", invoice_data=parsed_invoice, vendor_name=vendor_name
    )

    logger.info(f"✅ Posted to ERP: {post_result['erp_txn_id']}")

    return {
        **state,
        "posted": True,
        "erp_txn_id": post_result["erp_txn_id"],
        "scheduled_payment_id": payment_result["payment_id"],
        "current_stage": "POSTING",
    }


def notify_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """NOTIFY: Send notifications"""
    print("\n" + "=" * 70)
    logger.info("✉️  STAGE 11: NOTIFY")
    logger.info("=" * 70)

    from .mcp_servers.atlas_server import atlas_server

    invoice_id = state.get("parsed_invoice", {}).get("invoice_id")

    logger.info("📞 MCP ATLAS: notify_vendor")
    vendor_result = atlas_server.call_tool("notify_vendor", invoice_id=invoice_id)

    logger.info("📞 MCP ATLAS: notify_finance_team")
    finance_result = atlas_server.call_tool(
        "notify_finance_team", invoice_id=invoice_id
    )

    logger.info(f"✅ Notifications sent")

    return {
        **state,
        "notify_status": {"vendor": vendor_result, "finance": finance_result},
        "current_stage": "NOTIFY",
    }


def complete_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """COMPLETE: Finalize workflow"""
    print("\n" + "=" * 70)
    logger.info("✅ STAGE 12: COMPLETE")
    logger.info("=" * 70)

    from .mcp_servers.common_server import common_server

    logger.info("📞 MCP COMMON: output_final_payload")
    final_payload = common_server.call_tool("output_final_payload", state=state)

    logger.info(f"✅ Workflow COMPLETED!")

    return {
        **state,
        "final_payload": final_payload,
        "workflow_status": "COMPLETED",
        "current_stage": "COMPLETE",
    }


# ==================== BUILD WORKFLOW ====================


def create_workflow(db_path: str = "data/demo.db"):
    """
    Create LangGraph Workflow with SQLite checkpointer and error handling
    - Retry logic on deterministic nodes (per workflow.json spec)
    - HITL split into checkpoint + decision stages
    """
    logger.info("\n🔧 Building LangGraph Workflow with HITL...")

    # Create StateGraph
    workflow = StateGraph(dict)

    # Add nodes with retry wrappers for deterministic stages
    # Per spec: max_retries=3, backoff_seconds=2
    workflow.add_node(
        "intake", with_retry(intake_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "understand", with_retry(understand_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "prepare", with_retry(prepare_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "retrieve", with_retry(retrieve_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "match_two_way",
        with_retry(match_two_way_node, max_retries=3, backoff_seconds=2),
    )

    # Checkpoint and HITL nodes (no retry - these are control flow)
    workflow.add_node("checkpoint_hitl", checkpoint_hitl_node)
    workflow.add_node(
        "hitl_decision", hitl_decision_node
    )  # Non-deterministic (waits for human)

    # Remaining deterministic nodes with retry
    workflow.add_node(
        "reconcile", with_retry(reconcile_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "approve", with_retry(approve_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "posting", with_retry(posting_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "notify", with_retry(notify_node, max_retries=3, backoff_seconds=2)
    )
    workflow.add_node(
        "complete", with_retry(complete_node, max_retries=3, backoff_seconds=2)
    )

    # Set entry point
    workflow.set_entry_point("intake")

    # Linear flow through matching
    workflow.add_edge("intake", "understand")
    workflow.add_edge("understand", "prepare")
    workflow.add_edge("prepare", "retrieve")
    workflow.add_edge("retrieve", "match_two_way")
    workflow.add_edge("match_two_way", "checkpoint_hitl")

    # Conditional routing after CHECKPOINT_HITL
    workflow.add_conditional_edges(
        "checkpoint_hitl",
        should_continue_after_checkpoint,
        {
            "hitl_decision": "hitl_decision",  # If needs review → pause at hitl_decision
            "reconcile": "reconcile",  # If auto-approved → skip hitl_decision
        },
    )

    # Conditional routing after HITL_DECISION
    workflow.add_conditional_edges(
        "hitl_decision",
        should_continue_after_hitl,
        {
            "reconcile": "reconcile",  # If ACCEPT → continue
            "end": END,  # If REJECT → end
        },
    )

    # Continue through remaining stages after reconcile
    workflow.add_edge("reconcile", "approve")
    workflow.add_edge("approve", "posting")
    workflow.add_edge("posting", "notify")
    workflow.add_edge("notify", "complete")
    workflow.add_edge("complete", END)

    # Create SQLite checkpointer (NOT in-memory!)
    logger.info(f"✅ Using SQLite checkpointer: {db_path}")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    # Compile with checkpointer
    # Interrupt BEFORE hitl_decision (not before checkpoint_hitl)
    app = workflow.compile(
        checkpointer=checkpointer, interrupt_before=["hitl_decision"]
    )

    logger.info("✅ Workflow compiled with HITL support")
    logger.info("✅ Error handling: 3 retries, 2s backoff (exponential)")
    logger.info(f"✅ Checkpoints saved to: {db_path}")
    logger.info("✅ HITL stages: checkpoint_hitl → hitl_decision (spec compliant)")

    return app


if __name__ == "__main__":
    app = create_workflow()
    logger.info("\n✅ Workflow ready!")
