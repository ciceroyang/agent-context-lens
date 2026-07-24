"""Audit coding-agent context without sending repository data to a model."""

from .scanner import ContextFile, Finding, Report, scan

__all__ = ["ContextFile", "Finding", "Report", "scan"]
__version__ = "0.2.0"
