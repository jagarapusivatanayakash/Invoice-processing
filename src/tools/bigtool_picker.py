"""
Bigtool Picker - Dynamic tool selection from configured pools
Loads from workflow.json config and selects best available tool
NO FALLBACKS - will error if tool not available
"""

import json
from typing import Dict, Any, Optional, List


class BigtoolPicker:
    """
    Bigtool for dynamic tool selection
    Selects from configured pools based on availability
    """

    def __init__(self, config_path: str = "workflow.json"):
        self.config = self._load_config(config_path)
        self.pools = self.config.get("tools_hint", {}).get("example_pools", {})

        # Tool availability - set based on what we actually have
        self.available_tools = {
            "ocr": ["tesseract"],  # Only Tesseract available
            "enrichment": ["vendor_db"],  # Only local vendor DB
            "erp_connector": ["mock_erp"],  # Only mock ERP
            "db": ["sqlite"],  # Only SQLite
            "email": [],  # None available (will error if used)
            "storage": ["local_fs"],  # Only local filesystem
        }

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load workflow.json configuration"""
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            # Return minimal config if file not found
            return {"config": {"match_threshold": 0.90, "two_way_tolerance_pct": 5}}

    def select(
        self,
        capability: str,
        context: Optional[Dict[str, Any]] = None,
        pool_hint: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Select tool from pool based on capability

        Args:
            capability: Type of tool needed (ocr, enrichment, etc.)
            context: Additional context for selection
            pool_hint: Preferred tools from config

        Returns:
            Selected tool info

        Raises:
            ValueError: If no tools available for capability (NO FALLBACK)
        """
        available = self.available_tools.get(capability, [])

        if not available:
            raise ValueError(
                f"NO TOOLS AVAILABLE for capability '{capability}'. "
                f"Pool hint: {pool_hint}. "
                f"NO FALLBACK configured."
            )

        # Select first available tool
        selected = available[0]

        print(f"🔧 Bigtool selected: {selected} for {capability}")

        return {
            "name": selected,
            "capability": capability,
            "available": True,
            "pool": available,
            "pool_hint": pool_hint or [],
        }

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get("config", {}).get(key, default)

    def list_available(self, capability: str) -> List[str]:
        """List available tools for a capability"""
        return self.available_tools.get(capability, [])


# Global instance
bigtool_picker = BigtoolPicker()
