"""MCP (Model Context Protocol) base interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class MCPClient(ABC):
    """Abstract base class for MCP clients."""
    
    @abstractmethod
    def resolve_library_id(self, library_name: str) -> str:
        """
        Resolve library name to library ID.
        
        Args:
            library_name: Human-readable library name (e.g., "oneTBB")
            
        Returns:
            Library ID (e.g., "uxlfoundation/oneTBB")
        """
        pass
    
    @abstractmethod
    def get_library_docs(
        self, 
        library_id: str, 
        query: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documentation chunks for a query.
        
        Args:
            library_id: Library identifier
            query: Search query (question or topic)
            max_results: Maximum number of doc chunks to return
            
        Returns:
            List of doc chunks with metadata:
            [
                {
                    "content": str,
                    "source": str,
                    "relevance_score": float,
                    "metadata": dict
                }
            ]
        """
        pass
    
    @abstractmethod
    def check_connection(self) -> bool:
        """
        Verify that the MCP server is accessible.
        
        Returns:
            True if connection is successful
        """
        pass


class MCPError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPConnectionError(MCPError):
    """Raised when connection to MCP server fails."""
    pass


class MCPLibraryNotFoundError(MCPError):
    """Raised when requested library is not found."""
    pass
